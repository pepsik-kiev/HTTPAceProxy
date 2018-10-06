# -*- coding: utf-8 -*-
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
from gevent.event import AsyncResult, Event
import telnetlib
import logging
import requests
import random
from .acemessages import *

class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class Telnet(telnetlib.Telnet, object):

    if requests.compat.is_py3:
        def read_until(self, expected, timeout=None):
            expected = bytes(expected, encoding='utf-8')
            received = super(Telnet, self).read_until(expected, timeout)
            return str(received, encoding='utf-8')

        def write(self, buffer):
            buffer = bytes(buffer, encoding='utf-8')
            super(Telnet, self).write(buffer)

class AceClient(object):

    def __init__(self, ace, connect_timeout=5, result_timeout=10):
        # Telnet response buffer
        self._recvbuffer = None
        # AceEngine socket
        self._socket = None
        # AceEngine read result timeout
        self._resulttimeout = float(result_timeout)
        # Shutting down flag
        self._shuttingDown = Event()
        # AceEngine product key
        self._product_key = None
        # Result (Created with AsyncResult() on call)
        self._auth = AsyncResult()
        # Result for START URL
        self._url = AsyncResult()
        # Response time from AceEngine to get URL or DATA
        self._videotimeout = None
        # Result for CID
        self._cid = AsyncResult()
        # Result fo LOADASYNC
        self._loadasync = AsyncResult()
        # Current STATUS
        self._status = AsyncResult()
        # Current EVENT
        self._event = AsyncResult()
        # Current STATE
        self._state = AsyncResult()
        # Current AUTH
        self._gender = None
        self._age = None
        # Seekback seconds.
        self._seekback = None
        # Did we get START command again? For seekback.
        self._started_again = Event()

        try:
           self._socket = Telnet(ace['aceHostIP'], ace['aceAPIport'], connect_timeout)
           logging.debug('Successfully connected to AceStream on %s:%s' % (ace['aceHostIP'], ace['aceAPIport']))
        except:
           errmsg = 'The are no alive AceStream Engines found!'
           raise AceException(errmsg)
        else:
           # Spawning telnet data reader greenlet
           gevent.spawn(self._recvData)

    def destroy(self):
        '''
        AceClient Destructor
        '''
        if self._shuttingDown.ready(): return   # Already in the middle of destroying
        # Trying to disconnect
        try:
            logging.debug('Destroying AceStream client.....')
            self._shuttingDown.set()
            self._write(AceMessage.request.SHUTDOWN)
        except: pass # Ignore exceptions on destroy
        finally: self._shuttingDown.set()

    def reset(self):
        # Reset initial values
        self._started_again.clear()
        self._url.set()
        self._loadasync.set()
        self._cid.set()

    def _write(self, message):
        try:
            logging.debug('>>> %s' % message)
            self._socket.write('%s\r\n' % message)
        except EOFError as e: raise AceException('Telnet socket Write error! %s' % repr(e))

    def aceInit(self, gender=AceConst.SEX_MALE, age=AceConst.AGE_25_34, product_key=None, videoseekback=0, videotimeout=30):
        self._gender = gender
        self._age = age
        self._product_key = product_key
        self._seekback = videoseekback
        self._videotimeout = float(videotimeout)
        self._started_again.clear()

        self._auth = AsyncResult()
        self._write(AceMessage.request.HELLO) # Sending HELLOBG
        try: params = self._auth.get(timeout=self._resulttimeout)
        except gevent.Timeout:
            errmsg = 'Engine response time %ssec exceeded. HELLOTS not resived!' % self._resulttimeout
            raise AceException(errmsg)
            return

        self._auth = AsyncResult()
        self._write(AceMessage.request.READY(params.get('key',''), self._product_key))
        try:
            if self._auth.get(timeout=self._resulttimeout) == 'NOTREADY': # Get NOTREADY instead AUTH user_auth_level
               errmsg = 'NOTREADY recived from AceEngine! Wrong acekey?'
               raise AceException(errmsg)
               return
        except gevent.Timeout:
            errmsg = 'Engine response time %ssec exceeded. AUTH not resived!' % self._resulttimeout
            raise AceException(errmsg)

        if int(params.get('version_code', 0)) >= 3003600: # Display download_stopped massage
            params_dict = {'use_stop_notifications': '1'}
            self._write(AceMessage.request.SETOPTIONS(params_dict))

    def START(self, command, paramsdict, acestreamtype):
        '''
        Start video method
        Returns the url provided by AceEngine
        '''
        paramsdict['stream_type'] = ' '.join(['{}={}'.format(k,v) for k,v in acestreamtype.items()])
        self._url = AsyncResult()
        self._write(AceMessage.request.START(command.upper(), paramsdict))
        try: return self._url.get(timeout=self._videotimeout) # Get url for play from AceEngine
        except gevent.Timeout:
            errmsg = 'Engine response time %ssec exceeded. START URL not resived!' % self._videotimeout
            raise AceException(errmsg)

    def STOP(self):
        '''
        Stop video method
        '''
        self._state = AsyncResult()
        self._write(AceMessage.request.STOP)
        try: self._state.get(timeout=self._resulttimeout); self._started_again.clear()
        except gevent.Timeout:
            errmsg = 'Engine response time %ssec exceeded. STATE 0 (IDLE) not resived!' % self._resulttimeout
            raise AceException(errmsg)

    def LOADASYNC(self, command, params):
        self._loadasync = AsyncResult()
        self._write(AceMessage.request.LOADASYNC(command.upper(), random.randint(1, 100000), params))
        try: return self._loadasync.get(timeout=self._resulttimeout) # Get _contentinfo json
        except gevent.Timeout:
            errmsg = 'Engine response %ssec time exceeded. LOADARESP not resived!' % self._resulttimeout
            raise AceException(errmsg)

    def GETCONTENTINFO(self, command, value):
        paramsdict = { command:value, 'developer_id':'0', 'affiliate_id':'0', 'zone_id':'0' }
        return self.LOADASYNC(command, paramsdict)

    def GETCID(self, command, value):
        contentinfo = self.GETCONTENTINFO(command, value)
        if contentinfo['status'] in (1, 2):
            paramsdict = {'checksum':contentinfo['checksum'], 'infohash':contentinfo['infohash'], 'developer_id':'0', 'affiliate_id':'0', 'zone_id':'0'}
            self._cid = AsyncResult()
            self._write(AceMessage.request.GETCID(paramsdict))
            try:
                cid = self._cid.get(timeout=self._resulttimeout)
                return '' if cid is None or cid == '' else cid[2:]
            except gevent.Timeout:
                 errmsg = 'Engine response time %ssec exceeded. CID not resived!' % self._resulttimeout
                 raise AceException(errmsg)
        else:
            cid = None
            errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
            raise AceException(errmsg)

    def GETINFOHASH(self, command, value, idx=0):
        contentinfo = self.GETCONTENTINFO(command, value)
        if contentinfo['status'] in (1, 2):
            return contentinfo['infohash'], [x[0] for x in contentinfo['files'] if x[1] == int(idx)][0]
        elif contentinfo['status'] == 0:
           errmsg = 'LOADASYNC returned status 0: The transport file does not contain audio/video files'
           raise AceException(errmsg)
        else:
           errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
           raise AceException(errmsg)

    def AceStreamReader(self, url, cid, counter, req_headers=None):
        '''
        Get stream from AceEngine url and write it to client(s)
        '''
        logging.debug('Start StreamReader for url: %s' % url)
        with requests.Session() as session:
           if req_headers:
               session.headers.update(req_headers)
               logging.debug('Sending headers from client to AceEngine: %s' % session.headers)
           try:
              self._write(AceMessage.request.EVENT('play'))
              # AceEngine return link for HLS stream
              if url.endswith('.m3u8'):
                  _used_chunks = []
                  while self._state.get(timeout=self._resulttimeout)[0] in ('2', '3'):
                    for line in session.get(url, stream=True, timeout=(5, self._videotimeout)).iter_lines():
                       if line.startswith(b'download not found'): return
                       if line.startswith(b'http://') and line not in _used_chunks:
                          self.RAWDataReader(session.get(line, stream=True, timeout=(5, self._videotimeout)), counter.getClientsList(cid))
                          _used_chunks.append(line)
                          if len(_used_chunks) > 15: _used_chunks.pop(0)
              # AceStream return link for HTTP stream
              else: self.RAWDataReader(session.get(url, stream=True, timeout = (5, self._videotimeout)), counter.getClientsList(cid))

           except Exception as err:
              clients = counter.getClientsList(cid)
              if clients:
                 logging.error('"%s" StreamReader error: %s' % (clients[0].channelName, repr(err)))
                 gevent.wait([gevent.spawn(self.write_chunk, c, b'', True) for c in clients]) #b'0\r\n\r\n' - send the chunked trailer
           finally: _used_chunks = None

    def RAWDataReader(self, stream, clients):
        for chunk in stream.iter_content(chunk_size=1048576 if 'Content-Length' in stream.headers else None):
           if chunk: gevent.wait([gevent.spawn(self.write_chunk, c, chunk) for c in clients])

    def write_chunk(self, client, chunk, chunk_trailer=None):
        try: client.out.write(b'%X\r\n%s\r\n' % (len(chunk), chunk)) if not client.transcoder else client.out.write(chunk)
        except: client.destroy() # Client disconected
        if chunk_trailer: client.destroy()

    def _recvData(self):
        '''
        Data receiver method for greenlet
        '''
        while 1:
            try:
                self._recvbuffer = self._socket.read_until('\r\n').strip()
                logging.debug('<<< %s' % requests.compat.unquote(self._recvbuffer))
            except Exception as e:
                # If something happened during read, abandon reader.
                if not self._shuttingDown.ready(): self._shuttingDown.set()
                raise AceException('Exception at socket read. AceClient destroyed %s' % repr(e))
                return
            else: # Parsing everything only if the string is not empty
                # HELLOTS
                if self._recvbuffer.startswith('HELLOTS'):
                    # version=engine_version version_code=version_code key=request_key http_port=http_port
                    self._auth.set({ k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) })
                # NOTREADY
                elif self._recvbuffer.startswith('NOTREADY'): self._auth.set('NOTREADY')
                # AUTH
                elif self._recvbuffer.startswith('AUTH'): self._auth.set(self._recvbuffer.split()[1]) # user_auth_level
                # START
                elif self._recvbuffer.startswith('START'):
                    # url [ad=1 [interruptable=1]] [stream=1] [pos=position]
                    params = { k:v for k,v in (x.split('=') for x in self._recvbuffer.split() if '=' in x) }
                    if not self._seekback or self._started_again.ready() or params.get('stream','') is not '1':
                        # If seekback is disabled, we use link in first START command.
                        # If seekback is enabled, we wait for first START command and
                        # ignore it, then do seekback in first EVENT position command
                        # AceStream sends us STOP and START again with new link.
                        # We use only second link then.
                        self._url.set(self._recvbuffer.split()[1]) # url for play
                # LOADRESP
                elif self._recvbuffer.startswith('LOADRESP'):
                    self._loadasync.set(requests.compat.json.loads(requests.compat.unquote(''.join(self._recvbuffer.split()[2:]))))
                # STATE
                elif self._recvbuffer.startswith('STATE'): # tuple of (state_id, time of appearance)
                    self._state.set((self._recvbuffer.split()[1], gevent.time.time()))
                # STATUS
                elif self._recvbuffer.startswith('STATUS'):
                    self._tempstatus = self._recvbuffer.split()[1]
                    if self._tempstatus.startswith('main:idle'): pass
                    elif self._tempstatus.startswith('main:loading'): pass
                    elif self._tempstatus.startswith('main:starting'): pass
                    elif self._tempstatus.startswith('main:check'): pass
                    elif self._tempstatus.startswith('main:wait'): pass
                    elif self._tempstatus.startswith(('main:prebuf','main:buf')): pass #progress;time
                       #values = list(map(int, self._tempstatus.split(';')[3:]))
                       #self._status.set({k: v for k, v in zip(AceConst.STATUS, values)})
                    elif self._tempstatus.startswith('main:dl'): pass
                       #values = list(map(int, self._tempstatus.split(';')[1:]))
                       #self._status.set({k: v for k, v in zip(AceConst.STATUS, values)})
                    elif self._tempstatus.startswith('main:err'): # err;error_id;error_message
                       self._status.set_exception(AceException('%s with message %s' % (self._tempstatus.split(';')[0],self._tempstatus.split(';')[2])))
                # CID
                elif self._recvbuffer.startswith('##'): self._cid.set(self._recvbuffer)
                # INFO
                elif self._recvbuffer.startswith('INFO'): pass
                # EVENT
                elif self._recvbuffer.startswith('EVENT'):
                    self._tempevent = self._recvbuffer.split()
                    if self._seekback and not self._started_again.ready() and 'livepos' in self._tempevent:
                           params = { k:v for k,v in (x.split('=') for x in self._tempevent if '=' in x) }
                           self._write(AceMessage.request.LIVESEEK(int(params['last']) - self._seekback))
                           self._started_again.set()
                    elif 'getuserdata' in self._tempevent: self._write(AceMessage.request.USERDATA(self._gender, self._age))
                    elif 'cansave' in self._tempevent: pass
                    elif 'showurl' in self._tempevent: pass
                    elif 'download_stopped' in self._tempevent: pass
                # PAUSE
                elif self._recvbuffer.startswith('PAUSE'): self._write(AceMessage.request.EVENT('pause'))
                # RESUME
                elif self._recvbuffer.startswith('RESUME'): self._write(AceMessage.request.EVENT('play'))
                # STOP
                elif self._recvbuffer.startswith('STOP'): pass
                # SHUTDOWN
                elif self._recvbuffer.startswith('SHUTDOWN'):
                    self._socket.close()
                    logging.debug('AceClient destroyed')
                    break
            finally: gevent.sleep()
