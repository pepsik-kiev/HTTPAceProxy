'''
Simple statistics plugin

To use it, go to http://127.0.0.1:8000/stat
'''
from __future__ import division
from PluginInterface import AceProxyPlugin
from aceconfig import AceConfig
import psutil
import time, os
import logging, re
import requests

localnetranges = ( '192.168.0.0/16', '10.0.0.0/8',
                   '172.16.0.0/12', '224.0.0.0/4',
                   '240.0.0.0/5', '127.0.0.0/8', )

class Stat(AceProxyPlugin):
    handlers = ('stat',)
    logger = logging.getLogger('STAT')

    def __init__(self, AceConfig, AceStuff):
        self.config = AceConfig
        self.stuff = AceStuff

    def geo_ip_lookup(self, ip_address):
        Stat.logger.debug('Obtain geoip info for IP:%s' % ip_address)
        headers = {'User-Agent':'API Browser'}
        response = requests.get('https://freegeoip.lwan.ws/json/%s' % ip_address, headers=headers, timeout=5, verify=True).json()

        return {'country_code' : '' if not response['country_code'] else response['country_code'] ,
                'country'      : '' if not response['country_name'] else response['country_name'] ,
                'city'         : '' if not response['city'] else response['city']}

    def mac_lookup(self,ip_address):

        if ip_address == AceConfig.httphost:
           mac_address = []
           from uuid import getnode
           mac_address[0] = ':'.join('%02x' % ((getnode() >> 8*i) & 0xff) for i in reversed(range(6)))
        else:
           try: pid = os.system('arp -n %s' % ip_address) if AceConfig.osplatform != 'Windows' else os.system('arp -a %s' % ip_address)
           except: Stat.logger.error("Can't execute arp! Check if arp is installed!"); return "Local IP address "
           mac_address = re.findall(r"(([a-f\d]{1,2}(\:|\-)){5}[a-f\d]{1,2})", str(pid))

        if mac_address:
           headers = {'User-Agent':'API Browser'}
           try: response = requests.get('http://macvendors.co/api/%s/json' % mac_address[0], headers=headers, timeout=5).json()['result']['company']
           except: Stat.logger.error("Can't obtain vendor for MAC address %s" % mac_address)
           else: return response
        else: Stat.logger.error("Can't obtain MAC address for local IP %s" % ip_address)
        return 'Local IP address '

    def handle(self, connection, headers_only=False):
        current_time = time.time()

        connection.send_response(200)
        connection.send_header('Content-type', 'text/html; charset=utf-8')
        connection.send_header('Connection', 'close')
        connection.end_headers()

        if headers_only: return
        # Sys Info
        max_mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        connection.wfile.write('<html><head>')
        connection.wfile.write('<meta charset="UTF-8" http-equiv="Refresh" content="60"/>')
        connection.wfile.write('<title>AceProxy stat info</title>')
        connection.wfile.write('<link rel="stylesheet" type="text/css" href="http://github.com/downloads/lafeber/world-flags-sprite/flags16.css"/>')
        connection.wfile.write('<link rel="shortcut icon" href="http://i.piccy.info/i9/5777461ca749986f6fb4c4b06a70bfbe/1504856430/10417/1177931/SHesterenka_150x150.png" type="image/png">')
        connection.wfile.write('<style>h5 {margin-bottom: -15px;}</style>')
        connection.wfile.write('</head>')
        connection.wfile.write('<body><div class="f16">')

        connection.wfile.write('<p>Connections limit: ' + str(self.config.maxconns) + '&nbsp;&nbsp;&nbsp;Connected clients: ' + str(self.stuff.clientcounter.total) + '</p>')

        connection.wfile.write('<table  border="2" cellspacing="0" cellpadding="3">')
        connection.wfile.write('<tr align=CENTER valign=BASELINE BGCOLOR="#eeeee5"><td>Channel name</td><td>Client IP</td><td>Client/Location</td><td>Start time</td><td>Duration</td></tr>')


        for i in self.stuff.clientcounter.clients:
            for c in self.stuff.clientcounter.clients[i]:
                connection.wfile.write('<tr><td>')
                if c.channelIcon: connection.wfile.write('<img src="' + c.channelIcon + '" width="40" height="16"/>&nbsp;')
                if c.channelName: connection.wfile.write(c.channelName.encode('UTF8'))
                else: connection.wfile.write(i)
                connection.wfile.write('</td><td>' + c.handler.clientip + '</td>')
                clientinrange = any([requests.utils.address_in_network(c.handler.clientip,i) for i in localnetranges])
                if clientinrange: connection.wfile.write('<td>' + self.mac_lookup(c.handler.clientip).encode('UTF8').strip() + '</td>')
                else:
                    geo_ip_info = self.geo_ip_lookup(c.handler.clientip)
                    connection.wfile.write('<td>' + geo_ip_info.get('country').encode('UTF8') + ', ' + geo_ip_info.get('city').encode('UTF8') + '&nbsp;<i class="flag ' + geo_ip_info.get('country_code').encode('UTF8').lower() + '"></i>&nbsp;</td>')
                connection.wfile.write('<td>' + time.strftime('%c', time.localtime(c.connectionTime)) + '</td>')
                connection.wfile.write('<td align="center">' + time.strftime("%H:%M:%S",  time.gmtime(current_time-c.connectionTime)) + '</td></tr>')
        connection.wfile.write('</table></div>')

        connection.wfile.write('<h5>SYSTEM INFO :</h5>')
        connection.wfile.write('<p><font size="-3">OS '+ AceConfig.osplatform + '&nbsp;')
        connection.wfile.write('CPU cores: %s' % psutil.cpu_count() + ' used: %s' % psutil.cpu_percent() + '%</br>')
        connection.wfile.write('RAM MiB &nbsp;' )
        connection.wfile.write('total: %s ' % round(max_mem.total/2**20,2) + '&nbsp;used: %s' % round(max_mem.used/2**20,2) + '&nbsp;free: %s </br>' % round(max_mem.available/2**20,2))
        connection.wfile.write('DISK GiB &nbsp;')
        connection.wfile.write('total: %s ' % round(disk.total/2**30,2) + '&nbsp;used: %s' % round(disk.used/2**30,2) + '&nbsp;free: %s </font></p>' % round(disk.free/2**30,2))
        connection.wfile.write('</body></html>')
