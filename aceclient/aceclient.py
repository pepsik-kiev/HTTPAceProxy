# -*- coding: utf-8 -*-
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
from gevent.event import AsyncResult, Event
import traceback
import telnetlib
import logging
import requests
import json
import time
import random

from aceconfig import AceConfig
from .acemessages import *

class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class Telnet(telnetlib.Telnet, object):

    if AceConfig.PyVersion == '3':
        def read_until(self, expected, timeout=None):
            expected = bytes(expected, encoding='utf-8')
            received = super(Telnet, self).read_until(expected, timeout)
            return str(received, encoding='utf-8')

        def write(self, buffer):
            buffer = bytes(buffer, encoding='utf-8')
            super(Telnet, self).write(buffer)


class AceClient(object):

    def __init__(self, acehostslist, connect_timeout=5, result_timeout=10):
        # Receive buffer
        self._recvbuffer = None
        # Ace stream socket
        self._socket = None
        # Result timeout
        self._resulttimeout = float(result_timeout)
        # Shutting down flag
        self._shuttingDown = Event()
        # Product key
        self._product_key = None
        # Current STATUS
        self._status = None
        # Current AUTH
        self._authevent = Event()
        self._gender = None
        self._age = None
        # Result (Created with AsyncResult() on call)
        self._result = AsyncResult()
        # Result for getURL()
        self._urlresult = AsyncResult()
        # Result for GETCID()
        self._cidresult = AsyncResult()
        # Seekback seconds.
        self._seekback = None
        # Did we get START command again? For seekback.
        self._started_again = Event()

        self._idleSince = time.time()
        self._streamReaderConnection = None
        self._streamReaderState = Event()
        self._CHUNK_NUM = 1024 # Max number of chunks in queue
        self._streamReaderQueue = gevent.queue.Queue(maxsize=self._CHUNK_NUM) # Ring buffer
        self._engine_version_code = None

        # Logger
        logger = logging.getLogger('AceClient')
        # Try to connect AceStream engine
        for AceEngine in acehostslist:
           try:
               self._socket = Telnet(AceEngine[0], AceEngine[1], connect_timeout)
               AceConfig.acehost, AceConfig.aceAPIport, AceConfig.aceHTTPport = AceEngine[0], AceEngine[1], AceEngine[2]
               logger.debug('Successfully connected to AceStream on %s:%d' % (AceEngine[0], AceEngine[1]))
               break
           except:
               logger.debug('The are no alive AceStream on %s:%d' % (AceEngine[0], AceEngine[1]))
               pass
        # Spawning recvData greenlet
        if self._socket: gevent.spawn(self._recvData)
        else: logger.error('The are no alive AceStream Engines found'); return

    def destroy(self):
        '''
        AceClient Destructor
        '''
        if self._shuttingDown.ready(): return   # Already in the middle of destroying

        logger = logging.getLogger('AceClient_destroy') # Logger

        self._urlresult.set()   # And to prevent getUrl deadlock

        # Trying to disconnect
        try:
            logger.debug('Destroying AceStream client.....')
            self._shuttingDown.set()
            self._write(AceMessage.request.SHUTDOWN)
        except: pass # Ignore exceptions on destroy
        finally: self._shuttingDown.set()

    def reset(self):
        self._idleSince = time.time()
        self._started_again.clear()
        self._streamReaderState.clear()

    def _write(self, message):
        try:
            logger = logging.getLogger('AceClient_write')
            logger.debug('>>> %s' % message)
            self._socket.write( '{}\r\n'.format(message) )
        except EOFError as e: raise AceException('Write error! %s' % repr(e))

    def aceInit(self, gender=AceConst.SEX_MALE, age=AceConst.AGE_25_34, product_key=AceConfig.acekey):
        self._product_key = product_key
        self._gender = gender
        self._age = age
        self._seekback = AceConfig.videoseekback
        self._started_again.clear()
        self._authevent.clear()

        logger = logging.getLogger('AceClient_aceInit')
        self._write(AceMessage.request.HELLO) # Sending HELLOBG

        if not self._authevent.wait(timeout=self._resulttimeout):
            errmsg = 'Authentication timeout during AceEngine init! Wrong acekey?' # HELLOTS not resived from engine or Wrong key!
            raise AceException(errmsg)
            return
        # Display download_stopped massage
        if self._engine_version_code >= 3003600: self._write(AceMessage.request.SETOPTIONS)

    def _getResult(self):
        logger = logging.getLogger('AceClient_getResult') # Logger
        try: return self._result.get(timeout=self._resulttimeout)
        except gevent.Timeout:
            errmsg = 'Engine response time exceeded. getResult timeout from %s:%s' % (AceConfig.acehost, AceConfig.aceAPIport)
            raise AceException(errmsg)

    def getUrl(self, timeout=30.0):
        logger = logging.getLogger('AceClient_getURL') # Logger
        try: return self._urlresult.get(timeout=timeout)
        except gevent.Timeout:
            errmsg = 'Engine response time exceeded. GetURL timeout from %s:%s' % (AceConfig.acehost, AceConfig.aceAPIport)
            raise AceException(errmsg)

    def START(self, datatype, value, stream_type):
        '''
        Start video method
        Returns the url provided by AceEngine
        '''
        if stream_type == 'hls' and self._engine_version_code >= 3010500:
           stream_type = 'output_format=hls transcode_audio=%s transcode_mp3=%s transcode_ac3=%s preferred_audio_language=%s' % \
                         (AceConfig.transcode_audio, AceConfig.transcode_mp3, AceConfig.transcode_ac3, AceConfig.preferred_audio_language)
        else: stream_type = 'output_format=http'

        self._urlresult = AsyncResult()
        self._write(AceMessage.request.START(datatype.upper(), value, stream_type))
        return self.getUrl(timeout=float(AceConfig.videotimeout)) #url for play

    def STOP(self):
        '''
        Stop video method
        '''
        self._result = AsyncResult()
        self._write(AceMessage.request.STOP)
        self._getResult()

    def LOADASYNC(self, datatype, params):
        self._result = AsyncResult()
        self._write(AceMessage.request.LOADASYNC(datatype.upper(), random.randint(1, AceConfig.maxconns * 10000), params))
        return self._getResult() # _contentinfo or False

    def GETCONTENTINFO(self, datatype, value):
        paramsdict = { datatype:value, 'developer_id':'0', 'affiliate_id':'0', 'zone_id':'0' }
        return self.LOADASYNC(datatype, paramsdict)

    def GETCID(self, datatype, url):
        contentinfo = self.GETCONTENTINFO(datatype, url)
        cid = None
        if contentinfo:
           self._cidresult = AsyncResult()
           self._write(AceMessage.request.GETCID(contentinfo.get('checksum'), contentinfo.get('infohash'), '0', '0', '0'))
           cid = self._cidresult.get(block=True, timeout=5.0)
        return '' if cid is None or cid == '' else cid[2:]

    def startStreamReader(self, url, cid, counter, req_headers=None):
        logger = logging.getLogger('StreamReader')
        logger.debug('Open video stream: %s' % url)
        transcoder = None

        if 'range' in req_headers: del req_headers['range']
        logger.debug('Get headers from client: %s' % req_headers)

        with requests.get(url, headers=req_headers, stream=True, timeout=(5, AceConfig.videotimeout)) as self._streamReaderConnection:
          try:
              self._streamReaderConnection.raise_for_status() # raise an exception for error codes (4xx or 5xx)

              if url.endswith('.m3u8'):
                 self._streamReaderConnection.headers = {'Content-Type': 'application/octet-stream', 'Connection': 'Keep-Alive', 'Keep-Alive': 'timeout=15, max=100'}
                 popen_params = { "bufsize": requests.models.CONTENT_CHUNK_SIZE,
                                  "stdout" : gevent.subprocess.PIPE,
                                  "stderr" : None,
                                  "shell"  : False }

                 if AceConfig.osplatform == 'Windows':
                       ffmpeg_cmd = 'ffmpeg.exe '
                       CREATE_NO_WINDOW = 0x08000000
                       CREATE_NEW_PROCESS_GROUP = 0x00000200
                       DETACHED_PROCESS = 0x00000008
                       popen_params.update(creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
                 else: ffmpeg_cmd = 'ffmpeg '

                 ffmpeg_cmd += '-hwaccel auto -hide_banner -loglevel fatal -re -i %s -c copy -f mpegts -' % url
                 transcoder = gevent.subprocess.Popen(ffmpeg_cmd.split(), **popen_params)
                 out = transcoder.stdout
                 logger.warning('HLS stream detected. Ffmpeg transcoding started')
              else: out = self._streamReaderConnection.raw

              self._streamReaderState.set()
              self.play_event()

              while 1:
                 gevent.sleep()
                 clients = counter.getClients(cid)
                 if clients:
                     try:
                         data = out.read(requests.models.CONTENT_CHUNK_SIZE)
                         try: self._streamReaderQueue.put_nowait(data)
                         except gevent.queue.Full:
                              self._streamReaderQueue.get_nowait()
                              self._streamReaderQueue.put_nowait(data)
                     except requests.packages.urllib3.exceptions.ReadTimeoutError:
                         logger.warning('No data received from AceEngine for %ssec - broadcast stoped' % AceConfig.videotimeout); break
                     except: break
                     else:
                         for c in clients:
                            try: c.queue.put(data, timeout=5)
                            except gevent.queue.Full:  #Queue.Full client does not read data from buffer until 5sec - disconnect it
                                if len(clients) > 1:
                                    logger.debug('Disconnecting client: %s' % c.handler.clientip)
                                    c.destroy()
                            except gevent.GreenletExit: pass

                 else: logger.debug('All clients disconnected - broadcast stoped'); break

          except requests.exceptions.HTTPError as err:
                logger.error('An http error occurred while connecting to aceengine: %s' % repr(err))
          except requests.exceptions.RequestException:
                logger.error('There was an ambiguous exception that occurred while handling request')
          except:
                logger.error('Unexpected error in streamreader')
                logger.error(traceback.format_exc())
          finally:
                self.closeStreamReader()
                self._streamReaderState.clear()
                if transcoder:
                   try: transcoder.kill(); logger.warning('Ffmpeg transcoding stoped')
                   except: pass
                counter.deleteAll(cid)

    def closeStreamReader(self):
        logger = logging.getLogger('StreamReader')
        c = self._streamReaderConnection
        if c:
           logger.debug('Close video stream: %s' % c.url)
           c.close()
        self._streamReaderConnection = None
        self._streamReaderQueue.queue.clear()

    # EVENTS from client to AceEngine
    def play_event(self): self._write(AceMessage.request.PLAYEVENT)
    def pause_event(self): self._write(AceMessage.request.PAUSEEVENT)
    def stop_event(self): self._write(AceMessage.request.STOPEVENT)
    # END EVENTS

    def _recvData(self):
        '''
        Data receiver method for greenlet
        '''
        logger = logging.getLogger('AceClient_recvdata')

        while 1:
            gevent.sleep()
            try:
                self._recvbuffer = self._socket.read_until('\r\n').strip()
                logger.debug('<<< %s' % requests.compat.unquote(self._recvbuffer))
            except:
                # If something happened during read, abandon reader.
                logger.error('Exception at socket read. AceClient destroyed')
                if not self._shuttingDown.ready(): self._shuttingDown.set()
                return
            else: # Parsing everything only if the string is not empty
                # HELLOTS
                if self._recvbuffer.startswith(AceMessage.response.HELLO):
                    try: params = { k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) }
                    except: params = {}; raise AceException("Can't parse HELLOTS")
                    self._engine_version_code = int(params.get('version_code', 0))
                    self._write(AceMessage.request.READY_key(params.get('key',''), self._product_key))
                # NOTREADY
                elif self._recvbuffer.startswith(AceMessage.response.NOTREADY): self._authevent.clear()
                # AUTH
                elif self._recvbuffer.startswith(AceMessage.response.AUTH): self._authevent.set()
                # GETUSERDATA
                elif self._recvbuffer.startswith(AceMessage.response.GETUSERDATA):
                    self._write(AceMessage.request.USERDATA(self._gender, self._age))
                # START
                elif self._recvbuffer.startswith(AceMessage.response.START):
                    try: params = { k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) }
                    except: params = {}; raise AceException("Can't parse START")
                    if not self._seekback or (self._seekback and self._started_again.ready()) or params.get('stream','') is not '1':
                        # If seekback is disabled, we use link in first START command.
                        # If seekback is enabled, we wait for first START command and
                        # ignore it, then do seekback in first EVENT position command
                        # AceStream sends us STOP and START again with new link.
                        # We use only second link then.
                        self._urlresult.set(self._recvbuffer.split()[1])
                        self._started_again.clear()
                    else: logger.debug('START received. Waiting for %s.' % AceMessage.response.LIVEPOS)
                # LIVEPOS
                if self._recvbuffer.startswith(AceMessage.response.LIVEPOS):
                    if self._seekback and not self._started_again.ready(): # if seekback
                        try:
                             params = { k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) }
                             self._write(AceMessage.request.LIVESEEK(int(params['last']) - self._seekback))
                             self._started_again.set()
                        except: raise AceException("Can't parse %s" % AceMessage.response.LIVEPOS)
                # LOADRESP
                elif self._recvbuffer.startswith(AceMessage.response.LOADRESP):
                    _contentinfo = json.loads(requests.compat.unquote(' '.join(self._recvbuffer.split()[2:])))
                    if _contentinfo.get('status') == 100:
                        logger.error('LOADASYNC returned error with message: %s' % _contentinfo.get('message'))
                        self._result.set(False)
                    else: self._result.set(_contentinfo)
                # STATE
                elif self._recvbuffer.startswith(AceMessage.response.STATE):
                    if self._recvbuffer.split()[1] in ('0', '1'): self._result.set(True)
                # STATUS
                elif self._recvbuffer.startswith(AceMessage.response.STATUS):
                    self._status = self._recvbuffer.split()[1].split(';')
                    if 'main:err' in self._status: # main:err;error_id;error_message
                       logger.error('%s with message %s' % (self._status[0], self._status[2]))
                       self._result.set_exception(AceException('%s with message %s' % (self._status[0], self._status[2])))
                       self._urlresult.set_exception(AceException('%s with message %s' % (self._status[0], self._status[2])))
                # CID
                elif self._recvbuffer.startswith('##') or not self._recvbuffer: self._cidresult.set(self._recvbuffer)
                # PAUSE
                elif self._recvbuffer.startswith(AceMessage.response.PAUSE): self.pause_event()
                # RESUME
                elif self._recvbuffer.startswith(AceMessage.response.RESUME): self.play_event()
                # SHUTDOWN
                elif self._recvbuffer.startswith(AceMessage.response.SHUTDOWN):
                    self._socket.close()
                    logger.debug('AceClient destroyed')
                    return
