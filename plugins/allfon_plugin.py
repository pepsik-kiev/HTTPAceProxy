#-*- coding: utf-8 -*-
'''
AllFonTV Playlist Downloader Plugin
http://ip:port/allfon
'''

__author__ = 'AndreyPavlenko, Dorik1972'

import traceback
import gevent, requests
import logging, zlib
from urllib3.packages.six.moves.urllib.parse import urlparse, parse_qs, quote, unquote
from urllib3.packages.six import ensure_str, ensure_text
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
from requests_file import FileAdapter
import config.allfon as config
import config.picons.allfon as picons

class Allfon(AceProxyPlugin):

    handlers = ('allfon',)

    def __init__(self, AceConfig, AceProxy):
        self.logger = logging.getLogger('allfon_plugin')
        self.picons = self.channels = self.playlist = self.etag = self.last_modified = None
        self.playlisttime = gevent.time.time()
        self.headers = {'User-Agent': 'Magic Browser'}
        if config.updateevery: gevent.spawn(self.playlistTimedDownloader)

    def playlistTimedDownloader(self):
        while 1:
            self.Playlistparser()
            gevent.sleep(config.updateevery * 60)

    def Playlistparser(self):
        try:
           s = requests.Session()
           s.mount('file://', FileAdapter())
           with s.get(config.url, headers=self.headers, proxies=config.proxies, stream=False, timeout=30) as r:
              if r.status_code != 304:
                 if r.encoding is None: r.encoding = 'utf-8'
                 self.headers['If-Modified-Since'] = gevent.time.strftime('%a, %d %b %Y %H:%M:%S %Z', gevent.time.gmtime(self.playlisttime))
                 self.playlist = PlaylistGenerator(m3uchanneltemplate=config.m3uchanneltemplate)
                 self.picons = picons.logomap
                 self.channels = {}
                 m = requests.auth.hashlib.md5()
                 self.logger.info('Playlist %s downloaded' % config.url)
                 pattern = requests.auth.re.compile(r',(?P<name>.+)[\r\n].+[\r\n].+[\r\n](?P<url>[^\r\n]+)?')
                 for match in pattern.finditer(r.text, requests.auth.re.MULTILINE):
                    itemdict = match.groupdict()
                    name = itemdict.get('name', '').replace(' (allfon)','')
                    url = itemdict['url']
                    if not 'logo' in itemdict: itemdict['logo'] = picons.logomap.get(name)
                    self.picons[name] = itemdict['logo']

                    if url.startswith(('acestream://', 'infohash://')) \
                         or (url.startswith(('http://','https://')) and url.endswith(('.acelive', '.acestream', '.acemedia', '.torrent'))):
                       self.channels[name] = url
                       itemdict['url'] = quote(ensure_str('%s.ts' % name),'')

                    self.playlist.addItem(itemdict)
                    m.update(name.encode('utf-8'))

                 self.etag = '"' + m.hexdigest() + '"'
                 self.logger.debug('AllFon.m3u playlist generated')

              self.playlisttime = gevent.time.time()

        except requests.exceptions.RequestException: self.logger.error("Can't download %s playlist!" % config.url); return False
        except: self.logger.error(traceback.format_exc()); return False

        return True

    def handle(self, connection, headers_only=False):
        play = False
        # 30 minutes cache
        if not self.playlist or (gevent.time.time() - self.playlisttime > 30 * 60):
           if not self.Playlistparser(): connection.dieWithError(); return

        url = urlparse(connection.path)
        path = url.path[0:-1] if url.path.endswith('/') else url.path
        params = parse_qs(connection.query)

        if path.startswith('/%s/channel/' % connection.reqtype):
           if not path.endswith('.ts'):
              connection.dieWithError(404, 'Invalid path: %s' % unquote(path), logging.ERROR)
              return
           name = ensure_text(unquote(path[path.rfind('/')+1:]))
           url = self.channels.get(('.').join(name.split('.')[:-1]))
           if url is None:
              connection.dieWithError(404, 'Unknown channel: ' + name, logging.ERROR)
              return
           elif url.startswith('acestream://'):
              connection.path = '/content_id/%s/%s' % (url.split('/')[2], name)
           elif url.startswith('infohash://'):
              connection.path = '/infohash/%s/%s' % (url.split('/')[2], name)
           elif url.startswith(('http://', 'https://')) and url.endswith(('.acelive', '.acestream', '.acemedia', '.torrent')):
              connection.path = '/url/%s/%s' % (quote(url,''), name)
           connection.splittedpath = connection.path.split('/')
           connection.reqtype = connection.splittedpath[1].lower()
           name = name.split('.')[0]
           play = True
        elif self.etag == connection.headers.get('If-None-Match'):
           self.logger.debug('ETag matches - returning 304')
           connection.send_response(304)
           connection.send_header('Connection', 'close')
           connection.end_headers()
           return
        else:
           hostport = connection.headers['Host']
           path = '' if not self.channels else '/%s/channel' % connection.reqtype
           add_ts = True if path.endswith('/ts') else False
           exported = self.playlist.exportm3u(hostport=hostport, path=path, add_ts=add_ts, header=config.m3uheadertemplate, fmt=params.get('fmt', [''])[0])
           response_headers = { 'Content-Type': 'audio/mpegurl; charset=utf-8', 'Connection': 'close', 'Content-Length': len(exported),
                                 'Access-Control-Allow-Origin': '*', 'ETag': self.etag }
           try:
              h = connection.headers.get('Accept-Encoding').split(',')[0]
              compress_method = { 'zlib': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS),
                                  'deflate': zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS),
                                  'gzip': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16) }
              exported = compress_method[h].compress(exported) + compress_method[h].flush()
              response_headers['Content-Length'] = len(exported)
              response_headers['Content-Encoding'] = h
           except: pass

           connection.send_response(200)
           gevent.joinall([gevent.spawn(connection.send_header, k, v) for (k,v) in response_headers.items()])
           connection.end_headers()

        if play: connection.handleRequest(headers_only, name, self.picons.get(name), fmt=params.get('fmt', [''])[0])
        elif not headers_only:
           self.logger.debug('Exporting AllFon.m3u playlist')
           connection.wfile.write(exported)
