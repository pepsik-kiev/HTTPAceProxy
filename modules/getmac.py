# -*- coding: utf-8 -*-
# http://multivax.com/last_question.html

"""Get the MAC address of remote hosts or network interfaces.
It provides a platform-independent interface to get the MAC addresses of:
* System network interfaces (by interface name)
* Remote hosts on the local network (by IPv4/IPv6 address or hostname)
It provides one function: `get_mac_address()`
Examples:
    from getmac import get_mac_address
    eth_mac = get_mac_address(interface="eth0")
    win_mac = get_mac_address(interface="Ethernet 3")
    ip_mac = get_mac_address(ip="192.168.0.1")
    ip6_mac = get_mac_address(ip6="::1")
    host_mac = get_mac_address(hostname="localhost")
    updated_mac = get_mac_address(ip="10.0.0.1", network_request=True)
"""

import ctypes
import logging
import os
import platform
import re
import shlex
import socket
import struct
import sys
import traceback
from subprocess import check_output

try:  # Python 3
    from subprocess import DEVNULL  # type: ignore
except ImportError:  # Python 2
    DEVNULL = open(os.devnull, 'wb')  # type: ignore

# Configure logging
log = logging.getLogger('getmac')
log.addHandler(logging.NullHandler())

__version__ = '0.8.1'
PY2 = sys.version_info[0] == 2

# Configurable settings
DEBUG = 0
PORT = 55555

# Platform identifiers
_SYST = platform.system()
if _SYST == 'Java':
    try:
        import java.lang
        _SYST = str(java.lang.System.getProperty("os.name"))
    except ImportError:
        log.critical("Can't determine OS: couldn't import java.lang on Jython")
WINDOWS = _SYST == 'Windows'
DARWIN = _SYST == 'Darwin'
OPENBSD = _SYST == 'OpenBSD'
FREEBSD = _SYST == 'FreeBSD'
BSD = OPENBSD or FREEBSD  # Not including Darwin for now
WSL = False  # Windows Subsystem for Linux (WSL)
LINUX = False
if _SYST == 'Linux':
    if 'Microsoft' in platform.version():
        WSL = True
    else:
        LINUX = True

PATH = os.environ.get('PATH', os.defpath).split(os.pathsep)
if not WINDOWS:
    PATH.extend(('/sbin', '/usr/sbin'))

# Use a copy of the environment so we don't
# modify the process's current environment.
ENV = dict(os.environ)
ENV['LC_ALL'] = 'C'  # Ensure ASCII output so we parse correctly

# Constants
IP4 = 0
IP6 = 1
INTERFACE = 2
HOSTNAME = 3

MAC_RE_COLON = r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})'
MAC_RE_DASH = r'([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})'
MAC_RE_DARWIN = r'([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})'

# Used for mypy (a data type analysis tool)
# If you're copying the code, this section can be safely removed
try:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from typing import Optional
except ImportError:
    pass


def get_mac_address(
        interface=None, ip=None, ip6=None,
        hostname=None, network_request=True
):
    # type: (Optional[str], Optional[str], Optional[str], Optional[str], bool) -> Optional[str]
    """Get a Unicast IEEE 802 MAC-48 address from a local interface or remote host.
    You must only use one of the first four arguments. If none of the arguments
    are selected, the default network interface for the system will be used.
    Exceptions will be handled silently and returned as a None.
    For the time being, it assumes you are using Ethernet.
    NOTES:
    * You MUST provide str-typed arguments, REGARDLESS of Python version.
    * localhost/127.0.0.1 will always return '00:00:00:00:00:00'
    Args:
        interface (str): Name of a local network interface (e.g "Ethernet 3", "eth0", "ens32")
        ip (str): Canonical dotted decimal IPv4 address of a remote host (e.g 192.168.0.1)
        ip6 (str): Canonical shortened IPv6 address of a remote host (e.g ff02::1:ffe7:7f19)
        hostname (str): DNS hostname of a remote host (e.g "router1.mycorp.com", "localhost")
        network_request (bool): Send a UDP packet to a remote host to populate
        the ARP/NDP tables for IPv4/IPv6. The port this packet is sent to can
        be configured using the module variable `getmac.PORT`.
    Returns:
        Lowercase colon-separated MAC address, or None if one could not be
        found or there was an error.
    """
    if (hostname and hostname == 'localhost') or (ip and ip == '127.0.0.1'):
        return '00:00:00:00:00:00'

    # Resolve hostname to an IP address
    if hostname:
        ip = socket.gethostbyname(hostname)

    # Populate the ARP table by sending a empty UDP packet to a high port
    if network_request and (ip or ip6):
        if ip:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        try:
            if ip:
                s.sendto(b'', (ip, PORT))
            else:
                s.sendto(b'', (ip6, PORT))
        except Exception:
            log.error("Failed to send ARP table population packet")
            if DEBUG:
                log.debug(traceback.format_exc())
        finally:
            s.close()

    # Setup the address hunt based on the arguments specified
    if ip6:
        if not socket.has_ipv6:
            log.error("Cannot get the MAC address of a IPv6 host: "
                      "IPv6 is not supported on this system")
            return None
        elif ':' not in ip6:
            log.error("Invalid IPv6 address: %s", ip6)
            return None
        to_find = ip6
        typ = IP6
    elif ip:
        to_find = ip
        typ = IP4
    else:  # Default to searching for interface
        typ = INTERFACE
        if interface:
            to_find = interface
        else:
            # Default to finding MAC of the interface with the default route
            if WINDOWS and network_request:
                to_find = _fetch_ip_using_dns()
                typ = IP4
            elif WINDOWS:
                to_find = 'Ethernet'
            elif BSD:
                if OPENBSD:
                    to_find = _get_default_iface_openbsd()  # type: ignore
                else:
                    to_find = _get_default_iface_freebsd()  # type: ignore
                if not to_find:
                    to_find = 'em0'
            else:
                to_find = _hunt_linux_default_iface()  # type: ignore
                if not to_find:
                    to_find = 'en0'

    mac = _hunt_for_mac(to_find, typ, network_request)
    log.debug("Raw MAC found: %s", mac)

    # Check and format the result to be lowercase, colon-separated
    if mac is not None:
        mac = str(mac)
        if not PY2:  # Strip bytestring conversion artifacts
            mac = mac.replace("b'", '').replace("'", '')\
                     .replace('\\n', '').replace('\\r', '')
        mac = mac.strip().lower().replace(' ', '').replace('-', ':')

        # Fix cases where there are no colons
        if ':' not in mac and len(mac) == 12:
            log.debug("Adding colons to MAC %s", mac)
            mac = ':'.join(mac[i:i + 2] for i in range(0, len(mac), 2))

        # Pad single-character octets with a leading zero (e.g Darwin's ARP output)
        elif len(mac) < 17:
            log.debug("Length of MAC %s is %d, padding single-character "
                      "octets with zeros", mac, len(mac))
            parts = mac.split(':')
            new_mac = []
            for part in parts:
                if len(part) == 1:
                    new_mac.append('0' + part)
                else:
                    new_mac.append(part)
            mac = ':'.join(new_mac)

        # MAC address should ALWAYS be 17 characters before being returned
        if len(mac) != 17:
            log.warning("MAC address %s is not 17 characters long!", mac)
            mac = None
        elif mac.count(':') != 5:
            log.warning("MAC address %s is missing ':' characters", mac)
            mac = None
    return mac


def _search(regex, text, group_index=0):
    # type: (str, str, int) -> Optional[str]
    match = re.search(regex, text)
    if match:
        return match.groups()[group_index]
    return None


def _popen(command, args):
    # type: (str, str) -> str
    for directory in PATH:
        executable = os.path.join(directory, command)
        if (os.path.exists(executable)
            and os.access(executable, os.F_OK | os.X_OK)
                and not os.path.isdir(executable)):
            break
    else:
        executable = command
    if DEBUG >= 3:
        log.debug("Running: '%s %s'", executable, args)
    return _call_proc(executable, args)


def _call_proc(executable, args):
    # type: (str, str) -> str
    if WINDOWS:
        cmd = executable + ' ' + args  # type: ignore
    else:
        cmd = [executable] + shlex.split(args)  # type: ignore
    output = check_output(cmd, stderr=DEVNULL, env=ENV)
    if DEBUG >= 4:
        log.debug("Output from '%s' command: %s", executable, str(output))
    if not PY2 and isinstance(output, bytes):
        return str(output, 'utf-8')
    else:
        return str(output)


def _windows_ctypes_host(host):
    # type: (str) -> Optional[str]
    if not PY2:  # Convert to bytes on Python 3+ (Fixes GitHub issue #7)
        host = host.encode()  # type: ignore
    try:
        inetaddr = ctypes.windll.wsock32.inet_addr(host)  # type: ignore
        if inetaddr in (0, -1):
            raise Exception
    except Exception:
        hostip = socket.gethostbyname(host)
        inetaddr = ctypes.windll.wsock32.inet_addr(hostip)  # type: ignore

    buffer = ctypes.c_buffer(6)
    addlen = ctypes.c_ulong(ctypes.sizeof(buffer))

    send_arp = ctypes.windll.Iphlpapi.SendARP  # type: ignore
    if send_arp(inetaddr, 0, ctypes.byref(buffer), ctypes.byref(addlen)) != 0:
        return None

    # Convert binary data into a string.
    macaddr = ''
    for intval in struct.unpack('BBBBBB', buffer):  # type: ignore
        if intval > 15:
            replacestr = '0x'
        else:
            replacestr = 'x'
        macaddr = ''.join([macaddr, hex(intval).replace(replacestr, '')])
    return macaddr


def _fcntl_iface(iface):
    # type: (str) -> str
    import fcntl
    if not PY2:
        iface = iface.encode()  # type: ignore
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 0x8927 = SIOCGIFADDR
    info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', iface[:15]))
    if PY2:
        return ':'.join(['%02x' % ord(char) for char in info[18:24]])
    else:
        return ':'.join(['%02x' % ord(chr(char)) for char in info[18:24]])


def _uuid_ip(ip):
    # type: (str) -> Optional[str]
    from uuid import _arp_getnode  # type: ignore
    backup = socket.gethostbyname
    try:
        socket.gethostbyname = lambda x: ip
        mac1 = _arp_getnode()
        if mac1 is not None:
            mac1 = _uuid_convert(mac1)
            mac2 = _arp_getnode()
            mac2 = _uuid_convert(mac2)
            if mac1 == mac2:
                return mac1
    except Exception:
        raise
    finally:
        socket.gethostbyname = backup
    return None


def _uuid_lanscan_iface(iface):
    # type: (str) -> Optional[str]
    from uuid import _find_mac  # type: ignore
    if not PY2:
        iface = bytes(iface, 'utf-8')  # type: ignore
    mac = _find_mac('lanscan', '-ai', [iface], lambda i: 0)
    if mac:
        return _uuid_convert(mac)
    return None


def _uuid_convert(mac):
    # type: (int) -> str
    return ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))


def _read_sys_iface_file(iface):
    # type: (str) -> Optional[str]
    data = _read_file('/sys/class/net/' + iface + '/address')
    # Sometimes this can be empty or a single newline character
    return None if data is not None and len(data) < 17 else data


def _read_arp_file(host):
    # type: (str) -> Optional[str]
    data = _read_file('/proc/net/arp')
    if data is not None and len(data) > 1:
        # Need a space, otherwise a search for 192.168.16.2
        # will match 192.168.16.254 if it comes first!
        return _search(re.escape(host) + r' .+' + MAC_RE_COLON, data)
    return None


def _read_file(filepath):
    # type: (str) -> Optional[str]
    try:
        with open(filepath) as f:
            return f.read()
    except (OSError, IOError):  # This is IOError on Python 2.7
        log.debug("Could not find file: '%s'", filepath)
        return None


def _hunt_for_mac(to_find, type_of_thing, net_ok=True):
    # type: (Optional[str], int, bool) -> Optional[str]
    """Tries a variety of methods to get a MAC address.
    Format of method lists:
    Tuple:  (regex, regex index, command, command args)
            Command args is a list of strings to attempt to use as arguments
    lambda: Function to call
    """
    if to_find is None:
        log.warning("_hunt_for_mac() failed: to_find is None")
        return None
    if not PY2 and isinstance(to_find, bytes):
        to_find = str(to_find, 'utf-8')

    if WINDOWS and type_of_thing == INTERFACE:
        methods = [
            # getmac - Connection Name
            (r'\r\n' + to_find + r'.*' + MAC_RE_DASH + r'.*\r\n',
             0, 'getmac.exe', ['/NH /V']),

            # ipconfig
            (to_find + r'(?:\n?[^\n]*){1,8}Physical Address[ .:]+' + MAC_RE_DASH + r'\r\n',
             0, 'ipconfig.exe', ['/all']),

            # getmac - Network Adapter (the human-readable name)
            (r'\r\n.*' + to_find + r'.*' + MAC_RE_DASH + r'.*\r\n',
             0, 'getmac.exe', ['/NH /V']),

            # wmic - WMI command line utility
            lambda x: _popen('wmic.exe', 'nic where "NetConnectionID = \'%s\'" get '
                                         'MACAddress /value' % x).strip().partition('=')[2],
        ]
    elif (WINDOWS or WSL) and type_of_thing in [IP4, IP6, HOSTNAME]:
        methods = [
            # arp -a - Parsing result with a regex
            (MAC_RE_DASH, 0, 'arp.exe', ['-a %s' % to_find]),
        ]

        # Add methods that make network requests
        # Insert it *after* arp.exe since that's probably faster.
        if net_ok and type_of_thing != IP6 and not WSL:
            methods.insert(1, _windows_ctypes_host)
    elif (DARWIN or FREEBSD) and type_of_thing == INTERFACE:
        methods = [
            (r'ether ' + MAC_RE_COLON,
             0, 'ifconfig', [to_find]),

            # Alternative match for ifconfig if it fails
            (to_find + r'.*ether ' + MAC_RE_COLON,
             0, 'ifconfig', ['']),

            (MAC_RE_COLON,
             0, 'networksetup', ['-getmacaddress %s' % to_find]),
        ]
    elif FREEBSD and type_of_thing in [IP4, IP6, HOSTNAME]:
        methods = [
            (r'\(' + re.escape(to_find) + r'\)\s+at\s+' + MAC_RE_COLON,
             0, 'arp', [to_find])
        ]
    elif OPENBSD and type_of_thing == INTERFACE:
        methods = [
            (r'lladdr ' + MAC_RE_COLON,
             0, 'ifconfig', [to_find]),
        ]
    elif OPENBSD and type_of_thing in [IP4, IP6, HOSTNAME]:
        methods = [
            (re.escape(to_find) + r'[ ]+' + MAC_RE_COLON,
             0, 'arp', ['-an']),
        ]
    elif type_of_thing == INTERFACE:
        methods = [
            _read_sys_iface_file,
            _fcntl_iface,

            # Fast modern Ubuntu ifconfig
            (r'ether ' + MAC_RE_COLON,
             0, 'ifconfig', [to_find]),

            # Fast ifconfig
            (r'HWaddr ' + MAC_RE_COLON,
             0, 'ifconfig', [to_find]),

            # ip link (Don't use 'list' due to SELinux [Android 24+])
            (to_find + r'.*\n.*link/ether ' + MAC_RE_COLON,
             0, 'ip', ['link %s' % to_find, 'link']),

            # netstat
            (to_find + r'.*HWaddr ' + MAC_RE_COLON,
             0, 'netstat', ['-iae']),

            # More variations of ifconfig
            (to_find + r'.*ether ' + MAC_RE_COLON,
             0, 'ifconfig', ['']),
            (to_find + r'.*HWaddr ' + MAC_RE_COLON,
             0, 'ifconfig', ['', '-a', '-v']),

            # Tru64 ('-av')
            (to_find + r'.*Ether ' + MAC_RE_COLON,
             0, 'ifconfig', ['-av']),
            _uuid_lanscan_iface,
        ]
    elif type_of_thing in [IP4, IP6, HOSTNAME]:
        esc = re.escape(to_find)
        methods = [
            _read_arp_file,
            lambda x: _popen('ip', 'neighbor show %s' % x)
            .partition(x)[2].partition('lladdr')[2].strip().split()[0],

            (r'\(' + esc + r'\)\s+at\s+' + MAC_RE_COLON,
             0, 'arp', [to_find, '-an', '-an %s' % to_find]),

            # Darwin oddness
            (r'\(' + esc + r'\)\s+at\s+' + MAC_RE_DARWIN,
             0, 'arp', [to_find, '-a', '-a %s' % to_find]),
            _uuid_ip,
        ]
    else:
        log.critical("Reached end of _hunt_for_mac() if-else chain!")
        return None
    return _try_methods(methods, to_find)


def _try_methods(methods, to_find=None):
    # type: (list, Optional[str]) -> Optional[str]
    """Runs the methods specified by _hunt_for_mac().
    We try every method and see if it returned a MAC address. If it returns
    None or raises an exception, we continue and try the next method.
    """
    found = None
    for m in methods:
        try:
            if isinstance(m, tuple):
                for arg in m[3]:  # list(str)
                    if DEBUG:
                        log.debug("Trying: '%s %s'", m[2], arg)
                    # Arguments: (regex, _popen(command, arg), regex index)
                    found = _search(m[0], _popen(m[2], arg), m[1])
                    if DEBUG:
                        log.debug("Result: %s\n", found)
                    if found:  # Skip remaining args AND remaining methods
                        break
            elif callable(m):
                if DEBUG:
                    log.debug("Trying: '%s' (to_find: '%s')", m.__name__, str(to_find))
                if to_find is not None:
                    found = m(to_find)
                else:
                    found = m()
                if DEBUG:
                    log.debug("Result: %s\n", found)
            else:
                log.critical("Invalid type '%s' for method '%s'", type(m), str(m))
        except Exception as ex:
            if DEBUG:
                log.debug("Exception: %s", str(ex))
            if DEBUG >= 2:
                log.debug(traceback.format_exc())
            continue
        if found:  # Skip remaining methods
            break
    return found


def _get_default_iface_linux():
    # type: () -> Optional[str]
    """Get the default interface by reading /proc/net/route.
    This is the same source as the `route` command, however it's much
    faster to read this file than to call `route`. If it fails for whatever
    reason, we can fall back on the system commands (e.g for a platform
    that has a route command, but maybe doesn't use /proc?).
    """
    data = _read_file('/proc/net/route')
    if data is not None and len(data) > 1:
        for line in data.split('\n')[1:-1]:
            iface_name, dest = line.split('\t')[:2]
            if dest == '00000000':
                return iface_name
    return None


def _hunt_linux_default_iface():
    # type: () -> Optional[str]
    # NOTE: for now, we check the default interface for WSL using the
    # same methods as POSIX, since those parts of the net stack work fine.
    methods = [
        _get_default_iface_linux,
        lambda: _popen('route', '-n').partition('0.0.0.0')[2].partition('\n')[0].split()[-1],
        lambda: _popen('ip', 'route list 0/0').partition('dev')[2].partition('proto')[0].strip(),
    ]
    return _try_methods(methods)


def _get_default_iface_openbsd():
    # type: () -> Optional[str]
    methods = [
        lambda: _popen('route', '-nq show -inet -gateway -priority 1')
        .partition('127.0.0.1')[0].strip().rpartition(' ')[2],
    ]
    return _try_methods(methods)


def _get_default_iface_freebsd():
    # type: () -> Optional[str]
    methods = [
        (r'default[ ]+\S+[ ]+\S+[ ]+(\S+)\n',
         0, 'netstat', ['-r']),
    ]
    return _try_methods(methods)


def _fetch_ip_using_dns():
    # type: () -> str
    """Determines the IP address of the default network interface.
    Sends a UDP packet to Cloudflare's DNS (1.1.1.1), which should go through
    the default interface. This populates the source address of the socket,
    which we then inspect and return.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('1.1.1.1', 53))
    ip = s.getsockname()[0]
    s.close()  # NOTE: sockets don't have context manager in 2.7 :(
    return ip
