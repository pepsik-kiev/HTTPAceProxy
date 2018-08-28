# -*- coding: utf-8 -*-
'''
Simple statistics plugin

To use it, go to http://acehttp_proxy_ip:port/stat
'''
from __future__ import division
from PluginInterface import AceProxyPlugin
from aceconfig import AceConfig
from gevent.subprocess import Popen, PIPE
try: from urlparse import parse_qs
except: from urllib.parse import parse_qs
import psutil
import time
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
        self.params = None

    def bytes2human(self, n):
        # http://code.activestate.com/recipes/578019
        symbols = ('K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
        prefix = { s:(1 << (i + 1)*10) for i,s in enumerate(symbols) }
        for s in reversed(symbols):
            if n >= prefix[s]:
                value = float(n) / prefix[s]
                return '%.1f%s' % (value, s)
        return '%sB' % n


    def geo_ip_lookup(self, ip_address):
        Stat.logger.debug('Obtain geoip info for IP:%s' % ip_address)
        headers = {'User-Agent':'API Browser'}
        response = requests.get('http://geoip.nekudo.com/api/%s/en' % ip_address, headers=headers, timeout=5).json()
        return {'country_code' : '' if not response['country']['code'] else response['country']['code'].lower(),
                'country'      : '' if not response['country']['name'] else response['country']['name'],
                'city'         : '' if not response['city'] else response['city']}

    def mac_lookup(self,ip_address):

        if ip_address == AceConfig.httphost:
           from uuid import getnode
           try: mac_address = ':'.join('%02x' % ((getnode() >> 8*i) & 0xff) for i in reversed(list(range(6))))
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

           try: mac_address = re.search(r'(([a-f\d]{1,2}(\:|\-)){5}[a-f\d]{1,2})', pid.communicate()[0].decode('utf-8')).group(0)
           except: mac_address = None

        if mac_address:
           headers = {'User-Agent':'API Browser'}
           try: response = requests.get('http://macvendors.co/api/%s/json' % mac_address, headers=headers, timeout=5).json()['result']['company']
           except: Stat.logger.error("Can't obtain vendor for MAC address %s" % mac_address)
           else: return response
        else: Stat.logger.error("Can't obtain MAC address for local IP %s" % ip_address)
        return 'Local IP address '

    def get_param(self, key):
        return self.params[key][0] if key in self.params else None

    def handle(self, connection, headers_only=False):
        self.params = parse_qs(connection.query)

        if self.get_param('action') == 'get_status':

            current_time = time.time()

            connection.send_response(200)
            connection.send_header('Content-type', 'application/json')
            connection.send_header('Connection', 'close')
            connection.end_headers()

            if headers_only: return
            # Sys Info
            max_mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            response = {}
            response['status'] = 'success'
            response['sys_info'] = {
                 'os_platform': AceConfig.osplatform,
                 'cpu_nums': psutil.cpu_count(),
                 'cpu_percent': psutil.cpu_percent(interval=1),
                 'total_ram': self.bytes2human(max_mem.total),
                 'used_ram': self.bytes2human(max_mem.used),
                 'free_ram': self.bytes2human(max_mem.available),
                 'total_disk': self.bytes2human(disk.total),
                 'used_disk': self.bytes2human(disk.used),
                 'free_disk': self.bytes2human(disk.free),
                  }

            response['connection_info'] = {
                 'max_clients': self.config.maxconns,
                 'total_clients': self.stuff.clientcounter.total,
                }

            response['clients_data'] = []
            with self.stuff.clientcounter.lock:
              for i in self.stuff.clientcounter.clients:
                 for c in self.stuff.clientcounter.clients[i]:
                    if any([requests.utils.address_in_network(c.handler.clientip,i) for i in localnetranges]):
                       clientInfo = self.mac_lookup(c.handler.clientip)
                    else:
                       clientInfo =u'<i class="flag {country_code}"></i>&nbsp;&nbsp;{country}, {city}'.format(**self.geo_ip_lookup(c.handler.clientip))

                    client_data = {
                        'channelIcon': c.channelIcon,
                        'channelName': c.channelName,
                        'clientIP': c.handler.clientip,
                        'clientLocation': clientInfo,
                        'startTime': time.strftime('%c', time.localtime(c.connectionTime)),
                        'durationTime': time.strftime("%H:%M:%S", time.gmtime(current_time-c.connectionTime))
                         }

                    response['clients_data'].append(client_data)

            connection.wfile.write(requests.compat.json.dumps(response, ensure_ascii=False).encode('utf-8'))

        else:

          connection.send_response(200)
          connection.send_header('Content-type', 'text/html; charset=utf-8')
          connection.send_header('Connection', 'close')
          connection.end_headers()

          connection.wfile.write(html_template)


html_template = b"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8"/>
    <meta name="description" content="HTTP AceProxy state panel">

<link rel="shortcut icon" href="http://i.piccy.info/i9/699484caf086b9c6b5c6cf2cf48f3624/1530371843/19958/1254756/shesterenka.png" type="image/png">

    <title>AceProxy stat info</title>

    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.3.1/jquery.min.js"></script>

    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-WskhaSGFgHYWDcbwN70/dfYBj47jz9qbsMId/iRN3ewGhXQFZCSftd1LZCfmhktB" crossorigin="anonymous">

    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/js/bootstrap.min.js" integrity="sha384-smHYKdLADwkXOn1EmN1qk/HfnUcbVRZyYmZ4qpPea6sjB/pTJ0euyQp0Mk8ck+5T" crossorigin="anonymous"></script>

    <link rel="stylesheet" type="text/css" href="http://github.com/downloads/lafeber/world-flags-sprite/flags16.css"/>

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

    <script type="text/javascript">
        getStatus();

        function getStatus() {
            $.ajax({
                url: 'stat/?action=get_status',
                type: 'get',
                success: function(resp) {
                    if(resp.status === 'success') {
                        renderPage(resp);
                    } else {
                        console.error('Error! getStatus() Response not returning status success');
                    }
                    setTimeout(getStatus, 5000);
                },
                error: function(resp, textStatus, errorThrown) {
                    console.error("getStatus() Unknown error!." +
                        " ResponseCode: " + resp.status +
                        " | textStatus: " + textStatus +
                        " | errorThrown: " + errorThrown);
                    $('tbody').html("");
                    $('main').append('<h1 class="text-center" style="color:red; font-weight: bold;">Server not responding! Refresh page!!!</h1>')
                },
            });
        }

        function renderPage(data) {
            var sys_info = data.sys_info;
            var connection_info = data.connection_info;
            var clients_data = data.clients_data;
            var clients_content = "";

            $('#sys_info').html("OS " + sys_info.os_platform + "&nbsp;CPU cores: " + sys_info.cpu_nums +
                                " used: " + sys_info.cpu_percent + "%</br>"+
                                "RAM &nbsp;total: " + sys_info.total_ram +
                                " &nbsp;used: " + sys_info.used_ram +
                                "&nbsp;free: " + sys_info.free_ram + "</br>DISK &nbsp;total: " + sys_info.total_disk +
                                "&nbsp;used: " + sys_info.used_disk + "&nbsp;free: " + sys_info.free_disk);

            $('#connection_info').html("Connections limit: " + connection_info.max_clients +
                                       "&nbsp;&nbsp;&nbsp;Connected clients: " + connection_info.total_clients);

            if (clients_data.length) {

                clients_data.forEach(function(item, i, arr) {

                    clients_content += '<tr><td><img src="' + item.channelIcon +
                                       '" width="40" height="20"/>&nbsp;&nbsp;' + item.channelName +
                                        '</td><td>' + item.clientIP + '</td><td>' + item.clientLocation + '</td>' +
                                        '<td>' + item.startTime + '</td><td class="text-center">' + item.durationTime + '</td></tr>';
                });

                $('tbody').html(clients_content);

            } else {
                $('tbody').html('');
            }
        }

    </script>

  </head>

  <body>
    <nav class="header">
        <div class="header-block">
            <div class="info-block">
                <h6>SYSTEM INFO :</h6>
                <p id="sys_info"></p>
            </div>
            <div class="status-connection">
                <p id="connection_info"></p>
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
                <tbody>
                </tbody>
            </table>
        </div>
    </main>
  </body>
</html>

"""
