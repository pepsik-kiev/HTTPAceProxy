'''
Simple statistics plugin
You will need to "pip install jinja2" first!

To use it, go to http://acehttp_proxy_ip:port/stat
'''
from __future__ import division
from PluginInterface import AceProxyPlugin
from aceconfig import AceConfig
from gevent.subprocess import Popen, PIPE
import psutil
import time
import logging, re
import requests
from jinja2 import Template

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
           from uuid import getnode
           try: mac_address = ':'.join('%02x' % ((getnode() >> 8*i) & 0xff) for i in reversed(range(6)))
           except: mac_address = None
        else:
           try:
              if AceConfig.osplatform != 'Windows':
                 Popen(['ping', '-c', '1', ip_address], stdout = PIPE, shell=False)
                 pid = Popen(['arp', '-n', ip_address], stdout = PIPE, shell=False)
              else:
                 popen_params = { 'stdout' : PIPE,
                                  'shell'  : False }
                 CREATE_NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
                 CREATE_NEW_PROCESS_GROUP = 0x00000200  # note: could get it from subprocess
                 DETACHED_PROCESS = 0x00000008          # 0x8 | 0x200 == 0x208
                 popen_params.update(creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP |  DETACHED_PROCESS)
                 Popen(['ping', '-n', '1', ip_address], **popen_params)
                 pid = Popen(['arp', '-a', ip_address], **popen_params)
           except: Stat.logger.error('Check if arp util is installed!'); return 'Local IP address '
           try: mac_address = re.search(r"(([a-f\d]{1,2}(\:|\-)){5}[a-f\d]{1,2})", pid.communicate()[0]).group(0)
           except: mac_address = None

        if mac_address:
           headers = {'User-Agent':'API Browser'}
           try: response = requests.get('http://macvendors.co/api/%s/json' % mac_address, headers=headers, timeout=5).json()['result']['company']
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

        template = Template(header_template)
        connection.wfile.write(template.render(os_platform = AceConfig.osplatform,
                                               cpu_nums = psutil.cpu_count(),
                                               cpu_percent = psutil.cpu_percent(),
                                               total_ram = round(max_mem.total/2**20,2),
                                               used_ram = round(max_mem.used/2**20,2),
                                               free_ram = round(max_mem.available/2**20,2),
                                               total_disk = round(disk.total/2**30,2),
                                               used_disk = round(disk.used/2**30,2),
                                               free_disk = round(disk.free/2**30,2),
                                               max_clients = self.config.maxconns,
                                               total_clients = self.stuff.clientcounter.total,
                                               ).encode('UTF8'))

        template = Template(row_template)
        for i in self.stuff.clientcounter.clients:
            for c in self.stuff.clientcounter.clients[i]:
                if any([requests.utils.address_in_network(c.handler.clientip,i) for i in localnetranges]):
                   clientInfo = self.mac_lookup(c.handler.clientip)
                else:
                   clientInfo = self.geo_ip_lookup(c.handler.clientip).get('country')
                connection.wfile.write(template.render(channelIcon = c.channelIcon,
                                                       channelName = c.channelName,
                                                       clientIP = c.handler.clientip,
                                                       clientLocation = clientInfo,
                                                       startTime = time.strftime('%c', time.localtime(c.connectionTime)),
                                                       durationTime = time.strftime("%H:%M:%S", time.gmtime(current_time-c.connectionTime)),
                                                       ).encode('UTF8'))
        connection.wfile.write(foot_template)


header_template = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" http-equiv="Refresh" content="60"/>
    <meta name="description" content="HTTP AceProxy state panel">

<link rel="shortcut icon" href="http://i.piccy.info/i9/699484caf086b9c6b5c6cf2cf48f3624/1530371843/19958/1254756/shesterenka.png" type="image/png">

    <title>AceProxy stat info</title>

    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-WskhaSGFgHYWDcbwN70/dfYBj47jz9qbsMId/iRN3ewGhXQFZCSftd1LZCfmhktB" crossorigin="anonymous">

    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/js/bootstrap.min.js" integrity="sha384-smHYKdLADwkXOn1EmN1qk/HfnUcbVRZyYmZ4qpPea6sjB/pTJ0euyQp0Mk8ck+5T" crossorigin="anonymous"></script>

    <link rel="stylesheet" type="text/css" href="http://github.com/downloads/lafeber/world-flags-sprite/flags16.css"/>

    <script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>

    <style>
        .header {height: 150px; background-color: #0a0351 !important; background-size: 100%;background-image: url(http://i.piccy.info/i9/32afd3631fc0032bbfc7bed47d8fec11/1530666765/66668/1254756/space_2294795_1280.jpg);}
        .header-block {position: relative; color:aliceblue; width: 100%; height: 100%;}
        .info-block {position: absolute; left: 15px; bottom:5px; text-shadow: 1px 1px 3px black;}
        .info-block > h6 {margin-bottom: 3px; font-weight: bold}
        .info-block > p {font-size: 0.7em; margin: 0;}
        .status-connection > p {position: absolute; right: 15px; bottom:5px; margin: 0;text-shadow: 1px 1px 1px black;}
        .heder-title {color:aliceblue; padding-top:35px; font-weight: bold; text-shadow: 2px 2px 1px black, 0 0 0.9em #008aff;}
        .heder-title > h1 {font-weight: bold; margin-bottom: 0px}
        .home-link {text-decoration: none; color: aliceblue; font-size: 0.7em;}
        .home-link:hover{color: #b6dcfe; text-decoration: none; font-size: 0.8em;}
        H1 > small {font-size: 0.4em;}
        .table .thead-light th {color: #495057; background-color: #e9e9e9; border: 3px ridge #4b4b4b;}
        .table-bordered td {border: 3px ridge #4b4b4b;}
        th > small {font-weight: bold}

    </style>

  </head>

  <body>

    <nav class="header">

        <div class="header-block">
            <div class="info-block">
                <h6>SYSTEM INFO :</h6>
                <p>OS {{os_platform}}&nbsp;CPU cores: {{cpu_nums}} used: {{cpu_percent}}%</br>
                RAM MiB &nbsp;total: {{total_ram}} &nbsp;used: {{used_ram}}&nbsp;free: {{free_ram}}</br>DISK GiB &nbsp;total: {{total_disk}}&nbsp;used: {{used_disk}}&nbsp;free: {{free_disk}} </p>
            </div>
            <div class="status-connection">
                <p>Connections limit: {{max_clients}}&nbsp;&nbsp;&nbsp;Connected clients: {{total_clients}}</p>
            </div>
            <div class="heder-title">
                <h1 class="text-center">HTTP AceProxy</h1>
                <p class="text-center"><a class="home-link" href="https://github.com/pepsik-kiev/HTTPAceProxy" target="_blank">Project home page on GitHub</a></p>
                <p class="text-center"><a class="home-link" href="http://mytalks.ru/index.php?topic=4506.0" target="_blank">Forum HTTPAceProxy</a></p>
            </div>
        </div>

    </nav>

    <main role="main" class="container" style="margin-top: 30px">
        <div class="f16 container container-fluid">
            <table class="table table-sm table-bordered">
                <thead class="thead-light text-center">
                    <tr>
                        <th scope="col">Channel name</th>
                        <th scope="col">Client IP</th>
                        <th scope="col">Client/Location</th>
                        <th scope="col">Start time</th>
                        <th scope="col">Duration</th>
                    </tr>
                </thead>
"""

row_template = """
                <tbody>

                    <tr>
                        <td>
                            <img src="{{channelIcon}}" width="40" height="20"/>&nbsp;&nbsp;{{channelName}}
                        </td>
                        <td>{{clientIP}}</td>
                        <td>{{clientLocation}}</td>
                        <td>{{startTime}}</td>
                        <td class="text-center">{{durationTime}}</td>
                    </tr>
                </tbody>
"""

foot_template = """
            </table>
        </div>
    </main>

  </body>
</html>

"""
