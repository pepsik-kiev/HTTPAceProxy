# -*- coding: utf-8 -*-
from aceconfig import AceConfig
from acemessages import *
import gevent
from gevent.event import AsyncResult
from gevent.event import Event
import telnetlib
import logging
import requests
import json
import time
import threading
import traceback
import random
import psutil
import Queue
from subprocess import PIPE
from collections import deque


class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class AceClient(object):

    def __init__(self, acehost, aceAPIport, aceHTTPport, acehostslist, connect_timeout=5, result_timeout=10):
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
        self._lock = threading.Condition(threading.Lock())
        self._streamReaderConnection = None
        self._streamReaderState = None
        self._streamReaderQueue = deque()
        self._engine_version_code = 0

        # Logger
        logger = logging.getLogger('AceClientimport tracebacknt_init')

        # Try to connect AceStream engine
        try:
            self._socket = telnetlib.Telnet(acehost, aceAPIport, connect_timeout)
            AceConfig.acehost, AceConfig.aceAPIport, AceConfig.aceHTTPport = acehost, aceAPIport, aceHTTPport
            logger.debug("Successfully connected to AceStream on %s:%d" % (acehost, aceAPIport))
        except:
            for AceEngine in acehostslist:
               try:
                   self._socket = telnetlib.Telnet(AceEngine[0], AceEngine[1], connect_timeout)
                   AceConfig.acehost, AceConfig.aceAPIport, AceConfig.aceHTTPport = AceEngine[0], AceEngine[1], AceEngine[2]
                   logger.debug("Successfully connected to AceStream on %s:%d" % (AceEngine[0], AceEngine[1]))
                   break
               except:
                   logger.debug("The are no alive AceStream on %s:%d" % (AceEngine[0], AceEngine[1]))
                   pass

        # Spawning recvData greenlet
        if self._socket: gevent.spawn(self._recvData); gevent.sleep()
        else: logger.error("The are no alive AceStream Engines found"); return

    def destroy(self):
        '''
        AceClient Destructor
        '''
        if self._shuttingDown.isSet(): return # Already in the middle of destroying

        logger = logging.getLogger("AceClient_destroy") # Logger
        self._resumeevent.set() # We should resume video to prevent read greenlet deadlock
        self._urlresult.set()   # And to prevent getUrl deadlock

        # Trying to disconnect
        try:
            logger.debug("Destroying AceStream client ...")
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
            logger = logging.getLogger("AceClient_write")
            logger.debug(message)
            self._socket.write(message + "\r\n")
        except EOFError as e: raise AceException("Write error! " + repr(e))

    def aceInit(self, gender=AceConst.SEX_MALE, age=AceConst.AGE_25_34, product_key=AceConfig.acekey):
        self._product_key = product_key
        self._gender = gender
        self._age = age
        self._seekback = AceConfig.videoseekback

        logger = logging.getLogger("AceClient_aceInit")
        self._write(AceMessage.request.HELLO) # Sending HELLOBG

        if not self._authevent.wait(self._resulttimeout):
            errmsg = "Authentication timeout. Wrong key?" # HELLOTS not resived from engine
            logger.error(errmsg)
            raise AceException(errmsg)
            return

        if not self._auth:
            errmsg = "Authentication error. Wrong key?"
            logger.error(errmsg)
            raise AceException(errmsg)
            return

        logger.debug("AceInit ended")

    def _getResult(self):
        try:
            result = self._result.get(timeout=self._resulttimeout)
            if not result:
                raise AceException("Result not received from %s:%s" % (AceConfig.acehost, AceConfig.aceAPIport))
        except gevent.Timeout: raise AceException("gevent_Timeout")
        return result

    def START(self, datatype, value, stream_type):
        '''
        Start video method
        '''
        if stream_type == 'hls':
           stream_type = 'output_format=hls' + ' transcode_audio=' + str(AceConfig.transcode_audio) \
                                             + ' transcode_mp3=' + str(AceConfig.transcode_mp3) \
                                             + ' transcode_ac3=' + str(AceConfig.transcode_ac3) \
                                             + ' preferred_audio_language=' + AceConfig.preferred_audio_language
        else: stream_type = 'output_format=http'

        self._urlresult = AsyncResult()
        self._write(AceMessage.request.START(datatype.upper(), value, stream_type))
        self._getResult()

    def STOP(self):
        '''
        Stop video method
        '''
        if self._state is not None and self._state != '0':
            self._result = AsyncResult()
            self._write(AceMessage.request.STOP)
            self._getResult()

    def LOADASYNC(self, datatype, params):
        self._result = AsyncResult()
        self._write(AceMessage.request.LOADASYNC(datatype.upper(), random.randint(1, AceConfig.maxconns * 10000), params))
        return self._getResult()

    def CONTENTINFO(self, datatype, value):
        dict = {'torrent': 'url', 'infohash':'infohash', 'raw':'data', 'pid':'content_id'}
        paramsdict = {dict[datatype]:value,'developer_id':'0','affiliate_id':'0','zone_id':'0'}
        return self.LOADASYNC(datatype, paramsdict)

    def GETCID(self, datatype, url):
        contentinfo = self.CONTENTINFO(datatype, url)
        self._cidresult = AsyncResult()
        self._write(AceMessage.request.GETCID(contentinfo.get('checksum'), contentinfo.get('infohash'), 0, 0, 0))
        cid = self._cidresult.get(True, 5)
        return '' if not cid or cid == '' else cid[2:]

    def GETINFOHASH(self, datatype, url):
        infohash = self.CONTENTINFO(datatype, url).get('infohash')
        return '' if not infohash or infohash == '' else infohash

    def getUrl(self, timeout=30):
        logger = logging.getLogger("AceClient_getURL") # Logger
        try:
            res = self._urlresult.get(timeout=timeout)
            return res
        except gevent.Timeout:
            errmsg = "Engine response time exceeded. GetURL timeout!"
            logger.error(errmsg)
            raise AceException(errmsg)

    def startStreamReader(self, url, cid, counter, req_headers=None):
        logger = logging.getLogger("StreamReader")
        logger.debug("Opening video stream: %s" % url)
        self._streamReaderState = 1
        transcoder = None

        if 'range' in req_headers: del req_headers['range']
        logger.debug("Get headers from client: %s" % req_headers)

        try:
            connection = self._streamReaderConnection = requests.get(url, headers=req_headers, stream=True)

            if connection.status_code  not in (200, 206):
                logger.error("Failed to open video stream %s" % url)
                return None

            if url.endswith('.m3u8'):
                self._streamReaderConnection.headers = {'Content-Type':'application/octet-stream','Connection': 'Keep-Alive','Keep-Alive': 'timeout=15, max=100'}
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
                transcoder = psutil.Popen(ffmpeg_cmd.split(), **popen_params)
                out = transcoder.stdout
                logger.warning("HLS stream detected. Ffmpeg transcoding started")
            else: out = connection.raw

        except requests.exceptions.RequestException:
            logger.error("Failed to open video stream")
            logger.error(traceback.format_exc())
        except: logger.error(traceback.format_exc())

        else:
            with self._lock: self._streamReaderState = 2; self._lock.notifyAll()
            while True:
                data = None
                clients = counter.getClients(cid)
                if clients:
                   try: data = out.read(AceConfig.readchunksize)
                   except: logger.debug("No data received"); pass
                   else:
                        with self._lock:
                            if len(self._streamReaderQueue) == AceConfig.readcachesize:
                                self._streamReaderQueue.popleft()
                            self._streamReaderQueue.append(data)

                        for c in clients:
                            try: c.addChunk(data, 5.0)
                            except Queue.Full:
                                if len(clients) > 1:
                                    logger.debug("Disconnecting client: %s" % c)
                                    c.destroy()
                else: logger.debug("All clients disconnected - closing video stream"); break
        finally:
            self.closeStreamReader()
            if transcoder:
               try: transcoder.kill(); logger.warning("Ffmpeg transcoding stoped")
               except: pass
            with self._lock:
                self._streamReaderState = 3
                self._lock.notifyAll()
            counter.deleteAll(cid)

    def closeStreamReader(self):
        logger = logging.getLogger("StreamReader")
        c = self._streamReaderConnection
        if c:
           c.close()
           self._streamReaderConnection = None
           logger.debug("Video stream closed")
        self._streamReaderQueue.clear()

    def getPlayEvent(self, timeout=None):
        '''
        Blocking while in PAUSE, non-blocking while in RESUME
        '''
        return self._resumeevent.wait(timeout=timeout)

    def play(self): self._write(AceMessage.request.PLAY)
    def pause(self): self._write(AceMessage.request.PAUSE)
    def stop(self): self._write(AceMessage.request.STOP)

    def _recvData(self):
        '''
        Data receiver method for greenlet
        '''
        logger = logging.getLogger('AceClient_recvdata')

        while True:
            gevent.sleep()
            try:
                self._recvbuffer = self._socket.read_until("\r\n")
                self._recvbuffer = self._recvbuffer.strip()
                logger.debug('<<< ' + self._recvbuffer)
            except:
                # If something happened during read, abandon reader.
                if not self._shuttingDown.isSet():
                    logger.error("Exception at socket read")
                    self._shuttingDown.set()
                return

            if self._recvbuffer:
                # Parsing everything only if the string is not empty
                if self._recvbuffer.startswith(AceMessage.response.HELLO):
                    # Parse HELLO
                    if 'version_code=' in self._recvbuffer:
                        v = self._recvbuffer.find('version_code=')
                        self._engine_version_code = int(self._recvbuffer[v+13:v+20])

                    if 'key=' in self._recvbuffer:
                        self._request_key_begin = self._recvbuffer.find('key=')
                        self._request_key = self._recvbuffer[self._request_key_begin + 4:self._request_key_begin + 14]
                        self._write(AceMessage.request.READY_key(self._request_key, self._product_key))
                        self._request_key = None
                    else: self._write(AceMessage.request.READY_nokey)
                # NOTREADY
                elif self._recvbuffer.startswith(AceMessage.response.NOTREADY):
                    logger.error("Ace engine is not ready. Wrong auth?")
                    self._auth = None
                    self._authevent.set()
                # LOADRESP
                elif self._recvbuffer.startswith(AceMessage.response.LOADRESP):
                    _contentinfo_raw = self._recvbuffer.split()[2:]
                    _contentinfo_raw = ' '.join(_contentinfo_raw)
                    _contentinfo = json.loads(_contentinfo_raw)
                    if _contentinfo.get('status') == 100:
                        logger.error("LOADASYNC returned error with message: %s" % _contentinfo.get('message'))
                        self._result.set(False)
                    else: self._result.set(_contentinfo); #logger.debug("Content info: %s", _contentinfo)
                # START
                elif self._recvbuffer.startswith(AceMessage.response.START):
                    if not self._seekback or self._started_again or not self._recvbuffer.endswith(' stream=1'):
                        # If seekback is disabled, we use link in first START command.
                        # If seekback is enabled, we wait for first START command and
                        # ignore it, then do seekback in first EVENT position command
                        # AceStream sends us STOP and START again with new link.
                        # We use only second link then.
                        try:
                            self._url = self._recvbuffer.split()[1]
                            self._urlresult.set(self._url)
                            self._resumeevent.set()
                        except IndexError as e: self._url = None
                    else: logger.debug("START received. Waiting for %s." % AceMessage.response.LIVEPOS)
                # STOP
                elif self._recvbuffer.startswith(AceMessage.response.STOP): pass
                # SHUTDOWN
                elif self._recvbuffer.startswith(AceMessage.response.SHUTDOWN):
                    logger.debug("Got SHUTDOWN from engine")
                    self._socket.close()
                    return
                # AUTH
                elif self._recvbuffer.startswith(AceMessage.response.AUTH):
                    try:
                        self._auth = self._recvbuffer.split()[1]
                        # Send USERDATA here
                        self._write(AceMessage.request.USERDATA(self._gender, self._age))
                    except: pass
                    self._authevent.set()
                # GETUSERDATA
                elif self._recvbuffer.startswith(AceMessage.response.GETUSERDATA):
                    raise AceException("You should init me first!")
                # LIVEPOS
                elif self._recvbuffer.startswith(AceMessage.response.LIVEPOS):
                    self._position = self._recvbuffer.split()
                    self._position_last = self._position[2].split('=')[1]
                    self._position_buf = self._position[9].split('=')[1]
                    self._position = self._position[4].split('=')[1]

                    if self._seekback and not self._started_again:
                        self._write(AceMessage.request.LIVESEEK(str(int(self._position_last) - self._seekback)))
                        logger.debug('Seeking back')
                        self._started_again = True
                # DOWNLOADSTOP
                elif self._recvbuffer.startswith(AceMessage.response.DOWNLOADSTOP):
                    self._state = self._recvbuffer.split()[1]
                # STATE
                elif self._recvbuffer.startswith(AceMessage.response.STATE):
                    self._state = self._recvbuffer.split()[1]
                # INFO
                elif self._recvbuffer.startswith(AceMessage.response.INFO):
                    self._state = self._recvbuffer.split()[1]
                # STATUS
                elif self._recvbuffer.startswith(AceMessage.response.STATUS):
                    self._tempstatus = self._recvbuffer.split()[1].split(';')[0]
                    if self._tempstatus != self._status:
                        self._status = self._tempstatus
                        logger.debug("STATUS changed to %s" % self._status)

                    if self._status == 'main:err':
                        logger.error(self._status + ' with message ' + self._recvbuffer.split(';')[2])
                        self._result.set_exception(
                            AceException(self._status + ' with message ' + self._recvbuffer.split(';')[2]))
                        self._urlresult.set_exception(
                            AceException(self._status + ' with message ' + self._recvbuffer.split(';')[2]))
                    elif self._status == 'main:starting': self._result.set(True)
                    elif self._status == 'main:idle': self._result.set(True)
                # PAUSE
                elif self._recvbuffer.startswith(AceMessage.response.PAUSE):
                    logger.debug("PAUSE event")
                    self._resumeevent.clear()
                # RESUME
                elif self._recvbuffer.startswith(AceMessage.response.RESUME):
                    logger.debug("RESUME event")
                    self._resumeevent.set()
                # CID
                elif self._recvbuffer.startswith('##') or len(self._recvbuffer) == 0:
                    self._cidresult.set(self._recvbuffer)
                    logger.debug("CID: %s" %self._recvbuffer)
