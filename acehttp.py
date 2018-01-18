#!/usr/bin/python2
# -*- coding: utf-8 -*-
'''
AceProxy: Ace Stream to HTTP Proxy

Website: https://github.com/ValdikSS/AceProxy
'''

import os, sys
# Uppend the directory for custom modules at the front of the path.
base_dir = os.path.dirname(os.path.realpath(__file__))
wheels_dir = os.path.join(base_dir, 'plugins/modules/wheels')
wheels_list = filter(lambda x: x.endswith('.whl'), os.listdir(wheels_dir))
for filename in wheels_list:
  sys.path.insert(0, wheels_dir + '/' + filename)

modules_dir = os.path.join(base_dir, 'plugins/modules')
sys.path.insert(0, modules_dir)

import traceback
import gevent, gevent.monkey
from gevent.queue import Full
# Monkeypatching and all the stuff
gevent.monkey.patch_all()

import aceclient
from aceconfig import AceConfig
from aceclient.clientcounter import ClientCounter
import glob
import signal
import logging
import psutil
from subprocess import PIPE
from socket import error as SocketException
from socket import SHUT_RDWR, socket, AF_INET, SOCK_DGRAM
from collections import deque
from base64 import b64encode
import time
import threading
import requests
from bencode import __version__ as bencode_version__
import ipaddr
from urlparse import urlparse, urlsplit, urlunsplit, parse_qs
import BaseHTTPServer, SocketServer
import Queue
from plugins.modules.PluginInterface import AceProxyPlugin
try:
    import pwd
    import grp
except ImportError:
    # Windows
    pass

class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    requestlist = []

    def log_message(self, format, *args):
        logger.info("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          requests.utils.unquote(format%args).decode('UTF-8')))

    def log_request(self, code='-', size='-'):
        logger.debug('"%s" %s %s',
                         self.requestline, str(code), str(size))

    def log_error(self, format, *args):
        logger.error(format, *args)

    def handle_one_request(self):
        '''
        Add request to requestlist, handle request and remove from the list
        '''
        HTTPHandler.requestlist.append(self)
        BaseHTTPServer.BaseHTTPRequestHandler.handle_one_request(self)
        HTTPHandler.requestlist.remove(self)

    def closeConnection(self):
        '''
        Disconnecting client
        '''
        if self.connected:
            self.connected = False
            try:
                self.wfile.close()
                self.rfile.close()
                self.connection.shutdown(SHUT_RDWR)
            except:
                pass

    def dieWithError(self, errorcode=500, logmsg='Dying with error', loglevel=logging.WARN):
        '''
        Close connection with error
        '''
        if logmsg:
            logging.log(loglevel, logmsg)
        if self.connected:
            try:
                self.send_error(errorcode)
                self.end_headers()
                self.closeConnection()
            except:
                pass

    def hangDetector(self):
        '''
        Detect client disconnection while in the middle of something
        or just normal connection close.
        '''
        logger = logging.getLogger('http_hangDetector')
        try:
            while True:
                if not self.rfile.read():
                    break
        except:
            pass
        finally:
            logger.debug("Client disconnected")
            client = self.client
            video = self.video

            if client:
                client.destroy()
            if video:
                video.close()

    def do_HEAD(self):
        return self.do_GET(headers_only=True)

    def do_GET(self, headers_only=False):
        '''
        GET request handler
        '''
        logger = logging.getLogger('do_GET')
        self.reqtime = time.time()
        self.connected = True
        # Set HTTP protocol version
        if self.request_version == 'HTTP/1.1':
             self.protocol_version = 'HTTP/1.1'
        # Don't wait videodestroydelay if error happened
        self.errorhappened = True
        # Connected client IP address
        self.clientip = self.headers['X-Forwarded-For'] if 'X-Forwarded-For' in self.headers else self.request.getpeername()[0]

        if AceConfig.firewall:
            # If firewall enabled
            self.clientinrange = any(map(lambda i: ipaddr.IPAddress(self.clientip) \
                                in ipaddr.IPNetwork(i), AceConfig.firewallnetranges))

            if (AceConfig.firewallblacklistmode and self.clientinrange) or \
                (not AceConfig.firewallblacklistmode and not self.clientinrange):
                    logger.info('Dropping connection from ' + self.clientip + ' due to ' + \
                                'firewall rules')
                    self.dieWithError(403)  # 403 Forbidden
                    return

        logger.info("Accepted connection from " + self.clientip + " path " + requests.utils.unquote(self.path).decode('UTF-8'))
        logger.debug("Headers:\n" + str(self.headers))
        try:
            self.splittedpath = self.path.split('/')
            self.reqtype = self.splittedpath[1].lower()
            # If first parameter is 'pid','torrent', 'infohash'.... etc or it should be handled
            # by plugin
            if not (self.reqtype in ('pid','torrent','infohash','url','raw','efile') or self.reqtype in AceStuff.pluginshandlers):
                self.dieWithError(400)  # 400 Bad Request
                return
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            return

        # Handle request with plugin handler
        if self.reqtype in AceStuff.pluginshandlers:
            try:
                AceStuff.pluginshandlers.get(self.reqtype).handle(self, headers_only)
            except Exception as e:
                logger.error('Plugin exception: ' + repr(e))
                logger.error(traceback.format_exc())
                self.dieWithError()
            finally:
                self.closeConnection()
                return

        self.handleRequest(headers_only)

    def handleRequest(self, headers_only, channelName=None, channelIcon=None, fmt=None):
        logger = logging.getLogger('HandleRequest')
        #logger.debug("Accept connected client headers :\n" + str(self.headers))
        self.requrl = urlparse(self.path)
        self.reqparams = parse_qs(self.requrl.query)
        self.path = self.requrl.path[:-1] if self.requrl.path.endswith('/') else self.requrl.path
        self.videoextdefaults = ('.3gp','.aac','.ape','.asf','.avi','.dv','.divx','.flac','.flc','.flv','.m2ts','.m4a','.mka','.mkv',
                                 '.mpeg','.mpeg4','.mpegts','.mpg4','.mp3','.mp4','.mpg','.mov','.m4v','.ogg','.ogm','.ogv','.oga',
                                 '.ogx','.qt','.rm','.swf','.ts','.vob','.wmv','.wav','.webm')
        # Check if third parameter exists…/pid/blablablablabla/video.mpg
        #                                                     |_________|
        # And if it ends with regular video extension
        try:
            if not self.path.endswith(self.videoextdefaults):
                logger.error("Request seems like valid but no valid video extension was provided")
                self.dieWithError(400)
                return
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            return

        # Limit concurrent connections
        if 0 < AceConfig.maxconns <= AceStuff.clientcounter.total:
            logger.info("Maximum connections reached, can't serve this")
            self.dieWithError(503)  # 503 Service Unavailable
            return

        # Pretend to work fine with Fake or HEAD request.
        if headers_only or AceConfig.isFakeRequest(self.path, self.reqparams, self.headers):
            # Return 200 and exit
            if headers_only:
                logger.debug("Sending headers and closing connection")
            else:
                logger.debug("Fake request - closing connection")
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
            self.send_header("Connection", "Close")
            self.end_headers()
            self.closeConnection()
            return

        # Make list with parameters
        # file_indexes developer_id affiliate_id zone_id stream_id
        self.params = list()
        for i in xrange(3, 8):
            try:
                self.params.append(int(self.splittedpath[i]))
            except (IndexError, ValueError):
                self.params.append('0')
        # End parameters

        self.url = None
        self.video = None

        self.path_unquoted = requests.utils.unquote(self.splittedpath[2])
        contentid = self.getCid(self.reqtype, self.path_unquoted)
        cid = contentid if contentid else self.path_unquoted

        self.client = Client(cid, self, channelName, channelIcon)
        shouldStart = AceStuff.clientcounter.add(cid, self.client) == 1

        try:
            # Initializing AceClient
            if shouldStart:
                # Send commands to AceEngine
                if contentid:
                    self.client.ace.START('PID', {'content_id': contentid, 'file_indexes': self.params[0]}, AceConfig.streamtype)
                elif self.reqtype == 'pid':
                    self.client.ace.START(self.reqtype, {'content_id': self.path_unquoted, 'file_indexes': self.params[0]}, AceConfig.streamtype)
                elif self.reqtype == 'torrent':
                    paramsdict = dict(zip(aceclient.acemessages.AceConst.START_PARAMS, self.params))
                    paramsdict['url'] = self.path_unquoted
                    self.client.ace.START(self.reqtype, paramsdict, AceConfig.streamtype)
                elif self.reqtype == 'infohash':
                    paramsdict = dict(zip(aceclient.acemessages.AceConst.START_PARAMS, self.params))
                    paramsdict['infohash'] = self.path_unquoted
                    self.client.ace.START(self.reqtype, paramsdict, AceConfig.streamtype)
                elif self.reqtype == 'url':
                    paramsdict = dict(zip(aceclient.acemessages.AceConst.START_PARAMS, self.params))
                    paramsdict['direct_url'] = self.path_unquoted
                    self.client.ace.START(self.reqtype, paramsdict, AceConfig.streamtype)
                elif self.reqtype == 'raw':
                    paramsdict = dict(zip(aceclient.acemessages.AceConst.START_PARAMS, self.params))
                    paramsdict['data'] = self.path_unquoted
                    self.client.ace.START(self.reqtype, paramsdict, AceConfig.streamtype)
                elif self.reqtype == 'efile':
                    self.client.ace.START(self.reqtype, {'efile_url':self.path_unquoted}, AceConfig.streamtype)

                logger.debug("START %s done %s" % (self.reqtype, self.path_unquoted))

                # Getting URL from engine
                if self.reqtype == 'infohash' or self.reqtype == 'torrent':
                     self.url = self.client.ace.getUrl(AceConfig.videotimeout*2)
                else:
                     self.url = self.client.ace.getUrl(AceConfig.videotimeout)
                # Rewriting host:port for remote Ace Stream Engine
                p = urlsplit(self.url)
                p = p._replace(netloc=AceConfig.acehost+':'+str(AceConfig.aceHTTPport))
                self.url = urlunsplit(p)

                logger.debug("Successfully get url %s from AceEngine!" % (self.url))
                self.errorhappened = False

            self.client.ace.play()

            self.hanggreenlet = gevent.spawn(self.hangDetector)
            logger.debug("hangDetector spawned")
            gevent.sleep()

            if not fmt:
                fmt = self.reqparams.get('fmt')[0] if 'fmt' in self.reqparams else None
                # Start translation
            self.client.handle(shouldStart, self.url, fmt, self.headers.dict)

        except (aceclient.AceException, requests.exceptions.RequestException) as e:
            logger.error("Exception: " + repr(e))
            self.errorhappened = True
            self.dieWithError()
        except gevent.GreenletExit:
            # hangDetector told us about client disconnection
            logger.debug('greenletExit')
            pass
        except Exception:
            # Unknown exception
            logger.error(traceback.format_exc())
            self.errorhappened = True
            self.dieWithError()
        finally:
            if not self.errorhappened and AceStuff.clientcounter.count(cid) == 1:
                # If no error happened and we are the only client
                try:
                    gevent.sleep() #VIDEO_DESTROY_DELAY
                except:
                    pass
            try:
                remaining = AceStuff.clientcounter.delete(cid, self.client)
                if self.client:
                   self.client.destroy()
                self.ace = None
                self.client = None
                logger.debug("END REQUEST")
            except:
                logger.error(traceback.format_exc())

    def getCid(self, reqtype, url):
        cid =''
        if  url.startswith('http') and (url.endswith('.acelive') or url.endswith('.torrent') or url.endswith('.acestream')):
            try:
                headers={'User-Agent': 'VLC/2.0.5 LibVLC/2.0.5','Range': 'bytes=0-','Connection': 'close','Icy-MetaData': '1'}
                f = b64encode(requests.get(url, headers=headers, stream = True, timeout=5).raw.read())
                headers={'User-Agent': 'Python-urllib/2.7','Content-Type': 'application/octet-stream', 'Connection': 'close'}
                cid = requests.post('http://api.torrentstream.net/upload/raw', data=f, headers=headers, timeout=5).json()['content_id']
            except:
                pass
            if cid == '':
                logging.debug("Failed to get ContentID from WEB API")
                try:
                   with AceStuff.clientcounter.lock:
                        if not AceStuff.clientcounter.idleace:
                           AceStuff.clientcounter.idleace = AceStuff.clientcounter.createAce()
                        cid = AceStuff.clientcounter.idleace.GETCID(reqtype, url)
                except:
                   logging.debug("Failed to get ContentID from engine")

        return None if not cid or cid == '' else cid

class HTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):

    def process_request(self, request, client_address):
        checkAce()
        SocketServer.ThreadingMixIn.process_request(self, request, client_address)

    def handle_error(self, request, client_address):
        #logging.debug(traceback.format_exc())
        pass


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

    def handle(self, shouldStart, url, fmt=None, req_headers=None):
        logger = logging.getLogger("ClientHandler")
        self.connectionTime = time.time()

        if shouldStart:
            self.ace._streamReaderState = 1
            gevent.spawn(self.ace.startStreamReader, url, self.cid, AceStuff.clientcounter, req_headers)
            gevent.sleep()

        with self.ace._lock:
            start = time.time()
            while self.handler.connected and self.ace._streamReaderState == 1:
                remaining = start + 5.0 - time.time()
                if remaining > 0:
                    self.ace._lock.wait(remaining)
                else:
                    logger.warning("Video stream not opened in 5 seconds - disconnecting")
                    self.handler.dieWithError()
                    return

            if self.handler.connected and self.ace._streamReaderState != 2:
                logger.warning("No video stream found")
                self.handler.dieWithError()
                return

        # Sending client headers to videostream
        if self.handler.connected:
            self.handler.send_response(self.ace._streamReaderConnection.status_code)
            FORWARD_HEADERS = ['Connection',
                               'Keep-Alive',
                               'Content-Range',
                               'Content-Type',
                               'X-Content-Duration',
                               'Content-Length',
                               ]
            SKIP_HEADERS = ['Server', 'Date', 'Transfer-Encoding', 'Accept-Ranges']
            response_headers = {}

            for k in self.ace._streamReaderConnection.headers:
                if k.split(':')[0] not in (FORWARD_HEADERS + SKIP_HEADERS):
                    logger.error('NEW HEADERS FOUND: %s' % k.split(':')[0])

            for h in FORWARD_HEADERS:
                if self.ace._streamReaderConnection.headers.get(h):
                    response_headers[h] = self.ace._streamReaderConnection.headers.get(h)
                    self.handler.send_header(h, self.ace._streamReaderConnection.headers.get(h))
            self.handler.end_headers()
            logger.debug('Sending HTTPAceProxy headers to client: %s' % response_headers )

        if AceConfig.transcode:

            if not fmt or not fmt in AceConfig.transcodecmd:
                fmt = 'default'

            if fmt in AceConfig.transcodecmd:
                stderr = None if AceConfig.loglevel == logging.DEBUG else DEVNULL
                popen_params = { "bufsize": AceConfig.readchunksize,
                                 "stdin"  : PIPE,
                                 "stdout" : self.handler.wfile,
                                 "stderr" : stderr,
                                 "shell"  : False }
                if AceConfig.osplatform == 'Windows':
                   # from msdn [1]
                   CREATE_NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
                   CREATE_NEW_PROCESS_GROUP = 0x00000200  # note: could get it from subprocess
                   DETACHED_PROCESS = 0x00000008          # 0x8 | 0x200 == 0x208
                   popen_params.update(creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)

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
            while self.handler.connected and self.ace._streamReaderState == 2:
                try:
                    data = self.getChunk(60.0)
                    if data and self.handler.connected:
                        try:
                            out.write(data)
                        except:
                            break
                    else:
                        break
                except Queue.Empty:
                    logger.warning("No data received in 60 seconds - disconnecting")
        finally:
            if transcoder:
               try:
                 transcoder.kill()
                 logger.warning("Ffmpeg transcoding stoped")
               except:
                 pass

    def addChunk(self, chunk, timeout):
        start = time.time()
        with self.lock:
            while(self.handler.connected and (len(self.queue) == AceConfig.readcachesize)):
                remaining = start + timeout + time.time()
                if remaining > 0:
                    self.lock.wait(remaining)
                else:
                    raise Queue.Full
            if self.handler.connected:
                self.queue.append(chunk)
                self.lock.notifyAll()

    def getChunk(self, timeout):
        start = time.time()
        with self.lock:
            while(self.handler.connected and (len(self.queue) == 0)):
                remaining = start + timeout - time.time()
                if remaining > 0:
                    self.lock.wait(remaining)
                else:
                    raise Queue.Empty
            if self.handler.connected:
                chunk = self.queue.popleft()
                self.lock.notifyAll()
                return chunk
            else:
                return None

    def destroy(self):
        with self.lock:
            self.handler.closeConnection()
            self.lock.notifyAll()
            self.queue.clear()

    def __eq__(self, other):
        return self is other

class AceStuff(object):
    '''
    Inter-class interaction class
    '''
# taken from http://stackoverflow.com/questions/2699907/dropping-root-permissions-in-python
def drop_privileges(uid_name, gid_name='nogroup'):

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
    old_umask = os.umask('077',8)

    if os.getuid() == running_uid and os.getgid() == running_gid:
        # could be useful
        os.environ['HOME'] = running_uid_home
        return True
    return False

# Spawning procedures
def spawnAce(cmd, delay=0):
    if AceConfig.osplatform == 'Windows':
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        try:
            key = _winreg.OpenKey(reg, 'Software\AceStream')
        except:
            logger.error("Can't find acestream!")
            sys.exit(1)
        engine = _winreg.QueryValueEx(key, 'EnginePath')
        AceStuff.acedir = os.path.dirname(engine[0])
        cmd = engine[0].split()
    try:
        AceStuff.ace = psutil.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        gevent.sleep(delay)
        return True
    except:
        return False

def checkAce():
    if AceConfig.acespawn and not isRunning(AceStuff.ace):
        AceStuff.clientcounter.destroyIdle()
        if hasattr(AceStuff, 'ace'):
            del AceStuff.ace
        if spawnAce(AceStuff.aceProc, 1):
            logger.error("Ace Stream died, respawned it with pid " + str(AceStuff.ace.pid))
            if AceConfig.osplatform == 'Windows':
                # Wait some time because ace engine refreshes the acestream.port file only after full loading...
                gevent.sleep(AceConfig.acestartuptimeout)
                detectPort()
        else:
            logger.error("Can't spawn Ace Stream!")
            clean_proc()
            sys.exit(1)
    else:
        try:
            with AceStuff.clientcounter.lock:
                 if not AceStuff.clientcounter.idleace:
                     AceStuff.clientcounter.idleace = AceStuff.clientcounter.createAce()
        except:
             logging.error("Failed to create Ace!")
        finally:
             logger.debug("AceStream alive on %s:%d" % (AceConfig.acehost, AceConfig.aceAPIport))

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
    import os.path
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    try:
        key = _winreg.OpenKey(reg, 'Software\AceStream')
    except:
        logger.error("Can't find AceStream!")
        sys.exit(1)
    engine = _winreg.QueryValueEx(key, 'EnginePath')
    AceStuff.acedir = os.path.dirname(engine[0])
    try:
        AceConfig.aceAPIport = int(open(AceStuff.acedir + '\\acestream.port', 'r').read())
        logger.info("Detected ace port: " + str(AceConfig.aceAPIport))
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
        except psutil.AccessDenied:
            # System process
            pass
        except psutil.NoSuchProcess:
            # Process terminated
            pass
    return None

def clean_proc():
    # Trying to close all spawned processes gracefully
    if AceConfig.acespawn and isRunning(AceStuff.ace):
        AceStuff.ace.terminate()
        gevent.sleep(1)
        if isRunning(AceStuff.ace):
            AceStuff.ace.kill()
        # for windows, subprocess.terminate() is just an alias for kill(), so we have to delete the acestream port file manually
        if AceConfig.osplatform == 'Windows' and os.path.isfile(AceStuff.acedir + '\\acestream.port'):
            os.remove(AceStuff.acedir + '\\acestream.port')

# This is what we call to stop the server completely
def shutdown(signum=0, frame=0):
    logger.info("Stopping server...")
    # Closing all client connections
    for connection in server.RequestHandlerClass.requestlist:
        try:
            # Set errorhappened to prevent waiting for videodestroydelay
            connection.errorhappened = True
            connection.closeConnection()
        except:
            logger.warning("Cannot kill a connection!")
    clean_proc()
    server.server_close()
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
    logger.info('Config reloaded')

logging.basicConfig(level=AceConfig.loglevel,
                    filename=AceConfig.logfile,
                    format=AceConfig.logfmt,
                    datefmt=AceConfig.logdatefmt)
logger = logging.getLogger('INIT')

#### Initial settings for AceEngine
AceConfig.acehost = AceConfig.acehostslist[0][0]
AceConfig.aceAPIport = AceConfig.acehostslist[0][1]
AceConfig.aceHTTPport = AceConfig.acehostslist[0][2]

### Initial settings for devnull
if AceConfig.acespawn or AceConfig.transcode:
   DEVNULL = open(os.devnull, 'wb')

#### Initial settings for AceHTTPproxy host IP
if AceConfig.httphost == '0.0.0.0':
   s = socket(AF_INET, SOCK_DGRAM)
   s.connect(("gmail.com",80))
   if s.getsockname()[0]:
     AceConfig.httphost = s.getsockname()[0]
     logger.debug('Ace Stream HTTP Proxy server IP: ' + AceConfig.httphost +' autodetected')
   s.close()

# Check whether we can bind to the defined port safely
if AceConfig.osplatform != 'Windows' and os.getuid() != 0 and AceConfig.httpport <= 1024:
    logger.error("Cannot bind to port " + str(AceConfig.httpport) + " without root privileges")
    sys.exit(1)

server = HTTPServer((AceConfig.httphost, AceConfig.httpport), HTTPHandler)
logger = logging.getLogger('HTTPServer')

logger.info("Ace Stream HTTP Proxy server starting ....")
logger.info("Using python %s" % sys.version.split(' ')[0])
logger.info("Using gevent %s" % gevent.__version__)
logger.info("Using psutil %s" % psutil.__version__)
logger.info("Using requests %s" % requests.__version__)
logger.info("Using bencode %s" % bencode_version__)
# Dropping root privileges if needed
if AceConfig.osplatform != 'Windows' and AceConfig.aceproxyuser and os.getuid() == 0:
    if drop_privileges(AceConfig.aceproxyuser):
        logger.info("Dropped privileges to user " + AceConfig.aceproxyuser)
    else:
        logger.error("Cannot drop privileges to user " + AceConfig.aceproxyuser)
        sys.exit(1)

# Creating ClientCounter
AceStuff.clientcounter = ClientCounter()

# setting signal handlers
try:
    gevent.signal(signal.SIGHUP, _reloadconfig)
    gevent.signal(signal.SIGTERM, shutdown)
except AttributeError:
    # not available on Windows
    pass

#### AceEngine startup
if AceConfig.osplatform == 'Windows':
     name = 'ace_engine.exe'
else:
     name = 'acestreamengine'
ace_pid = findProcess(name)
AceStuff.ace = None
if not ace_pid:
    if AceConfig.acespawn:
        if AceConfig.osplatform == 'Windows':
            import _winreg
            import os.path
            AceStuff.aceProc = ""
        else:
            AceStuff.aceProc = AceConfig.acecmd.split()
        if spawnAce(AceStuff.aceProc, 1):
            ace_pid = AceStuff.ace.pid
            AceStuff.ace = psutil.Process(ace_pid)
            logger.info("Ace Stream spawned with pid " + str(AceStuff.ace.pid))
else:
    AceStuff.ace = psutil.Process(ace_pid)

# Wait some time because ace engine refreshes the acestream.port file only after full loading...
if ace_pid and AceConfig.osplatform == 'Windows':
    gevent.sleep(AceConfig.acestartuptimeout)
    detectPort()

# Loading plugins
# Trying to change dir (would fail in freezed state)
try:
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
except:
    pass
# Creating dict of handlers
AceStuff.pluginshandlers = dict()
# And a list with plugin instances
AceStuff.pluginlist = list()
pluginsmatch = glob.glob('plugins/*_plugin.py')
sys.path.insert(0, 'plugins')
pluginslist = [os.path.splitext(os.path.basename(x))[0] for x in pluginsmatch]
for i in pluginslist:
    plugin = __import__(i)
    plugname = i.split('_')[0].capitalize()
    try:
        plugininstance = getattr(plugin, plugname)(AceConfig, AceStuff)
    except Exception as e:
        logger.error("Cannot load plugin " + plugname + ": " + repr(e))
        continue
    logger.debug('Plugin loaded: ' + plugname)
    for j in plugininstance.handlers:
        AceStuff.pluginshandlers[j] = plugininstance
    AceStuff.pluginlist.append(plugininstance)

# Start complite. Wating for requests
try:
    logger.info("Server started and waiting for requests at " + str(AceConfig.httphost) + ":" + str(AceConfig.httpport))
    while True:
        server.handle_request()
except (KeyboardInterrupt, SystemExit):
    shutdown()
