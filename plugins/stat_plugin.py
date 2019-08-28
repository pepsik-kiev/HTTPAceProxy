# -*- coding: utf-8 -*-
'''
Simple statistics plugin

To use it, go to http://acehttp_proxy_ip:port/stat
'''

__author__ = 'Dorik1972, !Joy!'

import time, zlib
import psutil, requests
import logging
from PluginInterface import AceProxyPlugin
from gevent.subprocess import Popen, PIPE
from gevent.pool import Group
from getmac import get_mac_address
from urllib3.packages.six.moves.urllib.parse import parse_qs
from urllib3.packages.six.moves import getcwdb
from urllib3.packages.six import ensure_text, ensure_binary
from requests.compat import json
from requests.utils import re

class Stat(AceProxyPlugin):
    handlers = ('stat',)
    logger = logging.getLogger('STAT')

    def __init__(self, AceConfig, AceProxy):
        self.config = AceConfig
        self.stuff = AceProxy
        self.params = None

    def ip_is_local(self, ip_string):
        if not ip_string:
           return False
        if ip_string == '127.0.0.1':
           return True
        combined_regex = '(^10\\.)|(^172\\.1[6-9]\\.)|(^172\\.2[0-9]\\.)|(^172\\.3[0-1]\\.)|(^192\\.168\\.)'
        return re.match(combined_regex, ip_string) is not None

    def get_vendor_Info(self, ip_address):
        try:
           headers = {'User-Agent':'API Browser'}
           with requests.get('http://macvendors.co/api/%s/json' % get_mac_address(ip=ip_address), headers=headers, timeout=5) as r:
              return r.json()['result']['company']
        except:
           Stat.logger.debug("Can't obtain vendor for %s address" % ip_address)
           return 'Local IP address'

    def handle(self, connection, headers_only=False):
        self.params = parse_qs(connection.query)
        path_file_ext = ''.join(connection.path.split('.')[-1:])

        if headers_only:
           self.SendResponse(200, 'json', '', connection)
           return

        if connection.path == '/stat':
           if self.params.get('action', [''])[0] == 'get_status':
              self.SendResponse(200, 'json', ensure_binary(json.dumps(self.getStatusJSON(), ensure_ascii=False)), connection)
           else:
              try: self.SendResponse(200, 'html', self.getReqFileContent('index.html'), connection)
              except:
                 connection.dieWithError(404, 'Not Found')
                 return

        elif path_file_ext:
           try: self.SendResponse(200, path_file_ext, self.getReqFileContent(connection.path.replace(r'/stat', '')), connection)
           except:
              connection.dieWithError(404, 'Not Found')
              return
        else:
           connection.dieWithError(404, 'Not Found')
           return

    def getReqFileContent(self, path):
        with open('http/%s' % path, 'rb') as handle:
           return handle.read()

    def SendResponse(self, status_code, f_ext, content, connection):
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
           connection.dieWithError(404, 'Not Found')
           return

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
        clients = self.stuff.clientcounter.getAllClientsList() # Get connected clients list
        statusJSON = {}
        statusJSON['status'] = 'success'
        statusJSON['sys_info'] = {
            'os_platform': self.config.osplatform,
            'cpu_nums': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=0, percpu=True),
            'cpu_freq': {k:v for k,v in psutil.cpu_freq()._asdict().items() if k in ('current','min','max')} if psutil.cpu_freq() else {},
            'mem_info': {k:v for k,v in psutil.virtual_memory()._asdict().items() if k in ('total','used','available')},
            'disk_info': {k:v for k,v in psutil.disk_usage(getcwdb())._asdict().items() if k in ('total','used','free')}
            }

        statusJSON['connection_info'] = {
            'max_clients': self.config.maxconns,
            'total_clients': len(clients),
            }

        def _add_client_data(c):
            if not c.clientInfo:
               if self.ip_is_local(c.clientip):
                  c.clientInfo = {'vendor': self.get_vendor_Info(c.clientip), 'country_code': '', 'country_name': '', 'city': ''}
               else:
                  try:
                     headers = {'User-Agent': 'API Browser'}
                     with requests.get('https://geoip-db.com/jsonp/%s' % c.clientip, headers=headers, stream=False, timeout=5) as r:
                        if r.encoding is None: r.encoding = 'utf-8'
                        c.clientInfo = json.loads(r.text.split('(', 1)[1].strip(')'))
                        c.clientInfo['vendor'] = ''
                  except: c.clientInfo = {'vendor': '', 'country_code': '', 'country_name': '', 'city': ''}

            return {
                'sessionID': c.sessionID,
                'channelIcon': c.channelIcon,
                'channelName': ensure_text(c.channelName),
                'clientIP': c.clientip,
                'clientInfo': c.clientInfo,
                #'clientBuff': c.q.qsize()*100/self.config.videotimeout,
                'startTime': time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(c.connectionTime)),
                'durationTime': time.strftime('%H:%M:%S', time.gmtime(time.time()-c.connectionTime)),
                'stat': c.ace.GetSTATUS(),
                    }

        statusJSON['clients_data'] = Group().map(_add_client_data, clients)
        return statusJSON
