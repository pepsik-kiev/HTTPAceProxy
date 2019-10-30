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
from urllib3.packages.six import PY2
from .acemessages import *

class AceException(Exception):
    '''
    Exception from AceClient
    '''
    pass

class Telnet(telnetlib.Telnet, object):
    '''
    Patching telnetlib methods for Py3 backward compatibility
    '''
    if not PY2:
       def read_until(self, expected, timeout=None):
           return super(Telnet, self).read_until(bytes(expected, 'ascii'), timeout).decode()

       def write(self, buffer):
           super(Telnet, self).write(bytes(buffer, 'ascii'))

       def expect(self, list, timeout=None):
           match_index, match_object, match_text = super(Telnet, self).expect([bytes(item, 'ascii') for item in list], timeout)
           return match_index, match_object, match_text.decode()

class AceClient(object):

    def __init__(self, params):

        # AceEngine product key
        self._product_key = params.get('acekey', AceConst.ACE_KEY)
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
        self._response = {}.fromkeys(['HELLOTS','AUTH','NOTREADY','LOADRESP','START','STATE','STATUS','EVENT',
                                      'STOP','PAUSE','RESUME','INFO','SHUTDOWN',], AsyncResult())
        # Broadcast title
        self._title = 'idleAce'
        # AceEngine socket
        try:
           self._socket = Telnet(params.get('ace')['aceHostIP'], params.get('ace')['aceAPIport'], params.get('connect_timeout', 10))
        except:
           raise AceException('The are no alive AceStream Engines found!')
        else:
           # Spawning telnet data reader with recvbuffer read timeout (allowable STATE 0 (IDLE) time)
           self._read = gevent.spawn(self._read, self._videotimeout)
           self._read.link(lambda x: self._socket.close())
           self._read.link(lambda x: logging.debug('[%.20s]: >>> %s' % (self._title, 'CLOSE telnet connetcion')))

    def __bool__(self):
        return self._read.started

    def __nonzero__(self):  # For Python 2 backward compatible
        return self.__bool__()

    def GetAUTH(self):
        '''
        AUTH method
        '''
        try:
           self._response['HELLOTS'] = AsyncResult()
           self._write(AceRequest.HELLOBG())
           paramsdict = self._response['HELLOTS'].get(timeout=self._responsetimeout)
        except gevent.Timeout as t:
           raise AceException('Engine response time %s exceeded. HELLOTS not resived!' % t)
        try:
           self._response['AUTH'] = AsyncResult()
           self._response['NOTREADY'] = AsyncResult()
           self._write(AceRequest.READY(paramsdict.get('key'), self._product_key))
           auth_level = self._response['AUTH'].get(timeout=self._responsetimeout)
           if int(paramsdict.get('version_code', 0)) >= 3003600:
              self._write(AceRequest.SETOPTIONS({'use_stop_notifications': '1'}))
        except gevent.Timeout as t:
           if self._response['NOTREADY'].value:
              errmsg = 'Engine response time %s exceeded. %s resived!' % (t, self._response['NOTREADY'].value)
           else:
              errmsg = 'Engine response time %s exceeded. AUTH not resived!' % t
           raise AceException(errmsg)

    def _read(self, timeout=30):
        '''
        Read telnet connection method
        '''
        while 1:
           with gevent.Timeout(timeout, False):
              try:
                 recvbuffer = self._socket.read_until('\r\n', None).strip().split()
                 logging.debug('[%.20s]: <<< %s' % (self._title, unquote(' '.join(recvbuffer))))
                 gevent.spawn(getattr(globals()[self.__class__.__name__], '_%s_' % recvbuffer[0].lower(), '_unrecognized_'), self, recvbuffer).link_value(self._response[recvbuffer[0]])
              except gevent.socket.timeout: pass # WinOS patch
              except gevent.Timeout:
                 self.ShutdownAce()
                 break
              except: break # Telnet connection unexpectedly closed or telnet connection error


    def _write(self, message):
        '''
        Write telnet connection method
        '''
        try:
           self._socket.write('%s\r\n' % message)
           logging.debug('[%.20s]: >>> %s' % (self._title, message))
        except gevent.socket.error:
           raise AceException('Error writing data to AceEngine API port')

    def ShutdownAce(self):
        '''
        Shutdown telnet connection method
        '''
        self._write(AceRequest.SHUTDOWN)

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
           self._response['START'] = AsyncResult()
           self._write(AceRequest.START(paramsdict))
           paramsdict = self._response['START'].get(timeout=self._videotimeout)
           if self._seekback and paramsdict.get('stream') and not paramsdict['url'].endswith('.m3u8'):
              try:
                 self._response['EVENT'] = AsyncResult()
                 paramsdict = self._response['EVENT'].get(timeout=self._responsetimeout)
              except gevent.Timeout as t:
                 raise AceException('EVENT livepos not received! Engine response time %s exceeded' % t)
              else:
                 try:
                    self._response['START'] = AsyncResult()
                    self._write(AceRequest.LIVESEEK(int(paramsdict['last']) - self._seekback))
                    paramsdict = self._response['START'].get(timeout=self._responsetimeout)
                 except gevent.Timeout as t:
                    raise AceException('START URL not received after LIVESEEK! Engine response time %s exceeded' % t)
           return paramsdict
        except gevent.Timeout as t:
           raise AceException('START URL not received! Engine response time %s exceeded' % t)

    def StopBroadcast(self):
        '''
        Stop video method
        '''
        self._write(AceRequest.STOP)

    def GetLOADASYNC(self, paramsdict):
        try:
           self._response['LOADRESP'] = AsyncResult()
           self._write(AceRequest.LOADASYNC(paramsdict))
           return self._response['LOADRESP'].get(timeout=self._responsetimeout) # Get _contentinfo json
        except gevent.Timeout as t:
           raise AceException('Engine response %s time exceeded. LOADRESP not resived!' % t)

    def GetSTATUS(self):
        try:
           self._response['STATUS'] = AsyncResult()
           return self._response['STATUS'].get(timeout=self._responsetimeout) # Get status
        except: return {'status': 'error'}

    def GetCONTENTINFO(self, paramsdict):
        paramsdict = self.GetLOADASYNC(paramsdict)
        if paramsdict.get('status') in (1, 2):
            return paramsdict
        elif paramsdict.get('status') == 0:
           errmsg = 'LOADASYNC returned status 0: The transport file does not contain audio/video files'
        else:
           errmsg = 'LOADASYNC returned error with message: {message}'.format(**paramsdict)
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
        if 'getuserdata' in recvbuffer: self._write(AceRequest.USERDATA(gender=self._gender, age=self._age))
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
    def _unrecognized_(self, recvbuffer):
        logging.warning('[%.20s]: unintended API response <<< %s' % (self._title, ' '.join(recvbuffer)))


######################################## END AceEngine API answers parsers ########################################
