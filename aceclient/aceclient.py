# -*- coding: utf-8 -*-
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import traceback
import gevent, gevent.queue
from gevent.event import AsyncResult, Event
from gevent.subprocess import Popen, PIPE
import telnetlib
from socket import SHUT_WR
import logging
import requests
import json
import time
import threading
import random

from aceconfig import AceConfig
from acemessages import *

class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class AceClient(object):

    def __init__(self, acehostslist, connect_timeout=5, result_timeout=10):
        # Receive buffer
        self._recvbuffer = None
        # Stream URL
        self._url = None
        # Ace stream socket
        self._socket = None
        # Result timeout
        self._resulttimeout = result_timeout
        # Shutting down flag
        self._shuttingDown = Event()
        # Product key
        self._product_key = None
        # Current STATUS
        self._status = None
        # Current STATE
        self._state = None
        # Current video position
        self._position = None
        # Available video position (loaded data)
        self._position_last = None
        # Buffered video pieces
        self._position_buf = None
        # Current AUTH
        self._auth = None
        self._gender = None
        self._age = None
        # Result (Created with AsyncResult() on call)
        self._result = AsyncResult()
        self._authevent = Event()
        # Result for getURL()
        self._urlresult = AsyncResult()
        # Result for GETCID()
        self._cidresult = AsyncResult()
        # Event for resuming from PAUSE
        self._resumeevent = Event()
        # Seekback seconds.
        self._seekback = AceConfig.videoseekback
        # Did we get START command again? For seekback.
        self._started_again = False

        self._idleSince = time.time()
        self._streamReaderConnection = None
        self._streamReaderState = None
        self._lock = threading.Condition(threading.Lock())
        self._streamReaderQueue = gevent.queue.Queue(maxsize=AceConfig.readcachesize) # Ring buffer
        self._engine_version_code = None

        # Logger
        logger = logging.getLogger('AceClientimport tracebacknt_init')
        # Try to connect AceStream engine
        for AceEngine in acehostslist:
           try:
               self._socket = telnetlib.Telnet(AceEngine[0], AceEngine[1], connect_timeout)
               AceConfig.acehost, AceConfig.aceAPIport, AceConfig.aceHTTPport = AceEngine[0], AceEngine[1], AceEngine[2]
               logger.debug('Successfully connected to AceStream on %s:%d' % (AceEngine[0], AceEngine[1]))
               break
           except:
               logger.debug('The are no alive AceStream on %s:%d' % (AceEngine[0], AceEngine[1]))
               pass
        # Spawning recvData greenlet
        if self._socket is not None: self.hanggreenlet = gevent.spawn(self._recvData); gevent.sleep()
        else: logger.error('The are no alive AceStream Engines found'); return

    def destroy(self):
        '''
        AceClient Destructor
        '''
        logger = logging.getLogger('AceClient_destroy') # Logger

        if self._shuttingDown.isSet():   # Already in the middle of destroying
            self._socket = None
            self.hanggreenlet.kill()
            return

        self._resumeevent.set() # We should resume video to prevent read greenlet deadlock
        self._urlresult.set()   # And to prevent getUrl deadlock

        # Trying to disconnect
        try:
            logger.debug('Destroying AceStream client.....')
            self._shuttingDown.set()
            self._write(AceMessage.request.SHUTDOWN)
        except: pass # Ignore exceptions on destroy
        finally: self._shuttingDown.set()

    def reset(self):
        self._started_again = False
        self._idleSince = time.time()
        self._streamReaderState = None

    def _write(self, message):
        try:
            logger = logging.getLogger('AceClient_write')
            logger.debug('>>> %s' % message)
            self._socket.write('%s\r\n' % message )
        except EOFError as e: raise AceException('Write error! %s' % repr(e))

    def aceInit(self, gender=AceConst.SEX_MALE, age=AceConst.AGE_25_34, product_key=AceConfig.acekey):
        self._product_key = product_key
        self._gender = gender
        self._age = age
        self._seekback = AceConfig.videoseekback
        self._started_again = False

        logger = logging.getLogger('AceClient_aceInit')
        self._write(AceMessage.request.HELLO) # Sending HELLOBG

        if not self._authevent.wait(self._resulttimeout):
            errmsg = 'Authentication timeout during AceEngine init!' # HELLOTS not resived from engine or Wrong key!
            logger.error(errmsg)
            raise AceException(errmsg)
            return

        if self._auth is None:
            errmsg = 'User data error! Check "aceage" and "acesex" parameters in aceconfig.py!' # Error while sending USERDATA to engine
            logger.error(errmsg)
            raise AceException(errmsg)
            return
        # Display download_stopped massage
        if self._engine_version_code >= 3003600: self._write(AceMessage.request.SETOPTIONS)

    def _getResult(self):
        try:
            result = self._result.get(timeout=self._resulttimeout)
            if not result:
                raise AceException('Result not received from %s:%s' % (AceConfig.acehost, AceConfig.aceAPIport))
        except gevent.Timeout: raise AceException('gevent_Timeout')
        return result

    def START(self, datatype, value, stream_type):
        '''
        Start video method
        '''
        if stream_type == 'hls' and self._engine_version_code >= 3010500:
           stream_type = 'output_format=hls transcode_audio=%s transcode_mp3=%s transcode_ac3=%s preferred_audio_language=%s' % \
                         (AceConfig.transcode_audio, AceConfig.transcode_mp3, AceConfig.transcode_ac3, AceConfig.preferred_audio_language)
        else: stream_type = 'output_format=http'

        self._urlresult = AsyncResult()
        self._write(AceMessage.request.START(datatype.upper(), value, stream_type))
        self._getResult()

    def STOP(self):
        '''
        Stop video method
        '''
        if self._state and self._state != '0':
            self._result = AsyncResult()
            self._write(AceMessage.request.STOP)
            self._getResult()

    def LOADASYNC(self, datatype, params):
        self._result = AsyncResult()
        self._write(AceMessage.request.LOADASYNC(datatype.upper(), random.randint(1, AceConfig.maxconns * 10000), params))
        return self._getResult()

    def GETCONTENTINFO(self, datatype, value):
        paramsdict = { datatype:value, 'developer_id':'0', 'affiliate_id':'0', 'zone_id':'0' }
        return self.LOADASYNC(datatype, paramsdict)

    def GETCID(self, datatype, url):
        contentinfo = self.GETCONTENTINFO(datatype, url)
        self._cidresult = AsyncResult()
        self._write(AceMessage.request.GETCID(contentinfo.get('checksum'), contentinfo.get('infohash'), 0, 0, 0))
        cid = self._cidresult.get(True, 5)
        return '' if not cid or cid == '' else cid[2:]

    def getUrl(self, timeout=30):
        logger = logging.getLogger('AceClient_getURL') # Logger
        try:
            res = self._urlresult.get(timeout=timeout)
            return res
        except gevent.Timeout:
            errmsg = 'Engine response time exceeded. GetURL timeout!'
            logger.error(errmsg)
            raise AceException(errmsg)

    def startStreamReader(self, url, cid, counter, req_headers=None):
        logger = logging.getLogger('StreamReader')
        logger.debug('Open video stream: %s' % url)
        self._streamReaderState = 1
        transcoder = None

        if 'range' in req_headers: del req_headers['range']
        logger.debug('Get headers from client: %s' % req_headers)

        try:
          self._streamReaderConnection = requests.get(url, headers=req_headers, stream=True, timeout=(5, 60))
          self._streamReaderConnection.raise_for_status() # raise an exception for error codes (4xx or 5xx)

          if url.endswith('.m3u8'):
              self._streamReaderConnection.headers = {'Content-Type': 'application/octet-stream', 'Connection': 'Keep-Alive', 'Keep-Alive': 'timeout=15, max=100'}
              popen_params = { "bufsize": AceConfig.readchunksize,
                               "stdout" : PIPE,
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
              transcoder = Popen(ffmpeg_cmd.split(), **popen_params)
              out = transcoder.stdout
              logger.warning('HLS stream detected. Ffmpeg transcoding started')
          else: out = self._streamReaderConnection.raw

          with self._lock: self._streamReaderState = 2; self._lock.notifyAll()
          self.play_event()

          while 1:
              self.getPlayEvent() # Wait for PlayEvent (stop/resume sending data from AceEngine to streamReaderQueue)
              clients = counter.getClients(cid)
              try: data = out.read(AceConfig.readchunksize)
              except: data = None
              if data is not None and clients:
                  self._streamReaderQueue.get() if self._streamReaderQueue.full() else self._streamReaderQueue.put(data)
                  for c in clients:
                      try: c.queue.put(data, timeout=5)
                      except gevent.queue.Full:  #Queue.Full client does not read data from buffer until 5sec - disconnect it
                          if len(clients) > 1:
                              logger.debug('Disconnecting client: %s' % c.handler.clientip)
                              c.destroy()
              elif counter.count(cid) == 0: logger.debug('All clients disconnected - broadcast stoped'); break
              else: logger.warning('No data received - broadcast stoped'); counter.deleteAll(cid); break

        except requests.exceptions.HTTPError as err:
              logger.error('An http error occurred while connecting to aceengine: %s' % err)
        except requests.exceptions.ConnectTimeout:
              logger.error('The request timed out while trying to connect to %s' % url)
        except requests.exceptions.ReadTimeout:
              logger.error('The aceengine did not send any data in 60sec')
        except requests.exceptions.RequestException:
              logger.error('There was an ambiguous exception that occurred while handling request to %s' % url)
        except:
              logger.error('Unexpected error in streamreader')
              logger.error(traceback.format_exc())

        finally:
              with self._lock: self._streamReaderState = None; self._lock.notifyAll()
              if transcoder is not None:
                 try: transcoder.kill(); logger.warning('Ffmpeg transcoding stoped')
                 except: pass

    def closeStreamReader(self):
        logger = logging.getLogger('StreamReader')
        c = self._streamReaderConnection
        if c:
           logger.debug('Close video stream: %s' % c.url)
           c.close()
           self._streamReaderConnection = None
        self._streamReaderQueue.queue.clear()

    def getPlayEvent(self, timeout=None):
        '''
        Blocking while in PAUSE, non-blocking while in RESUME
        '''
        return self._resumeevent.wait(timeout=timeout)

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
                logger.debug('<<< %s' % requests.compat.unquote(self._recvbuffer).decode('utf8'))
            except:
                # If something happened during read, abandon reader.
                logger.error('Exception at socket read. AceClient destroyed')
                if not self._shuttingDown.isSet(): self._shuttingDown.set()
                self._socket = None
                self.hanggreenlet.kill()
                return
            else:
                # Parsing everything only if the string is not empty

                # HELLOTS
                if self._recvbuffer.startswith(AceMessage.response.HELLO):
                    try: params = { k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) }
                    except: logger.error("Can't parse HELLOTS"); params = {}
                    self._engine_version_code = params['version_code'] if 'version_code' in params else None
                    if 'key' in params:
                        self._write(AceMessage.request.READY_key(params['key'], self._product_key))
                        self._request_key = None
                    else: self._write(AceMessage.request.READY_nokey)
                # NOTREADY
                elif self._recvbuffer.startswith(AceMessage.response.NOTREADY):
                    self._auth = None
                    self._authevent.set()
                    logger.error('AceEngine is not ready. Wrong auth?')
                # AUTH
                elif self._recvbuffer.startswith(AceMessage.response.AUTH):
                    try:
                        self._auth = self._recvbuffer.split()[1]
                        self._write(AceMessage.request.USERDATA(self._gender, self._age))
                    except: self._auth = None; pass
                    else: self._authevent.set()
                # GETUSERDATA
                elif self._recvbuffer.startswith(AceMessage.response.GETUSERDATA):
                    raise AceException('You should init me first!')
                # LOADRESP
                elif self._recvbuffer.startswith(AceMessage.response.LOADRESP):
                    _contentinfo = json.loads(requests.compat.unquote(' '.join(self._recvbuffer.split()[2:])).decode('utf8'))
                    if _contentinfo.get('status') == 100:
                        logger.error('LOADASYNC returned error with message: %s' % _contentinfo.get('message'))
                        self._result.set(False)
                    else: self._result.set(_contentinfo)
                # START
                elif self._recvbuffer.startswith(AceMessage.response.START):
                    if not self._seekback or self._started_again or not self._recvbuffer.endswith(' stream=1'):
                        # If seekback is disabled, we use link in first START command.
                        # If seekback is enabled, we wait for first START command and
                        # ignore it, then do seekback in first EVENT position command
                        # AceStream sends us STOP and START again with new link.
                        # We use only second link then.
                        try:
                            self._urlresult.set(self._recvbuffer.split()[1])
                            self._resumeevent.set()
                        except IndexError as e: self._url = None
                    else: logger.debug('START received. Waiting for %s.' % AceMessage.response.LIVEPOS)
                # STATE
                elif self._recvbuffer.startswith(AceMessage.response.STATE):
                    self._state = self._recvbuffer.split()[1]
                    if self._state in ('0','1'): self._result.set(True) #idle, starting
                    elif self._state == '6': self._result.set(False) # error
                # STATUS
                elif self._recvbuffer.startswith(AceMessage.response.STATUS):
                    self._status = self._recvbuffer.split()[1].split(';')
                    if 'main:err' in set(self._status):  # main:err;error_id;error_message
                       logger.error('%s with message %s' % (self._status[0], self._status[2]))
                       self._result.set_exception(AceException('%s with message %s' % (self._status[0], self._status[2])))
                       self._urlresult.set_exception(AceException('%s with message %s' % (self._status[0], self._status[2])))
                # LIVEPOS
                elif self._recvbuffer.startswith(AceMessage.response.LIVEPOS):
                    if self._seekback and not self._started_again:
                        try:
                             params = { k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) }
                             self._write(AceMessage.request.LIVESEEK(int(params['last']) - self._seekback))
                             logger.debug('Seeking back..<<..')
                             self._started_again = True
                        except: logger.error("Can't parse %s" % AceMessage.response.LIVEPOS)
                # CID
                elif self._recvbuffer.startswith('##') or len(self._recvbuffer) == 0: self._cidresult.set(self._recvbuffer)
                #DOWNLOADSTOP
                elif self._recvbuffer.startswith(AceMessage.response.DOWNLOADSTOP): pass
                # INFO
                elif self._recvbuffer.startswith(AceMessage.response.INFO): pass
                # SHOWURL
                elif self._recvbuffer.startswith(AceMessage.response.SHOWURL): pass
                # CANSAVE
                elif self._recvbuffer.startswith(AceMessage.response.CANSAVE): pass
                # PAUSE
                elif self._recvbuffer.startswith(AceMessage.response.PAUSE): self.pause_event(); self._resumeevent.clear()
                # RESUME
                elif self._recvbuffer.startswith(AceMessage.response.RESUME): self.play_event(); self._resumeevent.set()
                # STOP
                elif self._recvbuffer.startswith(AceMessage.response.STOP): pass
                # SHUTDOWN
                elif self._recvbuffer.startswith(AceMessage.response.SHUTDOWN):
                    self._socket.get_socket().shutdown(SHUT_WR)
                    self._recvbuffer = self._socket.read_all()
                    self._socket.close()
                    self._socket = None
                    self.hanggreenlet.kill()
                    logger.debug('AceClient destroyed')
        return
