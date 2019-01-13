# -*- coding: utf-8 -*-
'''
Simple statistics plugin

To use it, go to http://acehttp_proxy_ip:port/stat
'''

__author__ = 'Dorik1972, !Joy!'

from PluginInterface import AceProxyPlugin
from gevent.subprocess import Popen, PIPE
import time, zlib
try: from urlparse import parse_qs
except: from urllib.parse import parse_qs
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

    def mac_lookup(self, ip_address):
        mac_address = None
        if ip_address == self.config.httphost:
           from uuid import getnode
           try: mac_address = ':'.join('%02x' % ((getnode() >> 8*i) & 0xff) for i in reversed(list(range(6))))
           except: pass
        else:
           try:
              if self.config.osplatform != 'Windows':
                 p1 = Popen(['ping', '-c', '1', ip_address], stdout = PIPE, shell=False)
                 p2 = Popen(['arp', '-n', ip_address], stdout = PIPE, shell=False)
              else:
                 popen_params = { 'stdout' : PIPE,
                                  'shell'  : False }
                 CREATE_NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
                 CREATE_NEW_PROCESS_GROUP = 0x00000200  # note: could get it from subprocess
                 DETACHED_PROCESS = 0x00000008          # 0x8 | 0x200 == 0x208
                 popen_params.update(creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP |  DETACHED_PROCESS)
                 p1 = Popen(['ping', '-n', '1', ip_address], **popen_params)
                 p2 = Popen(['arp', '-a', ip_address], **popen_params)
           except: Stat.logger.error('Check if arp util is installed!'); return 'Local IP address '

           try: mac_address = re.search(r'(([a-f\d]{1,2}(\:|\-)){5}[a-f\d]{1,2})', p2.stdout.read().decode('utf-8')).group(0)
           except: pass
           finally: p1.stdout.close(); p2.stdout.close()

        if mac_address:
           try:
              headers = {'User-Agent':'API Browser'}
              with requests.get('http://macvendors.co/api/%s/json' % mac_address, headers=headers, timeout=5) as r:
                return r.json()['result']['company']
           except: Stat.logger.debug("Can't obtain vendor for MAC address %s" % mac_address)
        else: Stat.logger.debug("Can't obtain MAC address for local IP %s" % ip_address)
        return 'Local IP address '

    def handle(self, connection, headers_only=False):
        self.params = parse_qs(connection.query)
        path_file_ext = re.search(r'.js$|.css$|.html$|.png$|.jpg$|.jpeg$|.svg$', connection.path)

        if headers_only:
           self.WriteContent(200, 'json', '', connection)
           return

        if connection.path.startswith('/stat') and not path_file_ext:
           if self.params.get('action', [''])[0] == 'get_status':
              # Sys Info
              response = {}
              response['status'] = 'success'
              response['sys_info'] = {
                   'os_platform': self.config.osplatform,
                   'cpu_nums': psutil.cpu_count(),
                   'cpu_percent': psutil.cpu_percent(),
                   'mem_info': {k:v for k,v in psutil.virtual_memory()._asdict().items() if k in ('total','used','available')},
                   'disk_info': {k:v for k,v in psutil.disk_usage('/')._asdict().items() if k in ('total','used','free')}
                    }

              response['connection_info'] = {
                   'max_clients': self.config.maxconns,
                   'total_clients': self.stuff.clientcounter.totalClients(),
                    }

              response['clients_data'] = []
              # Dict {'CID': [client1, client2,....]} to list of values
              clients = [item for sublist in list(self.stuff.clientcounter.streams.values()) for item in sublist]
              for c in clients:
                 if not c.clientInfo:
                    if any([requests.utils.address_in_network(c.clientip,i) for i in localnetranges]):
                       c.clientInfo = self.mac_lookup(c.clientip)
                    else:
                       try:
                          headers = {'User-Agent':'API Browser'}
                          with requests.get('https://geoip-db.com/jsonp/%s' % c.clientip, headers=headers, stream=False, timeout=5) as r:
                             if r.encoding is None: r.encoding = 'utf-8'
                             r = requests.compat.json.loads(r.text.split('(', 1)[1].strip(')'))
                       except: r = {}
                       c.clientInfo = u'<i class="flag {}"></i>&nbsp;&nbsp;{}, {}'.format(r.get('country_code','n/a').lower(), r.get('country_name','n/a'), r.get('city', 'n/a'))

                 client_data = {
                      'channelIcon': c.channelIcon,
                      'channelName': c.channelName,
                      'clientIP': c.clientip,
                      'clientLocation': c.clientInfo,
                      'startTime': time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(c.connectionTime)),
                      'durationTime': time.strftime('%H:%M:%S', time.gmtime(time.time()-c.connectionTime)),
                      'stat': requests.get(c.cmd['stat_url'], timeout=2, stream=False).json()['response'] if self.config.new_api else c.ace._status.get(timeout=2)
                       }
                 response['clients_data'].append(client_data)

              self.WriteContent(200, 'json', requests.compat.json.dumps(response, ensure_ascii=False).encode('utf-8'), connection)
           else:
              try: self.WriteContent(200, 'html', self.getReqFileContent('index.html'), connection)
              except:
                 connection.dieWithError(404, 'Not Found')
                 return

        elif path_file_ext:

           try: self.WriteContent(200, path_file_ext.group(0)[1:], self.getReqFileContent(connection.path.replace(r'/stat', '')), connection)
           except:
              connection.dieWithError(404, 'Not Found')
              return
        else:
           connection.dieWithError(404, 'Not Found')

    def getReqFileContent(self, path):
        with open('http/%s' % path, 'rb') as handle:
           return handle.read()

    def WriteContent(self, status_code, type, content, connection):
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
