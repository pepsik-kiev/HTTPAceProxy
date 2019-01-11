# -*- coding: utf-8 -*-
'''
Simple statistics plugin

To use it, go to http://acehttp_proxy_ip:port/stat
'''

__author__ = 'Dorik1972, !Joy!'

from PluginInterface import AceProxyPlugin
from gevent.subprocess import Popen, PIPE
import time
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

    def mac_lookup(self,ip_address):
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

           p1.stdout.close(); p2.stdout.close()

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
        test_file_extension = re.search(r'\.js$|\.css$|\.html$|\.png$|\.jpg$|\.jpeg$|\.svg$', connection.path)

        if headers_only:
           self.setHeaders(200, 'json', 0, connection)
           return

        if connection.path == '/stat':
            if self.params.get('action', [''])[0] == 'get_status':

                # Sys Info
                max_mem = psutil.virtual_memory()
                disk = psutil.disk_usage('/')

                response = {}
                response['status'] = 'success'
                response['sys_info'] = {
                     'os_platform': self.config.osplatform,
                     'cpu_nums': psutil.cpu_count(),
                     'cpu_percent': psutil.cpu_percent(interval=1),
                     'total_ram': self.config.bytes2human(max_mem.total),
                     'used_ram': self.config.bytes2human(max_mem.used),
                     'free_ram': self.config.bytes2human(max_mem.available),
                     'total_disk': self.config.bytes2human(disk.total),
                     'used_disk': self.config.bytes2human(disk.used),
                     'free_disk': self.config.bytes2human(disk.free),
                      }

                response['connection_info'] = {
                     'max_clients': self.config.maxconns,
                     'total_clients': self.stuff.clientcounter.totalClients(),
                    }

                response['clients_data'] = []
                # Dict {'CID': [client1, client2,....]} to list of values
                clients = [item for sublist in list(self.stuff.clientcounter.streams.values()) for item in sublist]
                for c in clients:
                   if any([requests.utils.address_in_network(c.clientip,i) for i in localnetranges]):
                      clientInfo = self.mac_lookup(c.clientip)
                   else:
                      try:
                         headers = {'User-Agent':'API Browser'}
                         with requests.get('https://geoip-db.com/jsonp/%s' % c.clientip, headers=headers, stream=False, timeout=5) as r:
                            if r.encoding is None: r.encoding = 'utf-8'
                            r = requests.compat.json.loads(r.text.split('(', 1)[1].strip(')'))
                      except: r = {}
                      clientInfo = u'<i class="flag {}"></i>&nbsp;&nbsp;{}, {}'.format(r.get('country_code','n/a').lower(), r.get('country_name','n/a'), r.get('city', 'n/a'))

                   if self.config.new_api:
                      with requests.get(c.cmd['stat_url'], timeout=2, stream=False) as r:
                         stat = r.json()['response']
                   else:
                      stat = c.ace._status.get(timeout=2)

                   client_data = {
                        'channelIcon': c.channelIcon,
                        'channelName': c.channelName,
                        'clientIP': c.clientip,
                        'clientLocation': clientInfo,
                        'startTime': time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(c.connectionTime)),
                        'durationTime': time.strftime('%H:%M:%S', time.gmtime(time.time()-c.connectionTime)),
                        'streamSpeedDL': stat['speed_down'],
                        'streamSpeedUL': stat['speed_up'],
                        'streamPeers': stat['peers'],
                        'status': stat['status'],
                        'downloaded': self.config.bytes2human(stat['downloaded']),
                        'uploaded': self.config.bytes2human(stat['uploaded'])
                         }
                   response['clients_data'].append(client_data)

                exported = requests.compat.json.dumps(response, ensure_ascii=False).encode('utf-8')
                self.setHeaders(200, 'json', len(exported), connection)
                connection.wfile.write(exported)
            else:
                file_content = self.getReqFileContent("index.html")
                self.setHeaders(200, 'html', len(file_content), connection)
                connection.wfile.write(file_content)

        elif test_file_extension:
            path_file_ext = test_file_extension.group(0).replace(r'.', '')
            path = connection.path

            try:
                file_content = self.getReqFileContent(path.replace(r'/stat', ''))
            except:
                connection.dieWithError(404, 'Not Found')
                return

            self.setHeaders(200, path_file_ext, len(file_content), connection)
            connection.wfile.write(file_content)
        else:
            connection.dieWithError(404, 'Not Found')

    def getReqFileContent(self, path):
        root_dir = 'http'
        with open(root_dir + '/' + path, 'rb') as handle:
           file_content = handle.read()
        return file_content

    def setHeaders(self, status_code, type, len_content, connection):
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
        connection.send_header('Content-Length', len_content)
        connection.end_headers()