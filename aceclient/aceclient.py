# -*- coding: utf-8 -*-
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent, requests
import telnetlib
import logging
from gevent.event import AsyncResult, Event
from urllib3.packages.six.moves.urllib.parse import unquote
from urllib3.packages.six.moves import zip, map
from urllib3.packages.six import PY3
from .acemessages import *

class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class Telnet(telnetlib.Telnet, object):
    if PY3:
       def read_until(self, expected, timeout=None):
           return super(Telnet, self).read_until(bytes(expected, 'ascii'), timeout).decode()

       def write(self, buffer):
           super(Telnet, self).write(bytes(buffer, 'ascii'))

       def expect(self, list, timeout=None):
           for index, item in enumerate(list):
              list[index] = bytes(item, 'ascii')
           match_index, match_object, match_text = super(Telnet, self).expect(list, timeout)
           return match_index, match_object, match_text.decode()

class AceClient(object):

    def __init__(self, clientcounter, ace, connect_timeout=5, result_timeout=10):
        # Telnet socket response buffer
        self._recvbuffer = None
        # AceEngine socket
        self._socket = None
        # AceEngine read result timeout
        self._resulttimeout = result_timeout
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
        self._gender = self._age = None
        # Seekback seconds.
        self._seekback = None
        # Did we get START command again? For seekback.
        self._started_again = Event()
        # ClientCounter
        self._clientcounter = clientcounter
        # AceConfig.ace
        self._ace = ace

        try:
           self._socket = Telnet(self._ace['aceHostIP'], self._ace['aceAPIport'], connect_timeout)
           logging.debug('Successfully connected to AceStream on %s:%s' % (self._ace['aceHostIP'], self._ace['aceAPIport']))
        except:
           errmsg = 'The are no alive AceStream Engines found!'
           raise AceException(errmsg)

    def destroy(self):
        '''
        AceClient Destructor
        '''
        # Send SHUTDOWN to AceEngine
        try: self._write(AceMessage.request.SHUTDOWN)
        except: pass # Ignore exceptions on destroy
        finally: self._clientcounter.idleAce = None

    def reset(self):
        '''
        Reset initial values
        '''
        self._started_again.clear()
        self._url.set()
        self._loadasync.set()
        self._cid.set()

    def _write(self, message):
        try:
           self._socket.write('%s\r\n' % message)
           logging.debug('>>> %s' % message)
        except gevent.socket.error:
           raise AceException('Error writing data to AceEngine API port')

    def aceInit(self, gender=AceConst.SEX_MALE, age=AceConst.AGE_25_34, product_key=None, videoseekback=0, videotimeout=30):
        self._gender = gender
        self._age = age
        self._product_key = product_key
        self._seekback = videoseekback
        self._videotimeout = videotimeout
        self._started_again.clear()
        # Spawning telnet data reader with recvbuffer read timeout (allowable STATE 0 (IDLE) time)
        gevent.spawn(self._recvData, self._videotimeout)

        self._auth = AsyncResult()
        self._write(AceMessage.request.HELLO) # Sending HELLOBG
        try: params = self._auth.get(timeout=self._resulttimeout)
        except gevent.Timeout as t:
           errmsg = 'Engine response time %s exceeded. HELLOTS not resived!' % t
           raise AceException(errmsg)

        self._auth = AsyncResult()
        self._write(AceMessage.request.READY(params.get('key',''), self._product_key))
        try:
           if self._auth.get(timeout=self._resulttimeout) == 'NOTREADY': # Get NOTREADY instead AUTH user_auth_level
              errmsg = 'NOTREADY recived from AceEngine! Wrong acekey?'
              raise AceException(errmsg)
        except gevent.Timeout as t:
           errmsg = 'Engine response time %s exceeded. AUTH not resived!' % t
           raise AceException(errmsg)

        if int(params.get('version_code', 0)) >= 3003600: # Display download_stopped massage
           params_dict = {'use_stop_notifications': '1'}
           self._write(AceMessage.request.SETOPTIONS(params_dict))

    def START(self, command, paramsdict, acestreamtype):
        '''
        Start video method. Get url for play from AceEngine
        '''
        paramsdict['stream_type'] = ' '.join(['{}={}'.format(k,v) for k,v in acestreamtype.items()])
        self._url = AsyncResult()
        self._write(AceMessage.request.START(command.upper(), paramsdict))
        try: return self._url.get(timeout=self._videotimeout)
        except gevent.Timeout as t:
           errmsg = 'START URL not resived! Engine response time %s exceeded' % t
           raise AceException(errmsg)

    def STOP(self):
        '''
        Stop video method
        '''
        self._state = AsyncResult()
        self._write(AceMessage.request.STOP)
        try: self._state.get(timeout=self._resulttimeout)
        except gevent.Timeout as t:
           errmsg = 'Engine response time %s exceeded. STATE 0 (IDLE) not resived!' % t
           raise AceException(errmsg)

    def LOADASYNC(self, command, params, sessionid='0'):
        self._loadasync = AsyncResult()
        self._write(AceMessage.request.LOADASYNC(command.upper(), sessionid, params))
        try: return self._loadasync.get(timeout=self._resulttimeout) # Get _contentinfo json
        except gevent.Timeout as t:
           errmsg = 'Engine response %s time exceeded. LOADARESP not resived!' % t
           raise AceException(errmsg)

    def GETCONTENTINFO(self, command, value, sessionid='0'):
        paramsdict = { command:value, 'developer_id':'0', 'affiliate_id':'0', 'zone_id':'0' }
        return self.LOADASYNC(command, paramsdict, sessionid)

    def GETCID(self, command, value):
        contentinfo = self.GETCONTENTINFO(command, value)
        if contentinfo['status'] in (1, 2):
           paramsdict = {'checksum':contentinfo['checksum'], 'infohash':contentinfo['infohash'], 'developer_id':'0', 'affiliate_id':'0', 'zone_id':'0'}
           self._cid = AsyncResult()
           self._write(AceMessage.request.GETCID(paramsdict))
           try: return self._cid.get(timeout=self._resulttimeout)[2:] # ##CID
           except gevent.Timeout as t:
              errmsg = 'Engine response time %s exceeded. CID not resived!' % t
              raise AceException(errmsg)
        else:
           errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
           raise AceException(errmsg)

    def GETINFOHASH(self, command, value, sessionid='0', idx=0):
        contentinfo = self.GETCONTENTINFO(command, value, sessionid)
        if contentinfo['status'] in (1, 2):
           return contentinfo['infohash'], [x[0] for x in contentinfo['files'] if x[1] == int(idx)][0]
        elif contentinfo['status'] == 0:
           errmsg = 'LOADASYNC returned status 0: The transport file does not contain audio/video files'
           raise AceException(errmsg)
        else:
           errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
           raise AceException(errmsg)

    def BrodcastStreamer(self, playback_url, cid):

        def write_chunk(client, data, timeout=15.0, _bytearray=bytearray):
           try:
              client.connection.settimeout(timeout)
              client.out.write(_bytearray('%x\r\n' % len(data), 'utf-8') + data + b'\r\n' if client.response_use_chunked else data)
           except gevent.socket.timeout:  # Client did not read the data from socket for N sec - disconnect it
              logging.warning('Client %s does not read data until %s sec' % (client.clientip, timeout))
              client.connectGreenlet.kill()
           except: pass # The client unexpectedly disconnected while writing data to socket
           finally: client.connection.settimeout(None)

        def chunk_iterator(url):
           return s.get(url, timeout=(5, self._videotimeout)).iter_content(chunk_size=1048576)

        with requests.session() as s:
           s.verify = False
           s.stream = True
           try:
              if playback_url.endswith('.m3u8'): # AceEngine return link for HLS stream
                 used_urls = []
                 while 1:
                    for url in s.get(playback_url, timeout=(5, self._videotimeout)).iter_lines():
                       clients = self._clientcounter.getClientsList(cid)
                       if not clients or url.startswith(b'download not found'): return
                       if url.startswith(b'http://') and url not in used_urls:
                          for chunk in chunk_iterator(url):
                             if chunk: gevent.joinall([gevent.spawn(write_chunk, client, chunk) for client in clients if client.connectGreenlet])
                             else: break
                          used_urls.append(url)
                          if len(used_urls) > 15: used_urls.pop(0)
              else: # AceStream return link for HTTP stream
                 for chunk in chunk_iterator(playback_url):
                    clients = self._clientcounter.getClientsList(cid)
                    if not clients: break
                    gevent.joinall([gevent.spawn(write_chunk, client, chunk) for client in clients if client.connectGreenlet and chunk])

           except Exception as err: # requests errors
              gevent.joinall([gevent.spawn(client.dieWithError, 503, 'BrodcastStreamer:%s' % repr(err), logging.ERROR) for client in self._clientcounter.getClientsList(cid)])
              gevent.joinall([gevent.spawn(client.connectGreenlet.kill) for client in self._clientcounter.getClientsList(cid)])

    def _recvData(self, timeout=30):
        '''
        Data receiver method for greenlet
        '''
        while 1:
           # Destroy socket connection if AceEngine STATE 0 (IDLE) and we didn't read anything from socket until Nsec
           with gevent.Timeout(timeout, False):
              try: self._recvbuffer = self._socket.read_until('\r\n', None).strip()
              except gevent.Timeout: self.destroy()
              except gevent.socket.timeout: pass
              except Exception as err:
                 logging.error('AceException:%s' % repr(err))
                 break
              else:
                 logging.debug('<<< %s' % unquote(self._recvbuffer))
                 # Parsing everything only if the string is not empty
                 # HELLOTS
                 if self._recvbuffer.startswith('HELLOTS'):
                    #version=engine_version version_code=version_code key=request_key http_port=http_port
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
                    self._loadasync.set(requests.compat.json.loads(unquote(''.join(self._recvbuffer.split()[2:]))))
                 # STATE
                 elif self._recvbuffer.startswith('STATE'):
                    self._state.set(AceConst.STATE[self._recvbuffer.split()[1]]) # STATE state_id -> STATE_NAME
                 # STATUS
                 elif self._recvbuffer.startswith('STATUS'):
                    self._tempstatus = self._recvbuffer.split()[1]
                    stat = [self._tempstatus.split(';')[0].split(':')[1]] # main:????
                    if self._tempstatus.startswith('main:idle'): pass
                    elif self._tempstatus.startswith('main:loading'): pass
                    elif self._tempstatus.startswith('main:starting'): pass
                    elif self._tempstatus.startswith('main:check'): pass
                    elif self._tempstatus.startswith('main:err'): pass # err;error_id;error_message
                    elif self._tempstatus.startswith('main:dl'): #dl;
                       stat.extend(map(int, self._tempstatus.split(';')[1:]))
                    elif self._tempstatus.startswith('main:wait'): #wait;time;
                       stat.extend(map(int, self._tempstatus.split(';')[2:]))
                    elif self._tempstatus.startswith(('main:prebuf','main:buf')): #buf;progress;time;
                       stat.extend(map(int, self._tempstatus.split(';')[3:]))
                    if len(stat) == len(AceConst.STATUS):
                       self._status.set({k:v for k,v in zip(AceConst.STATUS, stat)}) # dl, wait, buf, prebuf
                    else: self._status.set({'status': stat[0]}) # idle, loading, starting, check
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
                 elif self._recvbuffer.startswith('PAUSE'): pass #self._write(AceMessage.request.EVENT('pause'))
                 # RESUME
                 elif self._recvbuffer.startswith('RESUME'): pass #self._write(AceMessage.request.EVENT('play'))
                 # STOP
                 elif self._recvbuffer.startswith('STOP'): pass #self._write(AceMessage.request.EVENT('stop'))
                 # SHUTDOWN
                 elif self._recvbuffer.startswith('SHUTDOWN'): self._socket.close(); break
