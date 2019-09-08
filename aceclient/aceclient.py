# -*- coding: utf-8 -*-
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
import telnetlib
import logging
from gevent.event import AsyncResult
from gevent.util import wrap_errors
from requests.compat import json
from urllib3.packages.six.moves.urllib.parse import unquote
from urllib3.packages.six.moves import zip
from urllib3.packages.six import PY2, ensure_str
from .acemessages import *

class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class Telnet(telnetlib.Telnet, object):
    if not PY2:
       def read_until(self, expected, timeout=None):
           return super(Telnet, self).read_until(bytes(expected, 'ascii'), timeout).decode()

       def write(self, buffer):
           super(Telnet, self).write(bytes(buffer, 'ascii'))

       def expect(self, list, timeout=None):
           match_index, match_object, match_text = super(Telnet, self).expect([bytes(item, 'ascii') for item in list], timeout)
           return match_index, match_object, match_text.decode()

class AceClient(object):

    def __init__(self, **params):

        # AceEngine product key
        self._product_key = params.get('acekey')
        # Current auth
        self._gender = params.get('acesex', AceConst.SEX_MALE)
        self._age = params.get('aceage', AceConst.AGE_25_34)
        # Seekback seconds.
        self._seekback = params.get('videoseekback', 0)
        # AceEngine API maximum allowable response read delay to receive playback URL
        self._videotimeout = params.get('videotimeout', 30)
        # AceEngine API maximum allowable response read delay
        self._responsetimeout = params.get('result_timeout', 5)
        # AceEngine API responses (Created with AsyncResult() on call)
        self._response = {
            'HELLOTS'  : [self._hellots_, AsyncResult()],
            'AUTH'     : [self._auth_, AsyncResult()],
            'NOTREADY' : [self._notready_, AsyncResult()],
            'LOADRESP' : [self._loadresp_, AsyncResult()],
            'START'    : [self._start_, AsyncResult()],
            'STATE'    : [self._state_, AsyncResult()],
            'STATUS'   : [self._status_, AsyncResult()],
            'EVENT'    : [self._event_, AsyncResult()],
            'STOP'     : [self._stop_, AsyncResult()],
            'PAUSE'    : [self._pause_, AsyncResult()],
            'RESUME'   : [self._resume_, AsyncResult()],
            'INFO'     : [self._info_, AsyncResult()],
            'SHUTDOWN' : [self._shutdown_, AsyncResult()],
            'CLOSE'    : [self._close_, AsyncResult()],
                         }
        # AceEngine socket
        try:
           self._socket = Telnet(params.get('ace')['aceHostIP'], params.get('ace')['aceAPIport'], params.get('connect_timeout', 10))
        except:
           errmsg = 'The are no alive AceStream Engines found!'
           raise AceException(errmsg)
        else:
           # Spawning telnet data reader with recvbuffer read timeout (allowable STATE 0 (IDLE) time)
           self._read = gevent.spawn(wrap_errors((EOFError, gevent.socket.error), self._read), self._videotimeout)

    def __bool__(self):
        return self._read.started

    def __nonzero__(self):  # For Python 2 backward compatible
        return self.__bool__()

    def GetAUTH(self):
        '''
        AUTH method
        '''
        try:
           self._response['HELLOTS'][1] = AsyncResult()
           self._write(AceMessage.request.HELLOBG())
           paramsdict = self._response['HELLOTS'][1].get(timeout=self._responsetimeout)
        except gevent.Timeout as t:
           errmsg = 'Engine response time %s exceeded. HELLOTS not resived!' % t
           raise AceException(errmsg)

        try:
           self._response['AUTH'][1] = AsyncResult()
           self._response['NOTREADY'][1] = AsyncResult()
           self._write(AceMessage.request.READY(paramsdict.get('key'), self._product_key))
           auth_level = self._response['AUTH'][1].get(timeout=self._responsetimeout)
           if int(paramsdict.get('version_code', 0)) >= 3003600:
              self._write(AceMessage.request.SETOPTIONS({'use_stop_notifications': '1'}))
        except gevent.Timeout as t:
           if self._response['NOTREADY'][1].value:
              errmsg = 'Engine response time %s exceeded. %s resived!' % (t, self._response['NOTREADY'].value)
           else:
              errmsg = 'Engine response time %s exceeded. AUTH not resived!' % t
           raise AceException(errmsg)

    def _read(self, timeout=30):
        '''
        Read telnet connection method
        '''
        while 1:
            recvbuffer = gevent.with_timeout(timeout, self._socket.read_until, '\r\n', None, timeout_value='CLOSE telnet connetcion').strip().split()
            logging.debug('<<< %s' % unquote(' '.join(recvbuffer)))
            gevent.spawn(self._response[recvbuffer[0]][0], recvbuffer).link(self._response[recvbuffer[0]][1])

    def _write(self, message):
        '''
        Write telnet connection method
        '''
        try:
           self._socket.write('%s\r\n' % message)
           logging.debug('>>> %s' % message)
        except gevent.socket.error:
           raise AceException('Error writing data to AceEngine API port')

    def ShutdownAce(self):
        '''
        Shutdown telnet connection method
        '''
        self._write(AceMessage.request.SHUTDOWN)

    def GetBroadcastStartParams(self, paramsdict):
        '''
        Start video method
        :return START params dict from AceEngine

        If seekback is disabled, we use link in first START command recived from AceEngine.
        If seekback is enabled, we wait for first START command and ignore it,
        then do seekback in first EVENT livepos command (EVENT livepos only for live translation (stream=1) and url not in hls).
        AceEngine sends us STOP and START again with new link. We use only second link then.
        '''
        try:
           self._response['START'][1] = AsyncResult()
           self._write(AceMessage.request.START(paramsdict))
           paramsdict = self._response['START'][1].get(timeout=self._videotimeout)
           if self._seekback and paramsdict.get('stream') and not paramsdict['url'].endswith('.m3u8'):
              try:
                 self._response['EVENT'][1] = AsyncResult()
                 paramsdict = self._response['EVENT'][1].get(timeout=self._responsetimeout)
              except gevent.Timeout as t:
                 errmsg = 'EVENT livepos not received! Engine response time %s exceeded' % t
                 raise AceException(errmsg)
              else:
                 try:
                    self._response['START'][1] = AsyncResult()
                    self._write(AceMessage.request.LIVESEEK(int(paramsdict['last']) - self._seekback))
                    paramsdict = self._response['START'][1].get(timeout=self._responsetimeout)
                 except gevent.Timeout as t:
                    errmsg = 'START URL not received after LIVESEEK! Engine response time %s exceeded' % t
                    raise AceException(errmsg)

           return paramsdict
        except gevent.Timeout as t:
           errmsg = 'START URL not received! Engine response time %s exceeded' % t
           raise AceException(errmsg)

    def StopBroadcast(self):
        '''
        Stop video method
        '''
        self._write(AceMessage.request.STOP)

    def GetLOADASYNC(self, paramsdict):
        try:
           self._response['LOADRESP'][1] = AsyncResult()
           self._write(AceMessage.request.LOADASYNC(paramsdict))
           return self._response['LOADRESP'][1].get(timeout=self._responsetimeout) # Get _contentinfo json
        except gevent.Timeout as t:
           errmsg = 'Engine response %s time exceeded. LOADRESP not resived!' % t
           raise AceException(errmsg)

    def GetSTATUS(self):
        try: return self._response['STATUS'][1].get(timeout=self._responsetimeout) # Get status
        except: return {'status': 'error'}

    def GetCONTENTINFO(self, paramsdict):
        file_idx = int(paramsdict.get('file_indexes', 0))
        paramsdict = self.GetLOADASYNC(paramsdict)
        if paramsdict.get('status') in (1, 2):
           return paramsdict.get('infohash'), ensure_str(next(iter([ x[0] for x in paramsdict.get('files') if x[1] == file_idx ]), None))
        elif paramsdict.get('status') == 0:
           errmsg = 'LOADASYNC returned status 0: The transport file does not contain audio/video files'
        else:
           errmsg = 'LOADASYNC returned error with message: %s' % contentinfo['message']
        raise AceException(errmsg)

######################################## AceEngine API answers parsers ########################################

    def _hellots_(self, recvbuffer):
        '''
        HELLOTS version=engine_version version_code=version_code key=request_key http_port=http_port
        '''
        return {k:v for k,v in [x.split('=') for x in recvbuffer[1:] if '=' in x]}

    def _auth_(self, recvbuffer):
        '''
        AUTH user_auth_level
        '''
        return recvbuffer[1]

    def _notready_(self, recvbuffer):
        '''
        NOTREADY
        '''
        return recvbuffer[0]

    def _start_(self, recvbuffer):
        '''
        START [url=] [infohash=] [file_index=] [ad=1 [interruptable=1]] [stream=1] [pos=position] [bitrate=] [length=]
        '''
        return  {k:v for k,v in [x.split('=') for x in recvbuffer[1:] if '=' in x]}

    def _loadresp_(self, recvbuffer):
        '''
        LOADRESP request_id {'status': status, 'files': [["Name", idx], [....]], 'infohash': infohash, 'checksum': checksum}
        '''
        return json.loads(unquote(''.join(recvbuffer[2:])))

    def _state_(self, recvbuffer):
        '''
        STATE state_id
        '''
        pass

    def _status_(self, recvbuffer):
        '''
        STATUS main:status_description|ad:status_description
        total_progress;immediate_progress;speed_down;http_speed_down;speed_up;peers;http_peers;downloaded;http_downloaded;uploaded
        '''
        recvbuffer = recvbuffer[1].split(';')
        if any(x in ['main:wait', 'main:seekprebuf'] for x in recvbuffer): del recvbuffer[1] #wait;time; / main:seekprebuf;progress
        elif any(x in ['main:buf','main:prebuf'] for x in recvbuffer): del recvbuffer[1:3] #buf/prebuf;progress;time;
        return {k:v.split(':')[1] if 'main' in v else v for k,v in zip(AceConst.STATUS, recvbuffer)}

    def _event_(self, recvbuffer):
        '''
        EVENT getuserdata
        EVENT cansave infohash=infohash index=index format=format
        EVENT showurl type=type url=url [width=width] [height=height]
        EVENT livepos last=xxx live_first=xxx pos=xxx first_ts=xxx last_ts=xxx is_live=1 live_last=xxx buffer_pieces=xx | for live translation only!
        EVENT download_stopped reason=reason option=option
        '''
        if 'getuserdata' in recvbuffer: self._write(AceMessage.request.USERDATA(gender=self._gender, age=self._age))
        elif any(x in ['cansave', 'showurl', 'download_stopped'] for x in recvbuffer): pass
        return {k:v for k,v in [x.split('=') for x in recvbuffer[2:] if '=' in x]}

    def _stop_(self, recvbuffer):
        '''
        STOP
        '''
        pass
    def _pause_(self, recvbuffer):
        '''
        PAUSE
        '''
        pass
    def _resume_(self, recvbuffer):
        '''
        RESUME
        '''
        pass
    def _info_(self, recvbuffer):
        '''
        INFO
        '''
        pass
    def _shutdown_(self, recvbuffer):
        '''
        SHUTDOWN
        '''
        self._read.kill()

    def _close_(self, recvbuffer):
        '''
        Close telnet connection
        '''
        self.ShutdownAce()

######################################## END AceEngine API answers parsers ########################################
