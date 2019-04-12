# -*- coding: utf-8 -*-
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
import telnetlib
import logging
from gevent.event import AsyncResult, Event
from requests.compat import json
from urllib3.packages.six.moves.urllib.parse import urlparse, unquote
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
           match_index, match_object, match_text = super(Telnet, self).expect([bytes(item, 'ascii') for item in list], timeout)
           return match_index, match_object, match_text.decode()

class AceClient(object):

    def __init__(self, ace, connect_timeout=5, result_timeout=10):
        # AceEngine socket
        self._socket = False
        self.ok = False
        # AceEngine read result timeout
        self._resulttimeout = result_timeout
        # AceEngine product key
        self._product_key = None
        # Response time from AceEngine to get URL or DATA
        self._videotimeout = None
        # Current auth
        self._gender = self._age = None
        # Seekback seconds.
        self._seekback = None
        # Result (Created with AsyncResult() on call)
        self._result = {}.fromkeys(['HELLOTS', 'AUTH', 'LOADRESP', 'START', 'STATUS', 'EVENT', 'STATE', 'CID'], AsyncResult())
        # Did we get START command again? For seekback.
        self._started_again = Event()
        # AceConfig start paramerers configiguration
        self._ace = ace
        # AceEngine API answers
        self._answers = {
            'HELLOTS': self._hellots_,
            'AUTH': self._auth_,
            'NOTREADY': self._notready_,
            'LOADRESP': self._loadresp_,
            'START': self._start_,
            'STATE': self._state_,
            'STATUS': self._status_,
            'EVENT': self._event_,
            'STOP': self._stop_,
            'PAUSE': self._pause_,
            'RESUME': self._resume_,
            'INFO': self._info_,
            'SHUTDOWN': self._shutdown_,
               }

        try:
           self._socket = Telnet(self._ace['aceHostIP'], self._ace['aceAPIport'], connect_timeout)
           logging.debug('Successfully connected to AceStream on {aceHostIP}:{aceAPIport}'.format(**self._ace))
        except:
           errmsg = 'The are no alive AceStream Engines found!'
           raise AceException(errmsg)
        else: self.ok = True

    def __bool__(self):
        return self.ok

    def __nonzero__(self):  # For Python 2 backward compatible
        return self.__bool__()

    def aceInit(self, gender=AceConst.SEX_MALE, age=AceConst.AGE_25_34, product_key=None, videoseekback=0, videotimeout=30):
        '''
        AceEngine init telnet connection
        '''
        self._gender = gender
        self._age = age
        self._product_key = product_key
        self._seekback = videoseekback
        self._videotimeout = videotimeout
        self._started_again.clear()
        # Spawning telnet data reader with recvbuffer read timeout (allowable STATE 0 (IDLE) time)
        gevent.spawn(self._read, self._videotimeout)

        self._result['AUTH'] = AsyncResult()
        self._write(AceMessage.request.HELLO) # Sending HELLOBG
        try:
           if self._result.get('AUTH').get(timeout=self._resulttimeout) == 'NOTREADY': # Get NOTREADY instead AUTH user_auth_level
              errmsg = 'NOTREADY recived from AceEngine! Wrong acekey?'
              raise AceException(errmsg)
        except gevent.Timeout as t:
           errmsg = 'Engine response time %s exceeded. AUTH not resived!' % t
           raise AceException(errmsg)

        if int(self._result.get('HELLOTS').get(timeout=self._resulttimeout).get('version_code', 0)) >= 3003600:
           self._write(AceMessage.request.SETOPTIONS({'use_stop_notifications': '1'}))

    def _read(self, timeout=30):
        '''
        Read telnet connection method
        '''
        while 1:
           with gevent.Timeout(timeout, False):
              try:
                 recvbuffer = self._socket.read_until('\r\n', None).strip().split()
                 logging.debug('<<< %s'% unquote(' '.join(recvbuffer)))
                 gevent.spawn(self._answers.get(recvbuffer[0], lambda: self._undefined_), recvbuffer)
              except gevent.Timeout: self.SHUTDOWN()
              except gevent.socket.timeout: pass
              except EOFError: # Telnet connection unexpectedly closed
                 self.ok = False
                 break

    def _write(self, message):
        '''
        Write telnet connection method
        '''
        try:
           self._socket.write('%s\r\n' % message)
           logging.debug('>>> %s' % message)
        except gevent.socket.error:
           raise AceException('Error writing data to AceEngine API port')

    def SHUTDOWN(self):
        '''
        Shutdown telnet connection method
        '''
        self._write(AceMessage.request.SHUTDOWN)

    def START(self, paramsdict):
        '''
        Start video method
        :return playback url from AceEngine
        '''
        self._result['START'] = AsyncResult()
        self._write(AceMessage.request.START(paramsdict))
        try: return self._result.get('START').get(timeout=self._videotimeout)
        except gevent.Timeout as t:
           errmsg = 'START URL not received! Engine response time %s exceeded' % t
           raise AceException(errmsg)

    def STOP(self):
        '''
        Stop video method
        '''
        if self._result.get('STATE').get(timeout=self._resulttimeout):
           self._write(AceMessage.request.STOP)
        '''
        Reset existing telnet connection initial values
        '''
        self._started_again.clear()
        self._result = {}.fromkeys(['HELLOTS', 'AUTH', 'LOADRESP', 'START', 'STATUS', 'EVENT', 'STATE', 'CID'], AsyncResult())

    def LOADASYNC(self, paramsdict):
        self._result['LOADRESP'] = AsyncResult()
        self._write(AceMessage.request.LOADASYNC(paramsdict))
        try: return self._result.get('LOADRESP').get(timeout=self._resulttimeout) # Get _contentinfo json
        except gevent.Timeout as t:
           errmsg = 'Engine response %s time exceeded. LOADRESP not resived!' % t
           raise AceException(errmsg)

    def GETCID(self, paramsdict):
        contentinfo = self.LOADASYNC(paramsdict)
        if contentinfo['status'] in (1, 2):
           self._result['CID'] = AsyncResult()
           self._write(AceMessage.request.GETCID(paramsdict.update(contentinfo)))
           try: return self._result.get('CID').get(timeout=self._resulttimeout) ## CID
           except gevent.Timeout as t:
              errmsg = 'Engine response time %s exceeded. CID not resived!' % t
              raise AceException(errmsg)
        else:
           errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
           raise AceException(errmsg)

    def GETCONTENTINFO(self, paramsdict):
        contentinfo = self.LOADASYNC(paramsdict)
        if contentinfo.get('status') in (1, 2):
           return contentinfo.get('infohash'), next(iter([x[0] for x in contentinfo.get('files') if x[1] == int(paramsdict.get('file_indexes', 0))]), None)
        elif contentinfo.get('status') == 0:
           errmsg = 'LOADASYNC returned status 0: The transport file does not contain audio/video files'
           raise AceException(errmsg)
        else:
           errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
           raise AceException(errmsg)

######################################## AceEngine API answers parsers ########################################

    def _hellots_(self, recvbuffer):
        '''
        HELLOTS version=engine_version version_code=version_code key=request_key http_port=http_port
        '''
        paramsdict = {k:v for k,v in [x.split('=') for x in recvbuffer[1:]]}
        self._write(AceMessage.request.READY(paramsdict.get('key'), self._product_key))
        self._result[recvbuffer[0]].set(paramsdict)

    def _auth_(self, recvbuffer):
        '''
        AUTH user_auth_level
        '''
        self._result[recvbuffer[0]].set(recvbuffer[1])

    def _notready_(self, recvbuffer):
        '''
        NOTREADY
        '''
        self._result['AUTH'].set(recvbuffer[0])

    def _start_(self, recvbuffer):
        '''
        START url [ad=1 [interruptable=1]] [stream=1] [pos=position]
        '''
        paramsdict = {k:v for k,v in [x.split('=') for x in recvbuffer[2:]]}
        if not self._seekback or self._started_again.ready() or paramsdict.get('stream','') is not '1':
           # If seekback is disabled, we use link in first START command.
           # If seekback is enabled, we wait for first START command and
           # ignore it, then do seekback in first EVENT position command
           # AceStream sends us STOP and START again with new link.
           # We use only second link then.
           self._result[recvbuffer[0]].set(recvbuffer[1]) # url for play
           self._started_again.clear()

    def _loadresp_(self, recvbuffer):
        '''
        LOADRESP request_id {'status': status, 'files': [["Name", idx], [....]], 'infohash': infohash, 'checksum': checksum}
        '''
        self._result[recvbuffer[0]].set(json.loads(unquote(''.join(recvbuffer[2:]))))

    def _state_(self, recvbuffer):
        '''
        STATE state_id
        '''
        self._result[recvbuffer[0]].set(recvbuffer[1])

    def _status_(self, recvbuffer):
        '''
        STATUS main:status_description|ad:status_description
        total_progress;immediate_progress;speed_down;http_speed_down;speed_up;peers;http_peers;downloaded;http_downloaded;uploaded
        '''
        paramslist = recvbuffer[1].split(';')
        if 'main:wait' in recvbuffer: del paramslist[1] #wait;time;
        elif any(x in ['main:buf','main:prebuf'] for x in paramslist): del paramslist[1:3] #buf/prebuf;progress;time;
        self._result[recvbuffer[0]].set({k:v.split(':')[1] if 'main' in v else v for k,v in zip(AceConst.STATUS, paramslist)})

    def _event_(self, recvbuffer):
        '''
        EVENT livepos last=xxx live_first=xxx pos=xxx first_ts=xxx last_ts=xxx is_live=1 live_last=xxx buffer_pieces=xx
        EVENT cansave infohash=infohash index=index format=format
        EVENT showurl type=type url=url [width=width] [height=height]
        EVENT download_stopped reason=reason option=option
        '''
        paramsdict = {k:v for k,v in [x.split('=') for x in recvbuffer[2:]]}
        if 'livepos' in recvbuffer and self._seekback and not self._started_again.ready():
           self._write(AceMessage.request.LIVESEEK(int(paramsdict['last']) - self._seekback))
           self._started_again.set()
        elif 'getuserdata' in recvbuffer: self._write(AceMessage.request.USERDATA(gender=self._gender, age=self._age))
        elif any(x in ['cansave', 'showurl', 'download_stopped'] for x in recvbuffer): pass

    def _stop_(self, recvbuffer): pass
    def _pause_(self, recvbuffer): pass
    def _resume_(self, recvbuffer): pass
    def _info_(self, recvbuffer): pass
    def _shutdown_(self, recvbuffer): pass

    def _undefined_(self, recvbuffer):
        '''
        Undefined/unknown/NonStanard commands
        '''
        if '##' in recvbuffer[0]:
           self._result['CID'].set(recvbuffer[0][2:]) # ##cid
        else: pass
######################################## END AceEngine API answers parsers ########################################
