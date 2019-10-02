# -*- coding: utf-8 -*-
'''
Simple statistics plugin

To use it, go to http://acehttp_proxy_ip:port/stat
'''

__author__ = 'Dorik1972, !Joy!'

import time, zlib
import psutil, requests
import logging
from gevent.subprocess import Popen, PIPE
from getmac import get_mac_address
from urllib3.packages.six.moves.urllib.parse import parse_qs
from urllib3.packages.six.moves import getcwdb, map
from urllib3.packages.six import ensure_binary
from requests.compat import json
from requests.utils import re

class Stat(object):
    handlers = ('stat',)
    logger = logging.getLogger('STAT')

    def __init__(self, AceConfig, AceProxy):
        self.AceConfig = AceConfig
        self.AceProxy = AceProxy

    def handle(self, connection):
        path_file_ext = connection.path[connection.path.rfind('.') + 1:]
        if connection.splittedpath[1] == 'stat' and connection.splittedpath.__len__() == 2:
           if 'get_status' in parse_qs(connection.query).get('action', ['']):
              Stat.SendResponse(200, 'json', ensure_binary(json.dumps(self.getStatusJSON(), ensure_ascii=True)), connection)
           else:
              try: Stat.SendResponse(200, 'html', Stat.getReqFileContent('index.html'), connection)
              except: connection.send_error(404, 'Not Found')

        elif path_file_ext:
           try: Stat.SendResponse(200, path_file_ext, Stat.getReqFileContent(connection.path.replace(r'/stat', '')), connection)
           except: connection.send_error(404, 'Not Found')
        else:
           connection.send_error(404, 'Not Found')

    @staticmethod
    def ip_is_local(ip_string):
        if not ip_string:
           return False
        if ip_string == '127.0.0.1':
           return True
        return re.match('(^10\\.)|(^172\\.1[6-9]\\.)|(^172\\.2[0-9]\\.)|(^172\\.3[0-1]\\.)|(^192\\.168\\.)', ip_string) is not None

    @staticmethod
    def get_vendor_Info(ip_address):
        try:
           headers = {'User-Agent':'API Browser'}
           with requests.get('http://macvendors.co/api/%s/json' % get_mac_address(ip=ip_address), headers=headers, timeout=5) as r:
              return r.json()['result']['company']
        except:
           Stat.logger.debug("Can't obtain vendor for %s address" % ip_address)
           return 'Local IP address'

    @staticmethod
    def getReqFileContent(path):
        with open('http/%s' % path, 'rb') as handle:
           return handle.read()

    @staticmethod
    def SendResponse(status_code, f_ext, content, connection):
        mimetype = {
            'js': 'text/javascript; charset=utf-8',
            'json': 'application/json; charset=utf-8',
            'css': 'text/css; charset=utf-8',
            'html': 'text/html; charset=utf-8',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'svg': 'image/svg+xml' }

        if f_ext not in mimetype:
           connection.send_error(404, 'Not Found')

        connection.send_response(status_code)
        connection.send_header('Content-type', mimetype[f_ext])
        connection.send_header('Connection', 'close')
        try:
           h = connection.headers.get('Accept-Encoding').split(',')[0]
           compress_method = { 'zlib': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS),
                               'deflate': zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS),
                               'gzip': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16) }
           content = compress_method[h].compress(content) + compress_method[h].flush()
           connection.send_header('Content-Encoding', h)
        except: pass
        connection.send_header('Content-Length', len(content))
        connection.end_headers()
        connection.wfile.write(content)

    def getStatusJSON(self):
        # Sys Info
        clients = self.AceProxy.clientcounter.getAllClientsList() # Get connected clients list
        statusJSON = {}
        statusJSON['status'] = 'success'
        statusJSON['sys_info'] = {
            'os_platform': self.AceConfig.osplatform,
            'cpu_nums': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=0, percpu=True),
            'cpu_freq': {k:v for k,v in psutil.cpu_freq()._asdict().items() if k in ('current','min','max')} if psutil.cpu_freq() else {},
            'mem_info': {k:v for k,v in psutil.virtual_memory()._asdict().items() if k in ('total','used','available')},
            'disk_info': {k:v for k,v in psutil.disk_usage(getcwdb())._asdict().items() if k in ('total','used','free')}
            }

        statusJSON['connection_info'] = {
            'max_clients': self.AceConfig.maxconns,
            'total_clients': clients.__len__(),
            }

        def _add_client_data(c):
            if not c.clientDetail:
               if Stat.ip_is_local(c.clientip):
                  c.clientDetail = {'vendor': Stat.get_vendor_Info(c.clientip), 'country_code': '', 'country_name': '', 'city': ''}
               else:
                  try:
                     headers = {'User-Agent': 'API Browser'}
                     with requests.get('https://geoip-db.com/jsonp/%s' % c.clientip, headers=headers, stream=False, timeout=5) as r:
                        if r.encoding is None: r.encoding = 'utf-8'
                        c.clientDetail = json.loads(r.text.split('(', 1)[1].strip(')'))
                        c.clientDetail['vendor'] = ''
                  except: c.clientDetail = {'vendor': '', 'country_code': '', 'country_name': '', 'city': ''}

            return {
                'sessionID': c.sessionID,
                'channelIcon': c.channelIcon,
                'channelName': c.channelName,
                'clientIP': c.clientip,
                'clientInfo': c.clientDetail,
                #'clientBuff': c.q.qsize()*100/self.AceConfig.videotimeout,
                'startTime': time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(c.connectionTime)),
                'durationTime': time.strftime('%H:%M:%S', time.gmtime(time.time()-c.connectionTime)),
                'stat': c.ace.GetSTATUS(),
                    }

        statusJSON['clients_data'] = list(map(_add_client_data, clients))
        return statusJSON
