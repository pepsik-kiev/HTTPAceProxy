#!/usr/bin/python2
# -*- coding: utf-8 -*-
'''
AceProxy: Ace Stream to HTTP Proxy
Website: https://github.com/pepsik-kiev/HTTPAceProxy
'''
import gevent
# Monkeypatching and all the stuff
from gevent import monkey; monkey.patch_all()

import os, sys
# Uppend the directory for custom modules at the front of the path.
base_dir = os.path.dirname(os.path.realpath(__file__))
wheels_dir = os.path.join(base_dir, 'modules/wheels')
wheels_list = filter(lambda x: x.endswith('.whl'), os.listdir(wheels_dir))
for filename in wheels_list: sys.path.insert(0, wheels_dir + '/' + filename)

modules_dir = os.path.join(base_dir, 'modules')
sys.path.insert(0, modules_dir)

import aceclient
import aceconfig
from aceconfig import AceConfig
from aceclient.clientcounter import ClientCounter
import traceback
import glob
import signal
import logging
import psutil
from subprocess import PIPE
from socket import error as SocketException
from socket import SHUT_RDWR, socket, AF_INET, SOCK_DGRAM
from collections import deque
from base64 import b64encode
from itertools import izip as zip
import time
import threading
import requests
import Queue
from bencode import __version__ as bencode_version__
import ipaddr
from urlparse import parse_qs
import BaseHTTPServer, SocketServer
from modules.PluginInterface import AceProxyPlugin
from concurrent.futures import ThreadPoolExecutor

class ThreadPoolMixIn(SocketServer.ThreadingMixIn):
    allow_reuse_address = daemon_threads = True
    requestlist = []

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
            self.close_request(request)
        except SocketException: pass
        except Exception:
            self.handle_error(request, client_address)
            self.close_request(request)
        finally: self.requestlist.remove(request)

    def process_request(self, request, client_address):
        self.requestlist.append(request)
        self.pool.submit(self.process_request_thread, request, client_address)

    def handle_error(self, request, client_address):
        logging.debug(traceback.format_exc())
        pass


class ThreadedPoolHTTPServer(ThreadPoolMixIn, BaseHTTPServer.HTTPServer):
    """
    Handle requests in a pool of separate threads.
    """
    # default threads value if max_workers=None - cpu_num() * 5 for custom value max_workers=N
    pool = ThreadPoolExecutor(max_workers=AceConfig.maxconns, thread_name_prefix='PoolHTTPServerThread')

class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def log_message(self, format, *args): pass
        #logger.debug('%s - %s - "%s"' % (self.address_string(), format%args, requests.utils.unquote(self.path).decode('utf8')))
    def log_request(self, code='-', size='-'): pass
        #logger.debug('"%s" %s %s', requests.utils.unquote(self.requestline).decode('utf8'), str(code), str(size))

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
        logger = logging.getLogger('do_GET')
        if self.request_version == 'HTTP/1.1': self.protocol_version = 'HTTP/1.1'

        # Connected client IP address
        self.clientip = self.headers['X-Forwarded-For'] if 'X-Forwarded-For' in self.headers else self.request.getpeername()[0]
        logger.info("Accepted connection from %s path %s" % (self.clientip, requests.utils.unquote(self.path)))
        logger.debug("Headers: %s" % self.headers.dict)

        # If firewall enabled
        if AceConfig.firewall and not checkFirewall(self.clientip):
           self.dieWithError(403, 'Dropping connection from %s due to firewall rules' % self.clientip, logging.ERROR)  # 403 Forbidden
           return

        try:
            self.splittedpath = self.path.split('/')
            self.reqtype = self.splittedpath[1].lower()
            # If first parameter is 'content_id','url','infohash' .... etc or it should be handled
            # by plugin
            if not (self.reqtype in ('content_id','url','infohash','direct_url','data','efile_url') or self.reqtype in AceStuff.pluginshandlers):
                self.dieWithError(400, 'Bad Request', logging.WARNING)  # 400 Bad Request
                return
        except IndexError:
            self.dieWithError(400, 'Bad Request', logging.WARNING)  # 400 Bad Request
            return

        # Handle request with plugin handler
        if self.reqtype in AceStuff.pluginshandlers:
            try: AceStuff.pluginshandlers.get(self.reqtype).handle(self, headers_only)
            except Exception as e: self.dieWithError(500, 'Plugin exception: %s' % repr(e))
                #logger.error(traceback.format_exc())
            finally: return

        self.handleRequest(headers_only)

    def handleRequest(self, headers_only, channelName=None, channelIcon=None, fmt=None):
        logger = logging.getLogger('HandleRequest')
        self.requrl = requests.utils.urlparse(self.path)
        self.reqparams = parse_qs(self.requrl.query)
        self.path = self.requrl.path[:-1] if self.requrl.path.endswith('/') else self.requrl.path
        self.videoextdefaults = ('.3gp','.aac','.ape','.asf','.avi','.dv','.divx','.flac','.flc','.flv','.m2ts','.m4a','.mka','.mkv',
                                 '.mpeg','.mpeg4','.mpegts','.mpg4','.mp3','.mp4','.mpg','.mov','.m4v','.ogg','.ogm','.ogv','.oga',
                                 '.ogx','.qt','.rm','.swf','.ts','.vob','.wmv','.wav','.webm')

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
            self.dieWithError(503, "Maximum client connections reached, can't serve this", logging.ERROR)  # 503 Service Unavailable
            return

        # Pretend to work fine with Fake or HEAD request.
        if headers_only or AceConfig.isFakeRequest(self.path, self.reqparams, self.headers):
            # Return 200 and exit
            if headers_only: logger.debug("Sending headers and closing connection")
            else: logger.debug("Fake request - closing connection")
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
            self.send_header("Connection", "Close")
            self.end_headers()
            return

        # Check is AceStream engine alive before start streaming
        if self.connection: checkAce()

        # Make dict with parameters
        # [file_indexes, developer_id, affiliate_id, zone_id, stream_id]
        paramsdict = dict()
        for i in xrange(3, 8):
            try: paramsdict.update({aceclient.acemessages.AceConst.START_PARAMS[i-3]: int(self.splittedpath[i])})
            except (IndexError, ValueError): paramsdict.update({aceclient.acemessages.AceConst.START_PARAMS[i-3]: '0'})
        paramsdict[self.reqtype] = requests.utils.unquote(self.splittedpath[2]) #self.path_unquoted
        #End parameters dict

        content_id = self.getCID(self.reqtype, paramsdict[self.reqtype])
        CID = content_id if content_id else paramsdict[self.reqtype]
        if not channelName and self.reqtype in ('content_id', 'url', 'infohash'):
           try:
               if not AceConfig.acehost: AceConfig.acehost, AceConfig.aceHTTPport = AceConfig.acehostslist[0][0], AceConfig.acehostslist[0][2]
               headers = {'User-Agent': 'Python-urllib/2.7','Content-Type': 'application/octet-stream', 'Connection': 'close'}
               url = 'http://%s:%s/server/api' % (AceConfig.acehost, AceConfig.aceHTTPport)
               params = {'method': 'get_media_files', self.reqtype: paramsdict[self.reqtype]}
               channelName = requests.get(url, headers=headers, params=params, timeout=5).json()['result'][str(paramsdict['file_indexes'])]
           except: channelName = CID
        if not channelIcon: channelIcon = 'http://static.acestream.net/sites/acestream/img/ACE-logo.png'
        # Create client
        self.client = Client(CID, self, channelName, channelIcon)

        try:
            # If there is no existing broadcast we create it
            if AceStuff.clientcounter.add(CID, self.client) == 1:
                logger.warning('Create a broadcast "%s"' % self.client.channelName)
                # Send START commands to AceEngine
                self.client.ace.START(self.reqtype, paramsdict, AceConfig.streamtype)
                # Getting URL from engine
                self.url = self.client.ace.getUrl(AceConfig.videotimeout*2) if self.reqtype in ('infohash', 'url', 'data') else self.client.ace.getUrl(AceConfig.videotimeout)
                # Rewriting host:port for remote Ace Stream Engine
                p = requests.utils.urlparse(self.url)._replace(netloc=AceConfig.acehost+':'+str(AceConfig.aceHTTPport))
                self.url = requests.utils.urlunparse(p)
                # Start streamreader for broadcast
                gevent.spawn(self.client.ace.startStreamReader, self.url, CID, AceStuff.clientcounter, self.headers.dict)
                gevent.sleep()
                logger.warning('Broadcast "%s" created' % self.client.channelName)

        except aceclient.AceException as e: self.dieWithError(500, 'AceClient exception: %s' % repr(e))
        except Exception as e: self.dieWithError(500, 'Unkonwn exception: %s' % repr(e))
        else:
               if not fmt: fmt = self.reqparams.get('fmt')[0] if 'fmt' in self.reqparams else None
               # streaming to client
               logger.info('Streaming "%s" to %s started' % (self.client.channelName, self.clientip))
               self.client.handle(fmt)
               logger.info('Streaming "%s" to %s finished' % (self.client.channelName, self.clientip))
        finally:
              if AceStuff.clientcounter.delete(CID, self.client) == 0:
                 logger.warning('Broadcast "%s" stoped. Last client disconnected' % self.client.channelName)
              self.client.destroy()
              return

    def getCID(self, reqtype, url):
        cid = None
        if reqtype == 'url' and url.endswith(('.acelive', '.acestream', '.acemedia' ,'.torrent')):
            try:
                headers={'User-Agent': 'VLC/2.0.5 LibVLC/2.0.5','Range': 'bytes=0-','Connection': 'close','Icy-MetaData': '1'}
                with requests.get(url, headers=headers, stream = True, timeout=5) as r:
                   headers={'User-Agent': 'Python-urllib/2.7','Content-Type': 'application/octet-stream', 'Connection': 'close'}
                   cid = requests.post('http://api.torrentstream.net/upload/raw', data=b64encode(r.raw.read()), headers=headers, timeout=5).json()['content_id']
            except: pass
            if not cid:
                logging.debug("Failed to get ContentID from WEB API")
                try:
                    with AceStuff.clientcounter.lock:
                        if not AceStuff.clientcounter.idleace: AceStuff.clientcounter.idleace = AceStuff.clientcounter.createAce()
                        cid = AceStuff.clientcounter.idleace.GETCID(reqtype, url)
                except: logging.error("Failed to get Infohash from engine")

        return None if not cid else cid

class Client:

    def __init__(self, cid, handler, channelName, channelIcon):
        self.cid = cid
        self.handler = handler
        self.channelName = channelName
        self.channelIcon = channelIcon
        self.ace = None
        self.lock = threading.Condition(threading.Lock())
        self.connectionTime = time.time()
        self.queue = deque()

    def handle(self, fmt=None):
        logger = logging.getLogger("ClientHandler")
        self.connectionTime = time.time()

        with self.ace._lock:
            start = time.time()
            while self.handler.connection and self.ace._streamReaderState == 1:
                remaining = start + 5.0 - time.time()
                if remaining > 0:
                    self.ace._lock.wait(remaining)
                else:
                    self.handler.dieWithError(500, 'Video stream not opened in 5 seconds - disconnecting')
                    return
            if self.handler.connection and self.ace._streamReaderState != 2:
                self.handler.dieWithError(500, 'No video stream found', logging.WARNING)
                return

        # Sending client headers to videostream
        if self.handler.connection:
            self.handler.send_response(self.ace._streamReaderConnection.status_code)
            FORWARD_HEADERS = ['Connection',
                               'Keep-Alive',
                               'Content-Range',
                               'Content-Type',
                               'X-Content-Duration',
                               'Content-Length',
                               ]
            SKIP_HEADERS = ['Server', 'Date', 'Transfer-Encoding', 'Accept-Ranges']
            response_headers={}
            for k in self.ace._streamReaderConnection.headers:
                if k.split(':')[0] not in (FORWARD_HEADERS + SKIP_HEADERS):
                    logger.error('NEW HEADERS FOUND: %s' % k.split(':')[0])
            for h in FORWARD_HEADERS:
                if self.ace._streamReaderConnection.headers.get(h):
                    response_headers[h] = self.ace._streamReaderConnection.headers.get(h)
                    self.handler.send_header(h, response_headers[h])
            self.handler.end_headers()
            logger.debug('Sending HTTPAceProxy headers to client: %s' % response_headers)

        if AceConfig.transcode and AceConfig.osplatform != 'Windows':
            if not fmt or not fmt in AceConfig.transcodecmd: fmt = 'default'
            if fmt in AceConfig.transcodecmd:
                stderr = None if AceConfig.loglevel == logging.DEBUG else DEVNULL
                popen_params = { "bufsize": AceConfig.readchunksize,
                                 "stdin"  : PIPE,
                                 "stdout" : self.handler.wfile,
                                 "stderr" : stderr,
                                 "shell"  : False }

                transcoder = psutil.Popen(AceConfig.transcodecmd[fmt], **popen_params)
                out = transcoder.stdin
                logger.warning("Ffmpeg transcoding started")
            else:
                transcoder = None
                out = self.handler.wfile
        else:
            transcoder = None
            out = self.handler.wfile
        try:
            while self.handler.connection:
                try:
                    data = self.getChunk(60.0)
                    try: out.write(data)
                    except: break
                except Queue.Empty: logger.warning("No data received in 60 seconds - disconnecting"); break
        finally:
            if transcoder:
               try: transcoder.kill(); logger.warning("Ffmpeg transcoding stoped")
               except: pass
            return

    def addChunk(self, chunk, timeout):
        start = time.time()
        with self.lock:
            while(self.handler.connection and (len(self.queue) == AceConfig.readcachesize)):
                remaining = start + timeout + time.time()
                if remaining > 0:
                    self.lock.wait(remaining)
                else: raise Queue.Full
            if self.handler.connection:
                self.queue.append(chunk)
                self.lock.notifyAll()

    def getChunk(self, timeout):
        start = time.time()
        with self.lock:
            while(self.handler.connection and (len(self.queue) == 0)):
                remaining = start + timeout - time.time()
                if remaining > 0:
                    self.lock.wait(remaining)
                else: raise Queue.Empty
            if self.handler.connection:
                chunk = self.queue.popleft()
                self.lock.notifyAll()
                return chunk
            else: return None

    def destroy(self):
        with self.lock:
             self.queue.clear()
             self.lock.notifyAll()

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
    old_umask = os.umask(077)

    if os.getuid() == running_uid and os.getgid() == running_gid:
        # could be useful
        os.environ['HOME'] = running_uid_home
        return True
    return False

# Spawning procedures
def spawnAce(cmd, delay=0.1):
    if AceConfig.osplatform == 'Windows':
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        try:
            key = _winreg.OpenKey(reg, 'Software\AceStream')
        except:
            logger.error("Can't find acestream!")
            sys.exit(1)
        else:
            engine = _winreg.QueryValueEx(key, 'EnginePath')
            AceStuff.acedir = os.path.dirname(engine[0])
            cmd = engine[0].split()
    try:
        AceStuff.ace = psutil.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        gevent.sleep(delay)
        return True
    except: return False

def checkFirewall(clientip):
    clientinrange = any(map(lambda i: ipaddr.IPAddress(clientip) in ipaddr.IPNetwork(i), AceConfig.firewallnetranges))
    if (AceConfig.firewallblacklistmode and clientinrange) or (not AceConfig.firewallblacklistmode and not clientinrange): return False
    return True

def checkAce():
    if AceConfig.acespawn and not isRunning(AceStuff.ace):
        AceStuff.clientcounter.destroyIdle()
        if hasattr(AceStuff, 'ace'): del AceStuff.ace
        if spawnAce(AceStuff.aceProc, 1):
            logger.error("Ace Stream died, respawned it with pid %s" % AceStuff.ace.pid)
            # Wait some time for ace engine sturtup .....
            gevent.sleep(AceConfig.acestartuptimeout)
            # refresh the acestream.port file for Windows only after full loading...
            if AceConfig.osplatform == 'Windows': detectPort()
        else:
            logger.error("Can't spawn Ace Stream!")
            clean_proc()
            sys.exit(1)

def detectPort():
    try:
        if not isRunning(AceStuff.ace):
            logger.error("Couldn't detect port! Ace Engine is not running?")
            clean_proc()
            sys.exit(1)
    except AttributeError:
        logger.error("Ace Engine is not running!")
        clean_proc()
        sys.exit(1)
    import _winreg
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    try:
        key = _winreg.OpenKey(reg, 'Software\AceStream')
    except:
        logger.error("Can't find AceStream!")
        sys.exit(1)
    else:
        engine = _winreg.QueryValueEx(key, 'EnginePath')
        AceStuff.acedir = os.path.dirname(engine[0])
    try:
        AceConfig.acehostslist[0][1] = int(open(AceStuff.acedir + '\\acestream.port', 'r').read())
        logger.info("Detected ace port: %s" % AceConfig.acehostslist[0][1])
    except IOError:
        logger.error("Couldn't detect port! acestream.port file doesn't exist?")
        clean_proc()
        sys.exit(1)

def isRunning(process):
    if psutil.version_info[0] >= 2:
        if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
            return True
    else:  # for older versions of psutil
        if process.is_running() and process.status != psutil.STATUS_ZOMBIE:
            return True
    return False

def findProcess(name):
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name'])
            if pinfo['name'] == name:
                return pinfo['pid']
        except psutil.AccessDenied: pass # System process
        except psutil.NoSuchProcess: pass # Process terminated
    return None

def clean_proc():
    # Trying to close all spawned processes gracefully
    if AceConfig.acespawn and isRunning(AceStuff.ace):
        logger.info('AceStream terminate.....')
        with AceStuff.clientcounter.lock:
            if AceStuff.clientcounter.idleace: AceStuff.clientcounter.idleace.destroy()
            gevent.sleep(1)
        AceStuff.ace.terminate()
        gevent.sleep(1)
        if isRunning(AceStuff.ace): AceStuff.ace.kill(); logger.warning('AceStream kill.....')
        # for windows, subprocess.terminate() is just an alias for kill(), so we have to delete the acestream port file manually
        if AceConfig.osplatform == 'Windows' and os.path.isfile(AceStuff.acedir + '\\acestream.port'):
            try: os.remove(AceStuff.acedir + '\\acestream.port')
            except: pass

# This is what we call to stop the server completely
def shutdown(signum=0, frame=0):
    logger.info('Shutdown server.....')
    for connection in server.requestlist:
        try: logger.debug("Kill a connection from %s" % connection.getpeername()[0]); connection.shutdown(SHUT_RDWR)
        except: logger.warning("Cannot kill a connection from %s" % connection.getpeername()[0])
    clean_proc()
    server.pool.shutdown()
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
    logger.info('Ace Stream HTTP Proxy config reloaded')

logging.basicConfig(level=AceConfig.loglevel, filename=AceConfig.logfile,
                    format=AceConfig.logfmt, datefmt=AceConfig.logdatefmt)
logger = logging.getLogger('HTTPServer')
### Initial settings for devnull
if AceConfig.acespawn or AceConfig.transcode: DEVNULL = open(os.devnull, 'wb')
#### Initial settings for AceHTTPproxy host IP
if AceConfig.httphost == '0.0.0.0':
   AceConfig.httphost = [(s.connect(('1.1.1.1', 53)), s.getsockname()[0], s.close()) for s in [socket(AF_INET, SOCK_DGRAM)]][0][1]
   logger.debug('Ace Stream HTTP Proxy server IP: %s autodetected' % AceConfig.httphost)
# Check whether we can bind to the defined port safely
if AceConfig.osplatform != 'Windows' and os.getuid() != 0 and AceConfig.httpport <= 1024:
    logger.error("Cannot bind to port %s without root privileges" % AceConfig.httpport)
    sys.exit(1)

logger.info("Ace Stream HTTP Proxy server starting .....")
logger.debug("Using python %s" % sys.version.split()[0])
logger.debug("Using gevent %s" % gevent.__version__)
logger.debug("Using psutil %s" % psutil.__version__)
logger.debug("Using requests %s" % requests.__version__)
logger.debug("Using bencode %s" % bencode_version__)

# Dropping root privileges if needed
if AceConfig.osplatform != 'Windows' and AceConfig.aceproxyuser and os.getuid() == 0:
    if drop_privileges(AceConfig.aceproxyuser):
        logger.info("Dropped privileges to user %s" % AceConfig.aceproxyuser)
    else:
        logger.error("Cannot drop privileges to user %s" % AceConfig.aceproxyuser)
        sys.exit(1)

# setting signal handlers
try:
    gevent.signal(signal.SIGHUP, _reloadconfig)
    gevent.signal(signal.SIGTERM, shutdown)
except AttributeError: pass  # not available on Windows

# Creating ClientCounter
AceStuff.clientcounter = ClientCounter()

#### AceEngine startup
name = 'ace_engine.exe' if AceConfig.osplatform == 'Windows' else 'acestreamengine'
ace_pid = findProcess(name)
AceStuff.ace = None
if not ace_pid:
    if AceConfig.acespawn:
        if AceConfig.osplatform == 'Windows':
            import _winreg
            AceStuff.aceProc = ""
        else:
            AceStuff.aceProc = AceConfig.acecmd.split()
        if spawnAce(AceStuff.aceProc, 1):
            ace_pid = AceStuff.ace.pid
            AceStuff.ace = psutil.Process(ace_pid)
else: AceStuff.ace = psutil.Process(ace_pid)

# Wait some time for ace engine sturtup .....
if ace_pid :
    gevent.sleep(AceConfig.acestartuptimeout)
    logger.info("Ace Stream engine spawned with pid %s" % AceStuff.ace.pid)
    # refresh the acestream.port file for Windows only after full loading...
    if AceConfig.osplatform == 'Windows': detectPort()

# Loading plugins
# Trying to change dir (would fail in freezed state)
try: os.chdir(os.path.dirname(os.path.realpath(__file__)))
except: pass
# Creating dict of handlers
AceStuff.pluginshandlers = dict()
# And a list with plugin instances
AceStuff.pluginlist = list()
pluginsmatch = glob.glob('plugins/*_plugin.py')
sys.path.insert(0, 'plugins')
pluginslist = [os.path.splitext(os.path.basename(x))[0] for x in pluginsmatch]
logger.info("Load Ace Stream HTTP Proxy plugins .....")
for i in pluginslist:
    plugin = __import__(i)
    plugname = i.split('_')[0].capitalize()
    try:
        plugininstance = getattr(plugin, plugname)(AceConfig, AceStuff)
    except Exception as e:
        logger.error("Cannot load plugin %s: %s" % (plugname, repr(e)))
        continue
    logger.debug('Plugin loaded: %s' % plugname)
    for j in plugininstance.handlers: AceStuff.pluginshandlers[j] = plugininstance
    AceStuff.pluginlist.append(plugininstance)

# Start complite. Wating for requests
server = ThreadedPoolHTTPServer((AceConfig.httphost, AceConfig.httpport),HTTPHandler)
logger.info('Server started at %s:%s Use <Ctrl-C> to stop' % (AceConfig.httphost ,AceConfig.httpport))
try: server.serve_forever()
except (KeyboardInterrupt, SystemExit): shutdown()
