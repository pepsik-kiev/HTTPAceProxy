# -*- coding: utf-8 -*-
'''
Simple statistics plugin

To use it, go to http://acehttp_proxy_ip:port/stat
'''

__author__ = 'Dorik1972, !Joy!'

from PluginInterface import AceProxyPlugin
from gevent.subprocess import Popen, PIPE
from getmac import get_mac_address
from urllib3.packages.six.moves.urllib.parse import parse_qs
from urllib3.packages.six.moves import getcwdb
from requests.compat import json
import os, time, zlib
import psutil
import logging, re
import requests

localnetranges = ( '192.168.0.0/16', '10.0.0.0/8',
                   '172.16.0.0/12', '224.0.0.0/4',
                   '240.0.0.0/5', '127.0.0.0/8', )

class Stat(AceProxyPlugin):
    handlers = ('stat',)
    logger = logging.getLogger('STAT')

    def __init__(self, AceConfig, AceProxy):
        self.config = AceConfig
        self.stuff = AceProxy
        self.params = None

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
        path_file_ext = re.search(r'.js$|.css$|.html$|.png$|.jpg$|.jpeg$|.svg$', connection.path)

        if headers_only:
           self.SendResponse(200, 'json', '', connection)
           return

        if connection.path == '/stat':
           if self.params.get('action', [''])[0] == 'get_status':
              self.SendResponse(200, 'json', json.dumps(self.getStatusJSON(), ensure_ascii=False).encode('utf-8'), connection)
           else:
              try: self.SendResponse(200, 'html', self.getReqFileContent('index.html'), connection)
              except:
                 connection.dieWithError(404, 'Not Found')
                 return

        elif path_file_ext:
           try: self.SendResponse(200, path_file_ext.group(0)[1:], self.getReqFileContent(connection.path.replace(r'/stat', '')), connection)
           except:
              connection.dieWithError(404, 'Not Found')
              return
        else:
           connection.dieWithError(404, 'Not Found')

    def getReqFileContent(self, path):
        with open('http/%s' % path, 'rb') as handle:
           return handle.read()

    def SendResponse(self, status_code, type, content, connection):
        content_type = {
            'js': r'text/javascript; charset=utf-8',
            'json': r'application/json',
            'css': r'text/css; charset=utf-8',
            'html': r'text/html; charset=utf-8',
            'png': r'image/png',
            'jpg': r'image/jpeg',
            'jpeg': r'image/jpeg',
            'svg': r'image/svg+xml'
             }
        connection.send_response(status_code)
        connection.send_header('Content-type', content_type[type])
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
        statusJSON = {}
        statusJSON['status'] = 'success'
        statusJSON['sys_info'] = {
            'os_platform': self.config.osplatform,
            'cpu_nums': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(),
            'mem_info': {k:v for k,v in psutil.virtual_memory()._asdict().items() if k in ('total','used','available')},
            'disk_info': {k:v for k,v in psutil.disk_usage(getcwdb())._asdict().items() if k in ('total','used','free')}
            }

        statusJSON['connection_info'] = {
            'max_clients': self.config.maxconns,
            'total_clients': self.stuff.clientcounter.totalClients(),
            }

        statusJSON['clients_data'] = []
        # Dict {'CID': [client1, client2,....]} to list of values
        clients = [item for sublist in list(self.stuff.clientcounter.streams.values()) for item in sublist]
        for c in clients:
            if not c.clientInfo:
                if any([requests.utils.address_in_network(c.clientip,i) for i in localnetranges]):
                    c.clientInfo = {'vendor': self.get_vendor_Info(c.clientip), 'country_code': '', 'country_name': '', 'city': ''}
                else:
                    try:
                        headers = {'User-Agent':'API Browser'}
                        with requests.get('https://geoip-db.com/jsonp/%s' % c.clientip, headers=headers, stream=False, timeout=5) as r:
                            if r.encoding is None: r.encoding = 'utf-8'
                            c.clientInfo = json.loads(r.text.split('(', 1)[1].strip(')'))
                            c.clientInfo['vendor'] = ''
                    except: c.clientInfo = {'vendor': '', 'country_code': '', 'country_name': '', 'city': ''}

            statusJSON['clients_data'].append({
                'channelIcon': c.channelIcon,
                'channelName': c.channelName,
                'clientIP': c.clientip,
                'clientInfo': c.clientInfo,
                'startTime': time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(c.connectionTime)),
                'durationTime': time.strftime('%H:%M:%S', time.gmtime(time.time()-c.connectionTime)),
                'stat': requests.get(c.cmd['stat_url'], timeout=2, stream=False).json()['response'] if self.config.new_api else c.ace._status.get(timeout=2)
                })
        return statusJSON
