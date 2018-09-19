#!/usr/bin/python3
# -*- coding: utf-8 -*-
'''

AceProxy: Ace Stream to HTTP Proxy
Website: https://github.com/pepsik-kiev/HTTPAceProxy

!!!!! Requirements !!!!!

Python2 (>=2.7.10) or Python3 (>=3.4)
gevent >= 1.2.2
psutil >= 5.3.0

'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
# Monkeypatching and all the stuff
from gevent import monkey; monkey.patch_all()

import os, sys, glob
# Uppend the directory for custom modules at the front of the path.
base_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(base_dir, 'modules'))
for wheel in glob.glob(os.path.join(base_dir, 'modules/wheels/') + '*.whl'): sys.path.insert(0, wheel)

import logging, traceback
import psutil
import time
import requests
try: from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except: from http.server import HTTPServer, BaseHTTPRequestHandler
from gevent.baseserver import BaseServer
try: from urlparse import parse_qs
except: from urllib.parse import parse_qs
from ipaddr import IPNetwork, IPAddress
from socket import error as SocketException
from socket import socket, AF_INET, SOCK_DGRAM, SHUT_RDWR
from base64 import b64encode
from modules.PluginInterface import AceProxyPlugin

import aceclient
from aceclient.clientcounter import ClientCounter
import aceconfig
from aceconfig import AceConfig

class GeventHTTPServer(HTTPServer):
    def process_request(self, request, client_address):
        checkAce() # Check is AceStream engine alive
        gevent.spawn(self.process_request_thread, request, client_address)

    def process_request_thread(self, request, client_address):
        try: self.finish_request(request, client_address)
        except SocketException: pass
        except Exception: self.handle_error(request, client_address)
        finally: self.close_request(request)

    def handle_error(self, request, client_address):
        logging.error(traceback.format_exc())
        pass

class HTTPHandler(BaseHTTPRequestHandler):
    server_version = 'HTTPAceProxy'

    def log_message(self, format, *args): pass
        #logger.debug('%s - %s - "%s"' % (self.address_string(), format%args, requests.compat.unquote(self.path).decode('utf8')))
    def log_request(self, code='-', size='-'): pass
        #logger.debug('"%s" %s %s', requests.compat.unquote(self.requestline).decode('utf8'), str(code), str(size))

    def dieWithError(self, errorcode=500, logmsg='Dying with error', loglevel=logging.ERROR):
        '''
        Close connection with error
        '''
        if logmsg: logging.log(loglevel, logmsg)
        if self.connection:
            try:
                self.send_error(errorcode)
                self.end_headers()
            except: pass

    def do_HEAD(self): return self.do_GET(headers_only=True)

    def do_GET(self, headers_only=False):
        '''
        GET request handler
        '''
        if self.request_version == 'HTTP/1.1': self.protocol_version = 'HTTP/1.1'
        logger = logging.getLogger('do_GET')
        # Connected client IP address
        self.clientip = self.headers['X-Forwarded-For'] if 'X-Forwarded-For' in self.headers else self.client_address[0]
        logger.info('Accepted connection from %s path %s' % (self.clientip, requests.compat.unquote(self.path)))
        logger.debug('Headers: %s' % dict(self.headers))

        params = requests.compat.urlparse(self.path)
        self.query, self.path = params.query, params.path[:-1] if params.path.endswith('/') else params.path

        # If firewall enabled
        if AceConfig.firewall and not checkFirewall(self.clientip):
           self.dieWithError(403, 'Dropping connection from %s due to firewall rules' % self.clientip, logging.ERROR)  # 403 Forbidden
           return

        try:
            self.splittedpath = self.path.split('/')
            self.reqtype = self.splittedpath[1].lower()
            # backward compatibility
            old2newUrlParts = {'torrent': 'url', 'pid': 'content_id'}
            if self.reqtype in old2newUrlParts: self.reqtype = old2newUrlParts[self.reqtype]

            # If first parameter is 'content_id','url','infohash' .... etc or it should be handled by plugin
            if not (self.reqtype in ('content_id', 'url', 'infohash', 'direct_url', 'data', 'efile_url') or self.reqtype in AceStuff.pluginshandlers):
                self.dieWithError(400, 'Bad Request', logging.WARNING)  # 400 Bad Request
                return
        except IndexError:
            self.dieWithError(400, 'Bad Request', logging.WARNING)  # 400 Bad Request
            return

        # Handle request with plugin handler
        if self.reqtype in AceStuff.pluginshandlers:
            try: AceStuff.pluginshandlers.get(self.reqtype).handle(self, headers_only)
            except Exception as e:
                self.dieWithError(500, 'Plugin exception: %s' % repr(e))
                logger.error(traceback.format_exc())
            finally: return
        self.handleRequest(headers_only)

    def handleRequest(self, headers_only, channelName=None, channelIcon=None, fmt=None):
        logger = logging.getLogger('HandleRequest')
        self.reqparams, self.path = parse_qs(self.query), self.path[:-1] if self.path.endswith('/') else self.path

        self.videoextdefaults = ('.3gp', '.aac', '.ape', '.asf', '.avi', '.dv', '.divx', '.flac', '.flc', '.flv', '.m2ts', '.m4a', '.mka', '.mkv',
                                 '.mpeg', '.mpeg4', '.mpegts', '.mpg4', '.mp3', '.mp4', '.mpg', '.mov', '.m4v', '.ogg', '.ogm', '.ogv', '.oga',
                                 '.ogx', '.qt', '.rm', '.swf', '.ts', '.vob', '.wmv', '.wav', '.webm')

        # If firewall enabled
        if AceConfig.firewall and not checkFirewall(self.clientip):
           self.dieWithError(403, 'Dropping connection from %s due to firewall rules' % self.clientip, logging.ERROR)  # 403 Forbidden
           return

        # Check if third parameter exists…/self.reqtype/blablablablabla/video.mpg
        #                                                     |_________|
        # And if it ends with regular video extension
        try:
            if not self.path.endswith(self.videoextdefaults):
                self.dieWithError(400, 'Request seems like valid but no valid video extension was provided', logging.ERROR)
                return
        except IndexError: self.dieWithError(400, 'Bad Request', logging.WARNING); return  # 400 Bad Request

        # Limit concurrent connections
        if 0 < AceConfig.maxconns <= AceStuff.clientcounter.total:
            self.dieWithError(503, "Maximum client connections reached, can't serve request from %" % self.clientip, logging.ERROR)  # 503 Service Unavailable
            return

        # Pretend to work fine with Fake or HEAD request.
        if headers_only or AceConfig.isFakeRequest(self.path, self.reqparams, self.headers):
            # Return 200 and exit
            if headers_only: logger.debug('Sending headers and closing connection')
            else: logger.debug('Fake request - closing connection')
            self.send_response(200)
            self.send_header('Content-Type', 'video/mpeg')
            self.send_header('Connection', 'Close')
            self.end_headers()
            return

        # Make dict with parameters
        # [file_indexes, developer_id, affiliate_id, zone_id, stream_id]
        paramsdict = {}.fromkeys(aceclient.acemessages.AceConst.START_PARAMS, '0')
        for i in range(3, len(self.splittedpath)):
            paramsdict[aceclient.acemessages.AceConst.START_PARAMS[i-3]] = self.splittedpath[i] if self.splittedpath[i].isdigit() else '0'
        paramsdict[self.reqtype] = requests.compat.unquote(self.splittedpath[2]) #self.path_unquoted
        #End parameters dict
        self.client = None
        try:
            CID, NAME = self.getINFOHASH(self.reqtype, paramsdict[self.reqtype], paramsdict['file_indexes'])
            if not channelName: channelName = NAME
            if not channelIcon: channelIcon = 'http://static.acestream.net/sites/acestream/img/ACE-logo.png'
            # Create client
            self.client = Client(self, CID, channelName, channelIcon)
            # If there is no existing broadcast we create it
            if AceStuff.clientcounter.add(CID, self.client) == 1:
                logger.warning('Create a broadcast "%s"' % self.client.channelName)
                # Send START commands to AceEngine and Getting URL from engine
                url = self.client.ace.START(self.reqtype, paramsdict, AceConfig.acestreamtype)
                # Rewriting host:port for remote Ace Stream Engine
                if not AceStuff.ace:
                  url = requests.compat.urlparse(url)._replace(netloc='%s:%s' % (AceConfig.ace['aceHostIP'], AceConfig.ace['aceHTTPport'])).geturl()
                # Start streamreader for broadcast
                gevent.spawn(self.client.ace.StreamReader, url, CID, AceStuff.clientcounter)
                logger.warning('Broadcast "%s" created' % self.client.channelName)

        except aceclient.AceException as e: self.dieWithError(500, 'AceClient exception: %s' % repr(e))
        except Exception as e: self.dieWithError(500, 'Unkonwn exception: %s' % repr(e))
        else:
            # streaming to client
            self.client.handle(self.reqparams.get('fmt', [''])[0])
            logger.info('Streaming "%s" to %s finished' % (self.client.channelName, self.clientip))
        finally:
            if self.client and AceStuff.clientcounter.delete(CID, self.client) == 0:
                logger.warning('Broadcast "%s" stoped. Last client disconnected' % self.client.channelName)
        return

    def getINFOHASH(self, reqtype, url, idx):
        if reqtype not in ('direct_url', 'efile_url'):
            if not AceStuff.clientcounter.idleace: AceStuff.clientcounter.idleace = createAce()
            return AceStuff.clientcounter.idleace.GETINFOHASH(reqtype, url, idx)

class Client:

    def __init__(self, handler, cid, channelName, channelIcon):
        self.handler = handler
        self.cid = cid
        self.channelName = channelName
        self.channelIcon = channelIcon
        self.ace = self.queue = None
        self.connectionTime = time.time()

    def handle(self, fmt=None):
        logger = logging.getLogger("ClientHandler")

        if not self.ace._state.wait(timeout=5.0): # STATE 1 (PREBUFFERING)
            self.handler.dieWithError(500, 'Video stream not opened in 5sec - disconnecting')
            return

        self.connectionTime = time.time()

        remaining = self.connectionTime + AceConfig.videostartbuffertime
        while  remaining >= time.time():
           gevent.sleep()
           if self.queue.qsize() >= self.ace._streamReaderQueue.maxsize: break

        # Sending videostream headers to client
        if self.handler.connection:
            response_headers = {'Connection': 'Keep-Alive', 'Keep-Alive': 'timeout=15, max=100', 'Content-Type': 'application/octet-stream', 'Access-Control-Allow-Origin': '*'}
            self.handler.send_response(200)
            logger.debug('Sending HTTPAceProxy headers to client: %s' % response_headers)
            for k,v in list(response_headers.items()): self.handler.send_header(k,v)
            self.handler.end_headers()

        transcoder = None
        out = self.handler.wfile

        if fmt and AceConfig.osplatform != 'Windows':
            if fmt in AceConfig.transcodecmd:
                stderr = None if AceConfig.loglevel == logging.DEBUG else DEVNULL
                popen_params = { 'bufsize': requests.models.CONTENT_CHUNK_SIZE,
                                 'stdin'  : gevent.subprocess.PIPE,
                                 'stdout' : self.handler.wfile,
                                 'stderr' : stderr,
                                 'shell'  : False }

                transcoder = gevent.subprocess.Popen(AceConfig.transcodecmd[fmt], **popen_params)
                out = transcoder.stdin
                logger.warning('Ffmpeg transcoding started')
            else:
                logger.error("Can't found fmt key. Ffmpeg transcoding not started!")

        logger.info('Streaming "%s" to %s started. Start buffer size: %s' % \
                 (self.channelName, self.handler.clientip, AceConfig.bytes2human(self.queue.qsize()*requests.models.CONTENT_CHUNK_SIZE)))

        while self.handler.connection:
            gevent.sleep()
            try: out.write(self.queue.get(timeout=AceConfig.videotimeout))
            except gevent.queue.Empty:
                logger.warning('No data received from StreamReader for %ssec - disconnecting "%s"' % (AceConfig.videotimeout,self.channelName))
                break
            except: break

        if transcoder is not None:
           try: transcoder.kill(); logger.warning('Ffmpeg transcoding stoped')
           except: pass
        self.destroy()
        return

    def destroy(self):
            if self.queue: self.queue.queue.clear()
            if self.handler.connection: self.handler.connection.close()

class AceStuff(object):
    '''
    Inter-class interaction class
    '''
# taken from http://stackoverflow.com/questions/2699907/dropping-root-permissions-in-python
def drop_privileges(uid_name='nobody', gid_name='nogroup'):
    try: import pwd, grp
    except ImportError: return False # Windows

    # Get the uid/gid from the name
    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_uid_home = pwd.getpwnam(uid_name).pw_dir
    running_gid = grp.getgrnam(gid_name).gr_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    old_umask = os.umask(int('077', 8))

    if os.getuid() == running_uid and os.getgid() == running_gid:
        # could be useful
        os.environ['HOME'] = running_uid_home
        logger.info('Changed permissions to: %s: %i, %s, %i' % (uid_name, running_uid, gid_name, running_gid))
        return True
    return False

# Spawning procedures
def spawnAce(cmd, delay=0.1):
    if AceConfig.osplatform == 'Windows':
        try: from _winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
        except: from winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
        reg = ConnectRegistry(None, HKEY_CURRENT_USER)
        try: key = OpenKey(reg, 'Software\AceStream')
        except: logger.error("Can't find acestream!"); sys.exit(1)
        else:
            engine = QueryValueEx(key, 'EnginePath')
            AceStuff.acedir = os.path.dirname(engine[0])
            cmd = engine[0].split()
    try:
        logger.debug('AceEngine starts .....')
        AceStuff.ace = gevent.event.AsyncResult()
        gevent.spawn(lambda: psutil.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)).link(AceStuff.ace)
        AceStuff.ace = AceStuff.ace.get(timeout=delay)
        return isRunning(AceStuff.ace)
    except: return False

def createAce(): # Create telnet connection to the AceEngine API port
    logger.debug('Create connection to AceEngine.....')
    try: ace = aceclient.AceClient(AceConfig.ace, AceConfig.aceconntimeout, AceConfig.aceresulttimeout)
    except:
         logger.error('Ace Stream telnet connection failed'); raise
    else:
         ace.aceInit(AceConfig.acesex, AceConfig.aceage, AceConfig.acekey, AceConfig.videoseekback, AceConfig.videotimeout)
         return ace

def checkAce():
    if AceConfig.acespawn and not isRunning(AceStuff.ace):
        AceStuff.clientcounter.destroyIdle()
        if hasattr(AceStuff, 'ace'): del AceStuff.ace
        if spawnAce(AceStuff.acecmd, AceConfig.acestartuptimeout):
            logger.error('Ace Stream died, respawned it with pid %s' % AceStuff.ace.pid)
            # refresh the acestream.port file for Windows only after full loading...
            if AceConfig.osplatform == 'Windows': detectPort()
            else: gevent.sleep(AceConfig.acestartuptimeout)
        else:
            logger.error("Can't spawn Ace Stream!")

def checkFirewall(clientip):
    try: clientinrange = any([IPAddress(clientip) in IPNetwork(i) for i in AceConfig.firewallnetranges])
    except: logger.error('Check firewall netranges settings !'); return False
    if (AceConfig.firewallblacklistmode and clientinrange) or (not AceConfig.firewallblacklistmode and not clientinrange): return False
    return True

def detectPort():
    try:
        if not isRunning(AceStuff.ace):
            logger.error("Couldn't detect port! Ace Engine is not running?")
            clean_proc(); sys.exit(1)
    except AttributeError:
        logger.error("Ace Engine is not running!")
        clean_proc(); sys.exit(1)
    try: from _winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
    except: from winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
    reg = ConnectRegistry(None, HKEY_CURRENT_USER)
    try: key = OpenKey(reg, 'Software\AceStream')
    except:
           logger.error("Can't find AceStream!")
           clean_proc(); sys.exit(1)
    else:
        engine = QueryValueEx(key, 'EnginePath')
        AceStuff.acedir = os.path.dirname(engine[0])
        try:
            gevent.sleep(AceConfig.acestartuptimeout)
            AceConfig.ace['aceAPIport'] = open(AceStuff.acedir + '\\acestream.port', 'r').read()
            logger.info("Detected ace port: %s" % AceConfig.ace['aceAPIport'])
        except IOError:
            logger.error("Couldn't detect port! acestream.port file doesn't exist?")
            clean_proc(); sys.exit(1)

def isRunning(process):
    return True if process.is_running() and process.status() != psutil.STATUS_ZOMBIE else False

def findProcess(name):
    pinfo = [p.info for p in psutil.process_iter(attrs=['pid', 'name']) if name in p.info['name']]
    return pinfo[0]['pid'] if pinfo else None

def clean_proc():
    # Trying to close all spawned processes gracefully
    if AceConfig.acespawn and isRunning(AceStuff.ace):
        AceStuff.clientcounter.destroyIdle()
        if AceConfig.osplatform == 'Windows' and os.path.isfile(AceStuff.acedir + '\\acestream.port'):
            try: os.remove(AceStuff.acedir + '\\acestream.port')
            except: pass
    import gc
    gevent.killall([obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)])

# This is what we call to stop the server completely
def shutdown(signum=0, frame=0):
    logger.info('Shutdown server.....')
    clean_proc()
    server.shutdown()
    server.server_close()
    logger.info('Bye Bye .....')
    sys.exit()

def _reloadconfig(signum=None, frame=None):
    '''
    Reload configuration file.
    SIGHUP handler.
    '''
    global AceConfig

    logger = logging.getLogger('reloadconfig')
    reload(aceconfig)
    from aceconfig import AceConfig
    #### Initial settings for AceHTTPproxy host IP
    if AceConfig.httphost == 'auto': AceConfig.httphost = get_ip_address()
    logger.info('Ace Stream HTTP Proxy config reloaded.....')

def get_ip_address():
    return [(s.connect(('1.1.1.1', 80)), s.getsockname()[0], s.close()) for s in [socket(AF_INET, SOCK_DGRAM)]][0][1]

def check_compatibility(gevent_version, psutil_version):

    # Check gevent for compatibility.
    major, minor, patch = list(map(int, gevent_version.split('.')[:3]))
    # gevent >= 1.2.2
    assert major == 1
    assert minor >= 2
    assert minor >= 2

    # Check psutil for compatibility.
    major, minor, patch = list(map(int, psutil_version.split('.')[:3]))
    # psutil >= 5.3.0
    assert major == 5
    assert minor >= 3
    assert patch >= 0


logging.basicConfig(level=AceConfig.loglevel, filename=AceConfig.logfile, format=AceConfig.logfmt, datefmt=AceConfig.logdatefmt)
logger = logging.getLogger('HTTPServer')
### Initial settings for devnull
if AceConfig.acespawn or not AceConfig.transcodecmd: DEVNULL = open(os.devnull, 'wb')

logger.info('Ace Stream HTTP Proxy server on Python %s starting .....' % sys.version.split()[0])
logger.debug('Using: gevent %s, psutil %s' % (gevent.__version__, psutil.__version__))

try: check_compatibility(gevent.__version__, psutil.__version__)
except (AssertionError, ValueError):
    logger.error("gevent %s or psutil %s doesn't match a supported version!" % (gevent.__version__, psutil.__version__))
    logger.info('Bye Bye .....')
    sys.exit()

#### Initial settings for AceHTTPproxy host IP
if AceConfig.httphost == 'auto':
    AceConfig.httphost = get_ip_address()
    logger.debug('Ace Stream HTTP Proxy server IP: %s autodetected' % AceConfig.httphost)

# Check whether we can bind to the defined port safely
if AceConfig.osplatform != 'Windows' and os.getuid() != 0 and AceConfig.httpport <= 1024:
    logger.error('Cannot bind to port %s without root privileges' % AceConfig.httpport)
    sys.exit(1)

# Dropping root privileges if needed
if AceConfig.osplatform != 'Windows' and AceConfig.aceproxyuser and os.getuid() == 0:
    if drop_privileges(AceConfig.aceproxyuser):
        logger.info('Dropped privileges to user %s' % AceConfig.aceproxyuser)
    else:
        logger.error('Cannot drop privileges to user %s' % AceConfig.aceproxyuser)
        sys.exit(1)

# setting signal handlers
try:
    gevent.signal(gevent.signal.SIGHUP, _reloadconfig)
    gevent.signal(gevent.signal.SIGTERM or gevent.signal.SIGINT, shutdown)
except AttributeError: pass  # not available on Windows

# Creating ClientCounter
AceStuff.clientcounter = ClientCounter()

#### AceEngine startup
AceStuff.ace = findProcess('ace_engine.exe' if AceConfig.osplatform == 'Windows' else os.path.basename(AceConfig.acecmd))
if not AceStuff.ace and AceConfig.acespawn:
   AceStuff.acecmd = '' if AceConfig.osplatform == 'Windows' else AceConfig.acecmd.split()
   if spawnAce(AceStuff.acecmd, AceConfig.acestartuptimeout):
       logger.info('Local AceStream engine spawned with pid %s' % AceStuff.ace.pid)
elif AceStuff.ace:
   AceStuff.ace = psutil.Process(AceStuff.ace)
   logger.info('Local AceStream engine found with pid %s' % AceStuff.ace.pid)

# If AceEngine started (found) localy
if AceStuff.ace:
    AceConfig.ace['aceHostIP'] = '127.0.0.1'
    # Refreshes the acestream.port file for OS Windows.....
    if AceConfig.osplatform == 'Windows': detectPort()
    else: gevent.sleep(AceConfig.acestartuptimeout)
else:
    try:
       url = 'http://%s:%s/webui/api/service' % (AceConfig.ace['aceHostIP'], AceConfig.ace['aceHTTPport'])
       params = {'method': 'get_version', 'format': 'json', 'callback': 'mycallback'}
       version = requests.get(url, params=params, timeout=5).json()['result']['version']
       logger.info('Remote AceStream engine ver.%s will be used on %s:%s' % (version, AceConfig.ace['aceHostIP'], AceConfig.ace['aceAPIport']))
    except: logger.error('AceStream not found!')

# Loading plugins
# Trying to change dir (would fail in freezed state)
try: os.chdir(os.path.dirname(os.path.realpath(__file__)))
except: pass
# Creating dict of handlers
AceStuff.pluginshandlers = {}
# And a list with plugin instances
AceStuff.pluginlist = list()
sys.path.insert(0, 'plugins')
logger.info("Load Ace Stream HTTP Proxy plugins .....")
for i in [os.path.splitext(os.path.basename(x))[0] for x in glob.glob('plugins/*_plugin.py')]:
    plugin = __import__(i)
    plugname = i.split('_')[0].capitalize()
    try: plugininstance = getattr(plugin, plugname)(AceConfig, AceStuff)
    except Exception as e:
        logger.error("Cannot load plugin %s: %s" % (plugname, repr(e)))
        continue
    logger.debug('Plugin loaded: %s' % plugname)
    for j in plugininstance.handlers: AceStuff.pluginshandlers[j] = plugininstance
    AceStuff.pluginlist.append(plugininstance)

# Start complite. Wating for requests
server = GeventHTTPServer((AceConfig.httphost, AceConfig.httpport), HTTPHandler)
logger.info('Server started at %s:%s Use <Ctrl-C> to stop' % (AceConfig.httphost, AceConfig.httpport))
try: server.serve_forever()
except (KeyboardInterrupt, SystemExit): shutdown()
