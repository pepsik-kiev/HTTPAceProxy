#!/usr/bin/python
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
# http://www.gevent.org/api/gevent.resolver.ares.html
try: gevent.config.resolver = ['ares', 'thread', 'dnspython', 'block']
except: pass
# Monkeypatching and all the stuff
from gevent import monkey; monkey.patch_all()
from gevent.pool import Pool
from gevent.server import StreamServer
from gevent.util import wrap_errors
from gevent.socket import socket, AF_INET, SOCK_DGRAM, SHUT_RDWR

import os, sys, glob
# Uppend the directory for custom modules at the front of the path.
ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, 'modules'))
for wheel in glob.glob(os.path.join(ROOT_DIR, 'modules', 'wheels', '*.whl')): sys.path.insert(0, wheel)

import logging
import psutil, requests, signal, mimetypes, traceback
from urllib3.packages.six.moves.BaseHTTPServer import BaseHTTPRequestHandler
from urllib3.packages.six.moves.urllib.parse import urlparse, unquote
from urllib3.packages.six.moves import range, map
from urllib3.packages.six import ensure_binary, ensure_str
try:
   from ipaddress import ip_network as IPNetwork, ip_address as IPAddress
except:
   from ipaddr import IPNetwork, IPAddress
import aceclient
from aceclient.clientcounter import ClientCounter
import aceconfig
from aceconfig import AceConfig
from utils import schedule, query_get

class HTTPHandler(BaseHTTPRequestHandler):

    server_version = 'HTTPAceProxy'
    protocol_version = 'HTTP/1.1'

    def __init__(self, socket, client_address):
        try: BaseHTTPRequestHandler.__init__(self, socket, client_address, self)
        except: pass

    def log_message(self, format, *args): pass
        #logger.debug('%s - %s - "%s"' % (self.address_string(), format%args, unquote(self.path).decode('utf8')))

    def log_request(self, code='-', size='-'): pass
        #logger.debug('"%s" %s %s', unquote(self.requestline).decode('utf8'), str(code), str(size))

    def finish(self):
        logging.debug('[{clientip}]: Disconnected'.format(**self.__dict__))
        self.connection.shutdown(SHUT_RDWR)
        if self.handlerGreenlet:
           self.handlerGreenlet.kill()

    def send_error(self, errorcode=500, logmsg='Dying with error', loglevel=logging.ERROR):
        '''
        Close connection with error
        '''
        try:
           self.send_response(errorcode)
           self.send_header('Content-Type', 'text/plain')
           self.send_header('Content-Length', len(logmsg))
           self.send_header('Connection', 'Close')
           self.end_headers()
           self.wfile.write(ensure_binary(logmsg))
        finally:
           logging.log(loglevel, logmsg)
           self.handlerGreenlet.kill()

    def do_HEAD(self):
        '''
        HEAD request handler
        '''
        return self.do_GET()

    def do_GET(self):
        '''
        GET request handler
        '''
        self.handlerGreenlet = gevent.getcurrent() # Current greenlet
        self.clientip = self.headers.get('X-Forwarded-For', self.address_string()) # Connected client IP address
        logging.info(unquote('[{clientip}]: {command} {request_version} request for: {path}'.format(**self.__dict__)))
        logging.debug('[%s]: Request headers: %s' % (self.clientip, dict(self.headers)))

        if AceConfig.firewall and not checkFirewall(self.clientip):
           self.send_error(401, '[{clientip}]: Dropping connection due to firewall rules'.format(**self.__dict__), logging.ERROR)

        self.path, _, self.query = self.path.partition('?')
        self.path = self.path.rstrip('/')
        # Pretend to work fine with Fake or HEAD request.
        if self.command == 'HEAD' or AceConfig.isFakeRequest(self.path, self.query, self.headers):
           # Return 200 and exit
           if self.command != 'HEAD': self.command = 'FAKE'
           logging.debug('[{clientip}]: {command} request: send headers and close the connection'.format(**self.__dict__))
           self.send_response(200)
           self.send_header('Content-Type', 'video/mp2t')
           self.send_header('Connection', 'Close')
           self.end_headers()
           return

        try:
           self.splittedpath = self.path.split('/')
           self.reqtype = self.splittedpath[1].lower()
           AceProxy.pluginshandlers[self.reqtype].handle(self) # If request should be handled by plugin
           raise IndexError()

        except (IndexError, KeyError):
           self.reqtype = {'torrent': 'url', 'pid': 'content_id'}.get(self.reqtype, self.reqtype) # For backward compatibility
           if self.reqtype in {'content_id', 'url', 'infohash', 'direct_url', 'data', 'efile_url'}:
              # Limit on the number of connected clients
              if 0 < AceConfig.maxconns <= len(AceProxy.clientcounter.getAllClientsList()):
                 self.send_error(403, "[{clientip}]: Maximum client connections reached, can't serve request".format(**self.__dict__), logging.ERROR)
              # Check if third path parameter is exists /{reqtype}/{reqtype_value}/.../.../video.mpg
              #                                                                           |_________|
              # And if it ends with regular video extension
              if not self.splittedpath[-1].endswith(('.avi', '.flv', '.m2ts', '.mkv', '.mpeg', '.mpeg4', '.mpegts',
                                                     '.mpg4', '.mp4', '.mpg', '.mov', '.mpv', '.qt', '.ts', '.wmv')):
                    self.send_error(501, '[{clientip}]: request seems like valid but no valid video extension was provided'.format(**self.__dict__), logging.ERROR)
              else:
                 self.handleRequest()
           elif self.reqtype not in AceProxy.pluginshandlers:
              self.send_error(400, '[{clientip}]: Bad Request'.format(**self.__dict__), logging.WARNING)  # 400 Bad Request

        except Exception as e:
           logging.error('Unexpected exception: %s' % repr(e))
           logging.error(traceback.format_exc())

    def handleRequest(self):
        '''
        Main request handler path: /{reqtype}/{reqtype_value}/{file_indexes}/{developer_id}/{affiliate_id}/{zone_id}/{stream_id}/{fname}.{ext}
        '''
        logger = logging.getLogger('handleRequest')
        # Make handler parameters dict
        self.__dict__.update({}.fromkeys(aceclient.acemessages.AceConst.START_PARAMS, '0')) # [file_indexes, developer_id, affiliate_id, zone_id, stream_id]
        self.__dict__.update({k:v for (k,v) in [(aceclient.acemessages.AceConst.START_PARAMS[i-3], self.splittedpath[i] if self.splittedpath[i].isdigit() else '0') for i in range(3, len(self.splittedpath))]})
        self.__dict__.update({self.reqtype: unquote(self.splittedpath[2]), # {reqtype: reqtype_value}
                              'ace': AceConfig.ace,
                              'acesex': AceConfig.acesex,
                              'aceage': AceConfig.aceage,
                              'acekey': AceConfig.acekey,
                              'connect_timeout': AceConfig.aceconntimeout,
                              'result_timeout': AceConfig.aceresulttimeout,
                              'videoseekback': AceConfig.videoseekback,
                              'videotimeout': AceConfig.videotimeout,
                              'stream_type': ' '.join(['{}={}'.format(k,v) for k,v in AceConfig.acestreamtype.items()]), # request http or hls from AceEngine
                              'sessionID': self.handlerGreenlet.name[self.handlerGreenlet.name.rfind('-') + 1:], # Greenlet.minimal_ident A small, unique non-negative integer
                              'connectionTime': gevent.time.time(),
                              'clientDetail': None,
                              'channelIcon': self.__dict__.get('channelIcon', 'http://static.acestream.net/sites/acestream/img/ACE-logo.png'),
                             })
        # End parameters dict
        try:
           self.q = gevent.queue.Queue(maxsize=AceConfig.videotimeout)
           transcoder = gevent.event.AsyncResult()
           out = self.wfile
           gevent.spawn(wrap_errors(gevent.socket.error, self.rfile.read)).link(lambda x: self.handlerGreenlet.kill()) # Client disconection watchdog
           try:
              if not AceProxy.clientcounter.idleAce:
                 logger.debug('Create a connection with AceStream on {ace[aceHostIP]}:{ace[aceAPIport]}'.format(**self.__dict__))
                 AceProxy.clientcounter.idleAce = aceclient.AceClient(self.__dict__)
                 AceProxy.clientcounter.idleAce.GetAUTH()
              if self.reqtype not in ('direct_url', 'efile_url'):
                 self.__dict__.update(AceProxy.clientcounter.idleAce.GetCONTENTINFO(self.__dict__))
                 self.channelName = ensure_str(self.__dict__.get('channelName', next(iter([ x[0] for x in self.files if x[1] == int(self.file_indexes) ]), 'NoNameChannel')))
              else:
                 self.channelName = ensure_str(self.__dict__.get('channelName', 'NoNameChannel'))
                 self.infohash = requests.auth.hashlib.sha1(ensure_binary(self.path)).hexdigest()
              AceProxy.clientcounter.idleAce._title = self.channelName
           except Exception as e:
              AceProxy.clientcounter.idleAce._read.kill()
              self.send_error(404, '%s' % repr(e), logging.ERROR)

           self.ext = self.__dict__.get('ext', self.channelName[self.channelName.rfind('.') + 1:])
           if self.ext == self.channelName: self.ext = query_get(self.query, 'ext', 'ts')
           mimetype = mimetypes.guess_type('{channelName}.{ext}'.format(**self.__dict__))[0]
           try:
              # If &fmt transcode key present in request
              fmt = query_get(self.query, 'fmt')
              if fmt:
                 if AceConfig.osplatform != 'Windows':
                    if fmt in AceConfig.transcodecmd:
                       stderr = None if AceConfig.loglevel == logging.DEBUG else DEVNULL
                       popen_params = { 'bufsize': 1048576, 'stdin': gevent.subprocess.PIPE,
                                        'stdout': self.wfile, 'stderr': stderr, 'shell': False }
                       try:
                          gevent.spawn(lambda: psutil.Popen(AceConfig.transcodecmd[fmt], **popen_params)).link(transcoder)
                          out = transcoder.get(timeout=2.0).stdin
                          logger.info('[{channelName}]: Transcoding to [{clientip}] started'.format(**self.__dict__))
                       except:
                          logger.error('[{channelName}]: Error starting transcoding to [{clientip}]! Is ffmpeg or VLC installed?'.format(**self.__dict__))
                    else:
                       logger.error("[{channelName}]: Can't found fmt key. Transcoding to [{clientip}] not started!".format(**self.__dict__))
                 elif AceConfig.osplatform == 'Windows':
                    logger.error('[{channelName}]: Not applicable in Windnows OS. Transcoding to [{clientip}] not started!'.format(**self.__dict__))

              if AceProxy.clientcounter.addClient(self) == 1:
                 # Create broadcast if it does not exist yet
                 gevent.spawn(StreamReader, self.ace.GetBroadcastStartParams(self.__dict__)).link(lambda x: logger.debug('[{channelName}]: Broadcast destroyed. Last client disconnected'.format(**self.__dict__)))
                 logger.debug('[{channelName}]: Broadcast created'.format(**self.__dict__))
              else:
                 logger.debug('[{channelName}]: Broadcast already exists'.format(**self.__dict__))
              logger.info('[{channelName}]: Streaming to [{clientip}] started'.format(**self.__dict__))
              # Sending videostream headers to client
              response_use_chunked = False if (transcoder.value or self.request_version == 'HTTP/1.0') else AceConfig.use_chunked
              drop_headers = []
              proxy_headers = { 'Connection': 'keep-alive',
                                'Keep-Alive': 'timeout=%s, max=100' % AceConfig.videotimeout,
                                'Accept-Ranges': 'none',
                                'Transfer-Encoding': 'chunked',
                                'Content-Type': 'video/MP2T' if mimetype is None else mimetype,
                              }

              if not response_use_chunked:
                 self.protocol_version = 'HTTP/1.0'
                 proxy_headers['Connection'] = 'Close'
                 drop_headers.extend(['Transfer-Encoding', 'Keep-Alive'])

              response_headers = [(k,v) for (k,v) in proxy_headers.items() if k not in drop_headers]
              self.send_response(200)
              logger.debug('[%s]: Sending HTTPAceProxy headers: %s' % (self.clientip, dict(response_headers)))
              gevent.joinall([gevent.spawn(self.send_header, k,v) for (k,v) in response_headers])
              self.end_headers()
              # write data to client while it is alive
              for chunk in self.q:
                 out.write(b'%X\r\n%s\r\n' % (len(chunk),chunk) if response_use_chunked else chunk)

           except aceclient.AceException as e:
              _ = AceProxy.pool.map(lambda x: x.send_error(500, repr(e), logging.ERROR), AceProxy.clientcounter.getClientsList(self.infohash))
           except  gevent.socket.error: pass # Client disconnected

        except gevent.GreenletExit:
           AceProxy.clientcounter.idleAce._read.kill()

        finally:
           AceProxy.clientcounter.deleteClient(self)
           logger.info('[{channelName}]: Streaming to [{clientip}] finished'.format(**self.__dict__))
           if transcoder.value:
              try: transcoder.value.kill(); logger.info('[{channelName}]: Transcoding to [{clientip}] stoped'.format(**self.__dict__))
              except: pass

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
    value = (os.getuid() == running_uid and os.getgid() == running_gid)
    if value:  # could be useful
       os.environ['HOME'] = running_uid_home
       logger.info('Changed permissions to: %s: %i, %s, %i' % (uid_name, running_uid, gid_name, running_gid))
    return value

def StreamReader(params):
    '''
    params: dict([url=] [file_index=] [infohash= ] [ad=1 [interruptable=1]] [stream=1] [pos=position] [bitrate=] [length=])
    '''

    def checkBroadcast():
        if not params['broadcastclients']:
           params['broadcast'].kill()
        return params['broadcast'].started

    def write_chunk(client, chunk, timeout=15.0):
        try: client.q.put(chunk, timeout=timeout)
        except gevent.queue.Full:
           client.send_error(500, '[%s]: does not read data until %s sec' % (client.clientip, timeout), logging.ERROR)

    def StreamWriter(url):
        for chunk in s.get(url, timeout=(5, AceConfig.videotimeout), stream=True).iter_content(chunk_size=1048576):
           _ = params['chunkpool'].map(lambda client: write_chunk(client, chunk), params['broadcastclients'])

    try:
       params.update({'url': urlparse(unquote(params['url']))._replace(netloc='{aceHostIP}:{aceHTTPport}'.format(**AceConfig.ace)).geturl(),
                      'broadcast': gevent.getcurrent(),
                      'broadcastclients': AceProxy.clientcounter.getClientsList(params['infohash']),
                      'chunkpool': Pool(),
                     })
       with requests.session() as s:
          if params['url'].endswith('.m3u8'): # AceEngine return link for HLS stream
             import m3u8; urls = []
             while checkBroadcast():
                for url in m3u8.load(params['url']).segments.uri:
                   if url in urls: continue
                   else:
                      StreamWriter(url)
                      urls.append(url)
                      if len(urls) > 50: urls.pop(0)

          else: StreamWriter(params['url']) #AceStream return link for HTTP stream
    except (TypeError, gevent.GreenletExit): pass
    except Exception as err:
       _ = AceProxy.pool.map(lambda x: x.send_error(500, repr(err), logging.ERROR), params['broadcastclients'])

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
       AceProxy.ace = AceProxy.ace.get(timeout=delay if delay>=0 else 0.5)
       return isRunning(AceProxy.ace)
    except: return False

def checkAce():
    if AceConfig.acespawn and not isRunning(AceProxy.ace):
       if AceProxy.clientcounter.idleAce: AceProxy.clientcounter.idleAce.ShutdownAce()
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
    return not ((AceConfig.firewallblacklistmode and clientinrange) or (not AceConfig.firewallblacklistmode and not clientinrange))

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
       else: logger.info('Detected ace port: {aceAPIport}'.format(**AceConfig.ace))

def isRunning(process):
     return (process.is_running() and process.status() != psutil.STATUS_ZOMBIE)

def findProcess(name):
    pinfo = next(iter([p.info for p in psutil.process_iter(attrs=['pid', 'name']) if name in p.info['name']]), None)
    return pinfo['pid'] if pinfo else pinfo

def clean_proc():
    # Trying to close all spawned processes gracefully
    _ = AceProxy.pool.map(lambda x: x.send_error(500, '[{clientip}]: abnormal termination!'.format(**x.__dict__), logging.ERROR), AceProxy.clientcounter.getAllClientsList())
    if AceConfig.acespawn and isRunning(AceProxy.ace):
       if AceProxy.clientcounter.idleAce:
          AceProxy.clientcounter.idleAce.ShutdownAce(); gevent.sleep(0.5)
       AceProxy.ace.terminate()
       if AceConfig.osplatform == 'Windows' and os.path.isfile(AceProxy.acedir + '\\acestream.port'):
          try:
             os.remove(AceProxy.acedir + '\\acestream.port')
             for proc in psutil.process_iter():
                if proc.name() == 'ace_engine.exe': proc.kill()
          except: pass

# This is what we call to stop the server completely
def shutdown():
    logging.info('Received CTL+C, shutting down Ace Stream HTTP Proxy server.....')
    clean_proc()
    AceProxy.server.close()
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
    # connecting to a UDP address doesn't send packets
    try: return [(s.connect(('1.1.1.1', 0)), s.getsockname()[0], s.close()) for s in [socket(AF_INET, SOCK_DGRAM)]][0][1]
    except:
       logger.error('Network is unreachable')
       sys.exit()

def check_compatibility(gevent_version, psutil_version):

    if not 'dev' in gevent_version:
       # Check gevent for compatibility.
       major, minor, patch = map(int, gevent_version.split('.')[:3])
       # gevent >= 1.3.3
       assert major >= 1

    # Check psutil for compatibility.
    major, minor, patch = map(int, psutil_version.split('.')[:3])
    # psutil >= 5.3.0
    assert major >= 5

logging.basicConfig(level=AceConfig.loglevel, filename=AceConfig.logfile, format=AceConfig.logfmt, datefmt=AceConfig.logdatefmt)
logger = logging.getLogger('HTTPServer')

### Initial settings for devnull
if AceConfig.acespawn or AceConfig.transcodecmd:
   try:
      from gevent.subprocess import DEVNULL  # Py3
   except ImportError:
      DEVNULL = open(os.devnull, 'wb')  # Py2

logger.info('Ace Stream HTTP Proxy server on Python %s starting .....' % sys.version.split()[0])
logger.debug('Using: %s OS with gevent %s, psutil %s' % (AceConfig.osplatform, gevent.__version__, psutil.__version__))

try: check_compatibility(gevent.__version__, psutil.__version__)
except (AssertionError, ValueError):
   logger.error("gevent %s or psutil %s doesn't match a supported version!" % (gevent.__version__, psutil.__version__))
   logger.error('Update python dependencies to required: gevent >= 1.3.3, psutil >= 5.3.0')
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
AceProxy.pool = Pool()
AceProxy.clientcounter = ClientCounter()
#### AceEngine startup
AceProxy.ace = findProcess('ace_engine.exe' if AceConfig.osplatform == 'Windows' else os.path.basename(AceConfig.acecmd))
if not AceProxy.ace and AceConfig.acespawn:
   if spawnAce():
      logger.info('Local AceStream engine spawned with pid %s' % AceProxy.ace.pid)
      schedule(AceConfig.acestartuptimeout, checkAce) # Start AceEngine alive watchdog
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
logger.info('Load Ace Stream HTTP Proxy plugins .....')

def add_handler(name):
    # isidentifier() Py2/Py3 compatible
    if requests.utils.re.match(r'^\w+$', name, requests.utils.re.UNICODE) and not name[0].isdigit() and name not in sys.modules:
       try:
          plugname = name.split('_')[0].capitalize()
          plugininstance = getattr(__import__(name), plugname)(AceConfig, AceProxy)
       except Exception as err: logger.error("Can't load plugin %s: %s" % (plugname, repr(err)))
       else:
          logger.debug('[%-15.15s]: Plugin loaded' % plugname)
          return {j:plugininstance for j in plugininstance.handlers}

# Creating dict of handlers
pluginslist = [os.path.splitext(os.path.basename(x))[0] for x in glob.glob('plugins/*_plugin.py')]
AceProxy.pluginshandlers = {key:val for k in map(add_handler, pluginslist) for key,val in k.items()}
# Server setup
AceProxy.server = StreamServer((AceConfig.httphost, AceConfig.httpport), handle=HTTPHandler, spawn=AceProxy.pool)
# Capture  signal handlers (SIGINT, SIGQUIT etc.)
gevent.signal_handler(signal.SIGTERM, shutdown)
gevent.signal_handler(signal.SIGINT, shutdown)
if AceConfig.osplatform != 'Windows':
   gevent.signal_handler(signal.SIGQUIT, shutdown)
   gevent.signal_handler(signal.SIGHUP, _reloadconfig)
AceProxy.server.start()
logger.info('Server started at {}:{} Use <Ctrl-C> to stop'.format(AceConfig.httphost, AceConfig.httpport))
# Start complite. Wating for requests
gevent.wait()
