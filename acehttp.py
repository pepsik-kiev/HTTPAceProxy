#!/usr/bin/python3
# -*- coding: utf-8 -*-
'''

AceProxy: Ace Stream to HTTP Proxy
Website: https://github.com/pepsik-kiev/HTTPAceProxy

!!!!! Requirements !!!!!

Python2 (>=2.7.10) or Python3 (>=3.4)
gevent >= 1.3.3
psutil >= 5.3.0

'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
# Monkeypatching and all the stuff
from gevent import monkey; monkey.patch_all()
from gevent.pywsgi import WSGIServer
from gevent.pool import Pool
from gevent.util import wrap_errors
from gevent.socket import socket, AF_INET, SOCK_DGRAM, SHUT_RDWR

import os, sys, glob
# Uppend the directory for custom modules at the front of the path.
ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, 'modules'))
for wheel in glob.glob(os.path.join(ROOT_DIR, 'modules', 'wheels', '*.whl')): sys.path.insert(0, wheel)

import logging
import psutil, requests, signal
from urllib3.packages.six.moves.BaseHTTPServer import BaseHTTPRequestHandler
from urllib3.packages.six.moves.urllib.parse import urlparse, parse_qs, unquote
from urllib3.packages.six.moves import range, map
from ipaddr import IPNetwork, IPAddress
from uuid import uuid4
import mimetypes
from modules.PluginInterface import AceProxyPlugin
import aceclient
from aceclient.clientcounter import ClientCounter
import aceconfig
from aceconfig import AceConfig


class HTTPHandler(BaseHTTPRequestHandler):
    server_version = 'HTTPAceProxy'
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args): pass
        #logger.debug('%s - %s - "%s"' % (self.address_string(), format%args, unquote(self.path).decode('utf8')))

    def log_request(self, code='-', size='-'): pass
        #logger.debug('"%s" %s %s', unquote(self.requestline).decode('utf8'), str(code), str(size))

    def handle(self):
        try: BaseHTTPRequestHandler.handle(self)
        except: pass

    def finish(self):
        try: self.handlerGreenlet.kill()
        except: pass

    def closeConnection(self):
        try: self.connection.shutdown(SHUT_RDWR)
        except: pass

    def dieWithError(self, errorcode=500, logmsg='Dying with error', loglevel=logging.ERROR):
        '''
        Close connection with error
        '''
        if logmsg: logging.log(loglevel, logmsg)
        try:
           self.send_error(errorcode)
           self.end_headers()
        except: pass
        self.closeConnection()

    def do_HEAD(self): return self.do_GET(headers_only=True)

    def do_GET(self, headers_only=False):
        '''
        GET request handler
        '''
        self.handlerGreenlet = gevent.getcurrent() # Current greenlet
        self.clientip = self.headers['X-Forwarded-For'] if 'X-Forwarded-For' in self.headers else self.client_address[0] # Connected client IP address
        logging.info('Accepted connection from %s path %s' % (self.clientip, unquote(self.path)))
        logging.debug('Client headers: %s' % dict(self.headers))

        parse_req = urlparse(self.path)
        self.query, self.path = parse_req.query, parse_req.path[:-1] if parse_req.path.endswith('/') else parse_req.path

        if AceConfig.firewall and not checkFirewall(self.clientip):
           self.dieWithError(401, 'Dropping connection from %s due to firewall rules' % self.clientip, logging.ERROR)
           return
        try:
           self.splittedpath = self.path.split('/')
           self.reqtype = self.splittedpath[1].lower()
           # backward compatibility
           old2newUrlParts = {'torrent': 'url', 'pid': 'content_id'}
           if self.reqtype in old2newUrlParts: self.reqtype = old2newUrlParts[self.reqtype]

           # If first parameter is 'content_id','url','infohash' .... etc or it should be handled by plugin
           if self.reqtype in AceProxy.pluginshandlers:
              try: AceProxy.pluginshandlers.get(self.reqtype).handle(self, headers_only)
              except Exception as e:
                 import traceback
                 logger.error(traceback.format_exc())
                 self.dieWithError(500, 'Plugin exception: %s' % repr(e))
              return

           elif self.reqtype in ('content_id', 'url', 'infohash', 'direct_url', 'data', 'efile_url'):
              self.handleRequest(headers_only)

           else:
              self.dieWithError(400, 'Bad Request', logging.WARNING)  # 400 Bad Request
              return

        except IndexError:
           self.dieWithError(400, 'Bad Request', logging.WARNING)  # 400 Bad Request
           return

    def handleRequest(self, headers_only, **params):
        '''
        :params: dict() with keys: channelName, channelIcon
        '''

        logger = logging.getLogger('HandleRequest')
        self.path = self.path[:-1] if self.path.endswith('/') else self.path

        videoextdefaults = ('.avi', '.flv', '.m2ts', '.mkv', '.mpeg', '.mpeg4', '.mpegts',
                                   '.mpg4', '.mp4', '.mpg', '.mov', '.mpv', '.qt', '.ts', '.wmv')
        # Limit on the number of connected clients
        if 0 < AceConfig.maxconns <= len(AceProxy.clientcounter.getAllClientsList()):
           self.dieWithError(403, "Maximum client connections reached, can't serve request from %s" % self.clientip, logging.ERROR)
           return
        # Check if third parameter exists…/pid/blablablablabla/video.mpg
        #                                                     |_________|
        # And if it ends with regular video extension
        try:
           if not self.path.endswith(videoextdefaults):
              self.dieWithError(501, 'Request seems like valid but no valid video extension was provided', logging.ERROR)
              return
        except IndexError:
           self.dieWithError(400, 'Bad Request', logging.WARNING) # 400 Bad Request
           return
        # Pretend to work fine with Fake or HEAD request.
        if params.get('headers_only') or AceConfig.isFakeRequest(self.path, self.query, self.headers):
           # Return 200 and exit
           if params.get('headers_only'): logger.debug('Sending headers and closing connection')
           else: logger.debug('Fake request - closing connection')
           self.send_response(200)
           self.send_header('Content-Type', 'video/mp2t')
           self.send_header('Connection', 'Close')
           self.end_headers()
           self.closeConnection()
           return

        # Make dict with parameters
        paramsdict = {self.reqtype: unquote(self.splittedpath[2])} # {command: value}
        paramsdict.update({}.fromkeys(aceclient.acemessages.AceConst.START_PARAMS, '0')) # [file_indexes, developer_id, affiliate_id, zone_id, stream_id]
        paramsdict.update({ k:v for (k,v) in [(aceclient.acemessages.AceConst.START_PARAMS[i-3], self.splittedpath[i] if self.splittedpath[i].isdigit() else '0') for i in range(3, len(self.splittedpath))] })
        paramsdict.update({ 'stream_type': ' '.join(['{}={}'.format(k,v) for k,v in AceConfig.acestreamtype.items()]) }) # request http or hls from AceEngine
        paramsdict['request_id'] = self.sessionID = str(uuid4().int)[:8]
        #End parameters dict

        self.connectionTime = gevent.time.time()
        self.clientInfo = self.transcoder = None
        self.channelIcon = params.get('channelIcon')
        if self.channelIcon is None: self.channelIcon = 'http://static.acestream.net/sites/acestream/img/ACE-logo.png'

        try:
           if not AceProxy.clientcounter.idleAce:
              logger.debug('Create connection to AceEngine.....')
              AceProxy.clientcounter.idleAce = aceclient.AceClient(AceConfig.ace, AceConfig.aceconntimeout, AceConfig.aceresulttimeout)
              AceProxy.clientcounter.idleAce.aceInit(AceConfig.acesex, AceConfig.aceage, AceConfig.acekey, AceConfig.videoseekback, AceConfig.videotimeout)
           if self.reqtype not in ('direct_url', 'efile_url'):
              self.CID, self.channelName = AceProxy.clientcounter.idleAce.GETCONTENTINFO(paramsdict)
           else:
              self.channelName = params.get('channelName')
              if self.channelName is None: self.channelName = 'NoNameChannel'
              self.CID = requests.auth.hashlib.sha1(self.channelName.encode('utf-8')).hexdigest()
        except aceclient.AceException as e:
           AceProxy.clientcounter.idleAce = None
           self.dieWithError(404, '%s' % repr(e), logging.ERROR)
           return
        ext = self.channelName[self.channelName.rfind(".") + 1:]
        if ext == self.channelName: ext = parse_qs(self.query).get('ext', ['ts'])[0]
        mimetype = mimetypes.guess_type('%s.%s'%(self.channelName, ext))[0]
        try:
           AceProxy.pool.spawn(wrap_errors(gevent.socket.error, self.rfile.read)).link(lambda x: self.finish()) # Client disconection watchdog
           self.q = gevent.queue.Queue(maxsize=AceConfig.videotimeout)
           self.out = self.wfile
           # If &fmt transcode key present in request
           fmt = parse_qs(self.query).get('fmt', [''])[0]
           if fmt and AceConfig.osplatform != 'Windows':
              if fmt in AceConfig.transcodecmd:
                 stderr = None if AceConfig.loglevel == logging.DEBUG else DEVNULL
                 popen_params = { 'bufsize': 1048576, 'stdin': gevent.subprocess.PIPE,
                                  'stdout': self.wfile, 'stderr': stderr, 'shell': False }
                 try:
                    self.transcoder = gevent.event.AsyncResult()
                    AceProxy.pool.spawn(lambda: psutil.Popen(AceConfig.transcodecmd[fmt], **popen_params)).link(self.transcoder)
                    self.transcoder = self.transcoder.get(timeout=2.0)
                    self.out = self.transcoder.stdin
                    logger.info('Transcoding for %s started' % self.clientip)
                 except:
                    logger.error('Error starting transcoding! Is Ffmpeg or VLC installed?')
                    self.transcoder = None
                    self.out = self.wfile
              else:
                 logger.error("Can't found fmt key. Transcoding not started!")

           # Start broadcast if it does not exist
           if AceProxy.clientcounter.addClient(self) == 1:
              AceProxy.pool.spawn(StreamReader, self.ace.START(paramsdict), self.CID).link(lambda x: logging.debug('Broadcast "%s" stoped. Last client disconnected' % self.channelName))

           logger.info('Streaming "%s" to %s started' % (self.channelName, self.clientip))
           # Sending videostream headers to client
           self.response_use_chunked = False if (self.transcoder is not None or self.request_version == 'HTTP/1.0') else AceConfig.use_chunked
           drop_headers = []
           proxy_headers = { 'Connection': 'keep-alive', 'Keep-Alive': 'timeout=15, max=100', 'Accept-Ranges': 'none',
                             'Transfer-Encoding': 'chunked', 'Content-Type': 'video/MP2T' if mimetype is None else mimetype }

           if not self.response_use_chunked:
              self.protocol_version = 'HTTP/1.0'
              proxy_headers['Connection'] = 'Close'
              drop_headers.extend(['Transfer-Encoding', 'Keep-Alive'])

           response_headers = [(k,v) for (k,v) in proxy_headers.items() if k not in drop_headers]
           self.send_response(200)
           logger.debug('Sending HTTPAceProxy headers to client: %s' % dict(response_headers))
           gevent.joinall([gevent.spawn(self.send_header, k,v) for (k,v) in response_headers])
           self.end_headers()
           # write data to client while he is alive
           for chunk in self.q: self.out.write(chunk)

        except aceclient.AceException as e:
           AceProxy.pool.map(lambda x: x.dieWithError(500, repr(e), logging.ERROR), AceProxy.clientcounter.getClientsList(self.CID))
        except (gevent.GreenletExit, gevent.socket.error): pass # Client disconnected
        finally:
           AceProxy.clientcounter.deleteClient(self)
           logging.info('Streaming "%s" to %s finished' % (self.channelName, self.clientip))
           if self.transcoder:
              try: self.transcoder.kill(); logging.info('Transcoding for %s stoped' % self.clientip)
              except: pass
           self.closeConnection()

class AceProxy(object):
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

def StreamReader(playback_url, cid):

    def write_chunk(client, data, timeout=15.0, _bytearray=bytearray):
        try:
           client.q.put(_bytearray('%x\r\n' % len(data), 'utf-8') + data + b'\r\n' if client.response_use_chunked else data, timeout=timeout)
        except gevent.queue.Full:
           client.dieWithError(500, 'Client %s does not read data until %s sec' % (client.clientip, timeout), logging.ERROR)

    def StreamWriter(url):
        for chunk in s.get(url, timeout=(5, AceConfig.videotimeout)).iter_content(chunk_size=1048576):
           AceProxy.pool.map(lambda x: write_chunk(x, chunk), AceProxy.clientcounter.getClientsList(cid))

    try:
       if not AceProxy.ace:
          playback_url = urlparse(playback_url)._replace(netloc='{aceHostIP}:{aceHTTPport}'.format(**AceConfig.ace)).geturl()
       with requests.session() as s:
          s.verify = False
          s.stream = True
          if playback_url.endswith('.m3u8'): # AceEngine return link for HLS stream
             used_urls = []
             while 1:
                for url in s.get(playback_url, timeout=(5, AceConfig.videotimeout)).iter_lines():
                   if not AceProxy.clientcounter.getClientsList(cid) or url.startswith(b'download not found'): return
                   if url.startswith(b'http://') and url not in used_urls:
                      StreamWriter(url)
                      used_urls.append(url)
                      if len(used_urls) > 15: used_urls.pop(0)
          else: StreamWriter(playback_url) #AceStream return link for HTTP stream
    except TypeError: pass
    except Exception as err:
       AceProxy.pool.map(lambda x: x.dieWithError(500, repr(err), logging.ERROR), AceProxy.clientcounter.getClientsList(cid))

# Spawning procedures
def spawnAce(cmd ='' if AceConfig.osplatform == 'Windows' else AceConfig.acecmd.split(), delay=AceConfig.acestartuptimeout):
    if AceConfig.osplatform == 'Windows':
       from urllib3.packages.six.moves.winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
       try: key = OpenKey(ConnectRegistry(None, HKEY_CURRENT_USER), r'Software\AceStream')
       except: logger.error("Can't find acestream!"); sys.exit(1)
       else:
          engine = QueryValueEx(key, 'EnginePath')
          cmd, AceProxy.acedir = engine[0].split(), os.path.dirname(engine[0])
    try:
       logger.debug('AceEngine start up .....')
       AceProxy.ace = gevent.event.AsyncResult()
       gevent.spawn(lambda: psutil.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)).link(AceProxy.ace)
       AceProxy.ace = AceProxy.ace.get(timeout=delay if delay>=0 else 0.1)
       return isRunning(AceProxy.ace)
    except: return False

def checkAce(chekinterval=AceConfig.acestartuptimeout):
    while 1:
       gevent.sleep(chekinterval)
       if AceConfig.acespawn and not isRunning(AceProxy.ace):
          if AceProxy.clientcounter.idleAce: AceProxy.clientcounter.idleAce.SHUTDOWN()
          if hasattr(AceProxy, 'ace'): del AceProxy.ace
          if spawnAce():
             logger.error('Ace Stream died, respawned with pid %s' % AceProxy.ace.pid)
             # refresh the acestream.port file for Windows only after full loading...
             if AceConfig.osplatform == 'Windows': detectPort()
             else: gevent.sleep(AceConfig.acestartuptimeout)
             # Creating ClientCounter
             AceProxy.clientcounter = ClientCounter()
          else:
             logger.error("Can't spawn Ace Stream!")

def checkFirewall(clientip):
    try: clientinrange = any([IPAddress(clientip) in IPNetwork(i) for i in AceConfig.firewallnetranges])
    except: logger.error('Check firewall netranges settings !'); return False
    if (AceConfig.firewallblacklistmode and clientinrange) or (not AceConfig.firewallblacklistmode and not clientinrange): return False
    return True

def detectPort():
    try:
       if not isRunning(AceProxy.ace):
          logger.error("Couldn't detect port! Ace Engine is not running?")
          clean_proc(); sys.exit(1)
    except AttributeError:
          logger.error("Ace Engine is not running!")
          clean_proc(); sys.exit(1)
    from urllib3.packages.six.moves.winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
    try: key = OpenKey(ConnectRegistry(None, HKEY_CURRENT_USER), r'Software\AceStream')
    except:
       logger.error("Can't find AceStream!")
       clean_proc(); sys.exit(1)
    else:
       engine = QueryValueEx(key, 'EnginePath')
       AceProxy.acedir = os.path.dirname(engine[0])
       try:
           gevent.sleep(AceConfig.acestartuptimeout)
           with open(AceProxy.acedir + '\\acestream.port', 'r') as f:
              AceConfig.ace['aceAPIport'] = f.read()
       except IOError:
           logger.error("Couldn't detect port! acestream.port file doesn't exist?")
           clean_proc(); sys.exit(1)
       else: logger.info("Detected ace port: %s" % AceConfig.ace['aceAPIport'])

def isRunning(process):
    return True if process.is_running() and process.status() != psutil.STATUS_ZOMBIE else False

def findProcess(name):
    pinfo = [p.info for p in psutil.process_iter(attrs=['pid', 'name']) if name in p.info['name']]
    return pinfo[0]['pid'] if pinfo else None

def clean_proc():
    # Trying to close all spawned processes gracefully
    if AceConfig.acespawn and isRunning(AceProxy.ace):
       if AceProxy.clientcounter.idleAce:
          AceProxy.clientcounter.idleAce.SHUTDOWN(); gevent.sleep(1)
       AceProxy.ace.terminate()
       if AceConfig.osplatform == 'Windows' and os.path.isfile(AceProxy.acedir + '\\acestream.port'):
          try:
             os.remove(AceProxy.acedir + '\\acestream.port')
             for proc in psutil.process_iter():
                if proc.name() == 'ace_engine.exe': proc.kill()
          except: pass

# This is what we call to stop the server completely
def shutdown(signum=0, frame=0):
    logger.info('Shutdown server.....')
    clean_proc()
    server.stop()
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
    try: return [(s.connect(('1.1.1.1', 80)), s.getsockname()[0], s.close()) for s in [socket(AF_INET, SOCK_DGRAM)]][0][1]
    except:
       logger.error('Network is unreachable')
       sys.exit()

def check_compatibility(gevent_version, psutil_version):

    # Check gevent for compatibility.
    major, minor, patch = map(int, gevent_version.split('.')[:3])
    # gevent >= 1.3.3
    assert major == 1
    assert minor >= 3
    assert minor >= 3

    # Check psutil for compatibility.
    major, minor, patch = map(int, psutil_version.split('.')[:3])
    # psutil >= 5.3.0
    assert major == 5
    assert minor >= 3
    assert patch >= 0

logging.basicConfig(level=AceConfig.loglevel, filename=AceConfig.logfile, format=AceConfig.logfmt, datefmt=AceConfig.logdatefmt)
logger = logging.getLogger('HTTPServer')

### Initial settings for devnull
if AceConfig.acespawn or AceConfig.transcodecmd:
   try:
      from gevent.subprocess import DEVNULL  # Py3
   except ImportError:
      DEVNULL = open(os.devnull, 'wb')  # Py2

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

# Creating ClientCounter
AceProxy.clientcounter = ClientCounter()
#### AceEngine startup
AceProxy.ace = findProcess('ace_engine.exe' if AceConfig.osplatform == 'Windows' else os.path.basename(AceConfig.acecmd))
if not AceProxy.ace and AceConfig.acespawn:
   if spawnAce():
      logger.info('Local AceStream engine spawned with pid %s' % AceProxy.ace.pid)
      gevent.spawn(checkAce) # Start AceEngine alive watchdog
elif AceProxy.ace:
   AceProxy.ace = psutil.Process(AceProxy.ace)
   logger.info('Local AceStream engine found with pid %s' % AceProxy.ace.pid)

# If AceEngine started (found) localy
if AceProxy.ace:
   AceConfig.ace['aceHostIP'] = '127.0.0.1'
   # Refreshes the acestream.port file for OS Windows.....
   if AceConfig.osplatform == 'Windows': detectPort()
   else: gevent.sleep(AceConfig.acestartuptimeout)
else:
   url = 'http://{aceHostIP}:{aceHTTPport}/webui/api/service'.format(**AceConfig.ace)
   params = {'method': 'get_version', 'format': 'json', 'callback': 'mycallback'}
   try:
      with requests.get(url, params=params, timeout=5) as r:
         logger.info('Remote AceStream engine ver.{} will be used on {aceHostIP}:{aceAPIport}'.format(r.json()['result']['version'], **AceConfig.ace))
   except: logger.error('AceStream not found!')

# Loading plugins
# Trying to change dir (would fail in freezed state)
try: os.chdir(ROOT_DIR)
except: pass
sys.path.insert(0, 'plugins')
logger.info("Load Ace Stream HTTP Proxy plugins .....")
pluginslist = [os.path.splitext(os.path.basename(x))[0] for x in glob.glob('plugins/*_plugin.py')]

def add_handler(i):
    plugin = __import__(i)
    plugname = i.split('_')[0].capitalize()
    try: plugininstance = getattr(plugin, plugname)(AceConfig, AceProxy)
    except Exception as err: logger.error("Can't load plugin %s: %s" % (plugname, repr(err)))
    logger.debug('Plugin loaded: %s' % plugname)
    return {j:plugininstance for j in plugininstance.handlers}

AceProxy.pool = Pool()
# Creating dict of handlers
AceProxy.pluginshandlers = {key:val for k in AceProxy.pool.map(add_handler, pluginslist) for key,val in k.items()}
# Server setup
server = WSGIServer((AceConfig.httphost, AceConfig.httpport), log=None, handler_class=HTTPHandler, spawn=AceProxy.pool)
# Setting signal handlers
gevent.signal(signal.SIGTERM, shutdown)
gevent.signal(signal.SIGINT, shutdown)
if AceConfig.osplatform != 'Windows': gevent.signal(signal.SIGHUP, _reloadconfig)
server.start()
logger.info('Server started at %s:%s Use <Ctrl-C> to stop' % (server.server_host, server.server_port))
# Start complite. Wating for requests
gevent.wait()
