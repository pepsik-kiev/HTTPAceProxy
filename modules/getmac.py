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

from __future__ import print_function

import ctypes
import os
import platform
import re
import shlex
import socket
import struct
import sys
import traceback
from subprocess import check_output

try:
    from subprocess import DEVNULL  # Py3
except ImportError:
    DEVNULL = open(os.devnull, 'wb')  # Py2

__version__ = '0.6.0'
DEBUG = 0
PORT = 55555

PY2 = sys.version_info[0] == 2
_SYST = platform.system()
WINDOWS = False
OSX = False
LINUX = False
BSD = False
POSIX = False
WSL = False

if _SYST == 'Linux':
    if 'Microsoft' in platform.version():
        WSL = True
    else:
        LINUX = True
elif _SYST == 'Windows':
    WINDOWS = True
elif _SYST == 'Darwin':
    OSX = True
elif _SYST == 'Java':
    WINDOWS = os.sep == '\\'

PATH = os.environ.get('PATH', os.defpath).split(os.pathsep)
if not WINDOWS:
    PATH.extend(('/sbin', '/usr/sbin'))

ENV = dict(os.environ)
ENV['LC_ALL'] = 'C'  # Ensure ASCII output so we parse correctly

IP4 = 0
IP6 = 1
INTERFACE = 2
HOSTNAME = 3

MAC_RE_COLON = r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})'
MAC_RE_DASH = r'([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})'
MAC_RE_DARWIN = r'([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})'

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
    # type: (str, str, str, str, bool) -> Optional[str]
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
        try:
            if ip:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(b'', (ip, PORT))
            else:
                s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
                s.sendto(b'', (ip6, PORT))
        except Exception:
            if DEBUG:
                print("ERROR: Failed to send ARP table population packet")
            if DEBUG >= 2:
                traceback.print_exc()

    # Setup the address hunt based on the arguments specified
    if ip6:
        if not socket.has_ipv6:
            _warn("Cannot get the MAC address of a IPv6 host: "
                  "IPv6 is not supported on this system")
            return None
        elif ':' not in ip6:
            _warn("Invalid IPv6 address: %s" % ip6)
            return None
        to_find = ip6
        typ = IP6
    elif ip:
        to_find = ip
        typ = IP4
    else:
        typ = INTERFACE
        if interface:
            to_find = interface
        else:
            # Default to finding MAC of the interface with the default route
            if WINDOWS:
                if network_request:
                    to_find = _fetch_ip_using_dns()
                    typ = IP4
                else:
                    to_find = 'Ethernet'
            else:
                to_find = _hunt_linux_default_iface()
                if not to_find:
                    to_find = 'en0'

    mac = _hunt_for_mac(to_find, typ, network_request)
    if DEBUG:
        print("Raw MAC found: %s" % mac)

    # Check and format the result to be lowercase, colon-separated
    if mac is not None:
        mac = str(mac)
        if not PY2:  # Strip bytestring conversion artifacts
            mac = mac.replace("b'", '').replace("'", '')\
                     .replace('\\n', '').replace('\\r', '')
        mac = mac.strip().lower().replace(' ', '').replace('-', ':')

        # Fix cases where there are no colons
        if ':' not in mac and len(mac) == 12:
            if DEBUG:
                print("Adding colons to MAC %s" % mac)
            mac = ':'.join(mac[i:i + 2] for i in range(0, len(mac), 2))

        # Pad single-character octets with a leading zero (e.g Darwin's ARP output)
        elif len(mac) < 17:
            if DEBUG:
                print("Length of MAC %s is %d, padding single-character "
                      "octets with zeros" % (mac, len(mac)))
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
            if DEBUG:
                print("ERROR: MAC %s is not 17 characters long!" % mac)
            mac = None
    return mac


def _warn(text):
    # type: (str) -> None
    import warnings
    warnings.warn(text, RuntimeWarning)


def _search(regex, text, group_index=0):
    # type: (str, str, int) -> str
    match = re.search(regex, text)
    if match:
        return match.groups()[group_index]


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
        print("Running: '%s %s'" % (executable, args))
    return _call_proc(executable, args)


def _call_proc(executable, args):
    # type: (str, str) -> str
    if WINDOWS:
        cmd = executable + ' ' + args
    else:
        cmd = [executable] + shlex.split(args)
    output = check_output(cmd, stderr=DEVNULL, env=ENV)
    if not PY2 and isinstance(output, bytes):
        return str(output, 'utf-8')
    else:
        return str(output)


def _windows_ctypes_host(host):
    # type: (str) -> Optional[str]
    if not PY2:  # Convert to bytes on Python 3+ (Fixes GitHub issue #7)
        host = host.encode()
    try:
        inetaddr = ctypes.windll.wsock32.inet_addr(host)
        if inetaddr in (0, -1):
            raise Exception
    except Exception:
        hostip = socket.gethostbyname(host)
        inetaddr = ctypes.windll.wsock32.inet_addr(hostip)

    buffer = ctypes.c_buffer(6)
    addlen = ctypes.c_ulong(ctypes.sizeof(buffer))

    send_arp = ctypes.windll.Iphlpapi.SendARP
    if send_arp(inetaddr, 0, ctypes.byref(buffer), ctypes.byref(addlen)) != 0:
        return None

    # Convert binary data into a string.
    macaddr = ''
    for intval in struct.unpack('BBBBBB', buffer):
        if intval > 15:
            replacestr = '0x'
        else:
            replacestr = 'x'
        macaddr = ''.join([macaddr, hex(intval).replace(replacestr, '')])
    return macaddr


def _fcntl_iface(iface):
    # type: (str) -> str
    import fcntl
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 0x8927 = SIOCGIFADDR
    info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', iface[:15]))
    return ':'.join(['%02x' % ord(char) for char in info[18:24]])


def _uuid_ip(ip):
    # type: (str) -> Optional[str]
    from uuid import _arp_getnode
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


def _uuid_lanscan_iface(iface):
    # type: (str) -> Optional[str]
    if not PY2:
        iface = bytes(iface)
    mac = __import__('uuid')._find_mac('lanscan', '-ai', [iface], lambda i: 0)
    if mac:
        return _uuid_convert(mac)


def _uuid_convert(mac):
    # type: (str) -> str
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


def _read_file(filepath):
    # type: (str) -> Optional[str]
    try:
        with open(filepath) as f:
            return f.read()
    except OSError:
        if DEBUG:
            print("Could not find file: '%s'" % filepath)
        return None


def _hunt_for_mac(to_find, type_of_thing, net_ok=True):
    # type: (str, int, bool) -> Optional[str]
    """Tries a variety of methods to get a MAC address.
    Format of method lists:
    Tuple:  (regex, regex index, command, command args)
            Command args is a list of strings to attempt to use as arguments
    lambda: Function to call
    """
    if not PY2 and isinstance(to_find, bytes):
        to_find = str(to_find, 'utf-8')

    # Windows - Network Interface
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

    # Windows - Remote Host
    elif (WINDOWS or WSL) and type_of_thing in [IP4, IP6, HOSTNAME]:
        methods = [
            # arp -a - Parsing result with a regex
            (MAC_RE_DASH, 0, 'arp.exe', ['-a %s' % to_find]),
        ]

        # Add methods that make network requests
        # Insert it *after* arp.exe since that's probably faster.
        if net_ok and type_of_thing != IP6 and not WSL:
            methods.insert(1, _windows_ctypes_host)

    # Non-Windows - Network Interface
    elif type_of_thing == INTERFACE:
        if OSX:
            methods = [
                # ifconfig for OSX
                (r'ether ' + MAC_RE_COLON,
                 0, 'ifconfig', [to_find]),

                # Alternative match for ifconfig if it fails
                (to_find + r'.*(ether) ' + MAC_RE_COLON,
                 1, 'ifconfig', ['']),

                # networksetup
                (MAC_RE_COLON,
                 0, 'networksetup', ['-getmacaddress %s' % to_find]),
            ]
        else:
            methods = [
                _read_sys_iface_file,

                _fcntl_iface,

                # Fast ifconfig
                (r'HWaddr ' + MAC_RE_COLON,
                 0, 'ifconfig', [to_find]),

                # ip link (Don't use 'list' due to SELinux [Android 24+])
                (to_find + r'.*\n.*link/ether ' + MAC_RE_COLON,
                 0, 'ip', ['link %s' % to_find, 'link']),

                # netstat
                (to_find + r'.*(HWaddr) ' + MAC_RE_COLON,
                 1, 'netstat', ['-iae']),

                # More variations of ifconfig
                (to_find + r'.*(HWaddr) ' + MAC_RE_COLON,
                 1, 'ifconfig', ['', '-a', '-v']),

                # Tru64 ('-av')
                (to_find + r'.*(Ether) ' + MAC_RE_COLON,
                 1, 'ifconfig', ['-av']),
                _uuid_lanscan_iface,
            ]

    # Non-Windows - Remote Host
    elif type_of_thing in [IP4, IP6, HOSTNAME]:
        esc = re.escape(to_find)
        methods = [
            _read_arp_file,

            lambda x: _popen('ip', 'neighbor show %s' % x)
            .partition(x)[2].partition('lladdr')[2].strip().split()[0],

            # -a: BSD-style format
            # -n: shows numerical addresses
            (r'\(' + esc + r'\)\s+at\s+' + MAC_RE_COLON,
             0, 'arp', [to_find, '-an', '-an %s' % to_find]),

            # Darwin (OSX) oddness
            (r'\(' + esc + r'\)\s+at\s+' + MAC_RE_DARWIN,
             0, 'arp', [to_find, '-a', '-a %s' % to_find]),

            _uuid_ip,
        ]
    else:
        _warn("ERROR: reached end of _hunt_for_mac() if-else chain!")
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
                        print("Trying: '%s %s'" % (m[2], arg))
                    # Arguments: (regex, _popen(command, arg), regex index)
                    found = _search(m[0], _popen(m[2], arg), m[1])
                    if DEBUG:
                        print("Result: %s\n" % found)
            elif callable(m):
                if DEBUG:
                    print("Trying: '%s' (to_find: '%s')" % (m.__name__, str(to_find)))
                if to_find is not None:
                    found = m(to_find)
                else:
                    found = m()
                if DEBUG:
                    print("Result: %s\n" % found)
        except Exception as ex:
            if DEBUG:
                print("Exception: %s" % str(ex))
            if DEBUG >= 2:
                traceback.print_exc()
            continue
        if found:
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
        data = data.split('\n')[1:-1]
        for line in data:
            iface_name, dest = line.split('\t')[:2]
            if dest == '00000000':
                return iface_name


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
    s.close()
    return ip
