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
from urllib3.packages.six import ensure_text, ensure_str
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
import config.allfon as config
import config.picons.allfon as picons

class Allfon(AceProxyPlugin):

    handlers = ('allfon',)

    def __init__(self, AceConfig, AceProxy):
        self.logger = logging.getLogger('allfon_plugin')
        self.picons = self.channels = self.playlist = self.playlisttime = self.etag = None

        if config.updateevery: gevent.spawn(self.playlistTimedDownloader)

    def playlistTimedDownloader(self):
        while 1:
            self.Playlistparser()
            gevent.sleep(config.updateevery * 60)

    def Playlistparser(self):
        self.playlisttime = int(gevent.time.time())
        self.playlist = PlaylistGenerator(m3uchanneltemplate=config.m3uchanneltemplate)
        self.picons = picons.logomap
        self.channels = {}
        m = requests.auth.hashlib.md5()
        try:
           headers = {'User-Agent': 'Magic Browser'}
           with requests.get(config.url, headers=headers, proxies=config.proxies, stream=False, timeout=30) as r:
              if r.encoding is None: r.encoding = 'utf-8'
              self.logger.info('Playlist %s downloaded' % config.url)
              pattern = requests.auth.re.compile(r',(?P<name>.+)[\r\n].+[\r\n].+[\r\n](?P<url>[^\r\n]+)?')
              for match in pattern.finditer(r.text, requests.auth.re.MULTILINE):
                 itemdict = match.groupdict()
                 name = itemdict.get('name', '')
                 url = itemdict['url']
                 if not 'logo' in itemdict: itemdict['logo'] = picons.logomap.get(name)
                 self.picons[name] = itemdict['logo']

                 if url.startswith(('acestream://', 'infohash://')) \
                       or (url.startswith(('http://','https://')) and url.endswith(('.acelive','.acestream','.acemedia'))):
                    self.channels[name] = url
                    itemdict['url'] = quote(ensure_str(name+'.ts'),'')

                 self.playlist.addItem(itemdict)
                 m.update(name.encode('utf-8'))

              self.etag = '"' + m.hexdigest() + '"'
              self.logger.debug('AllFon.m3u playlist generated')

        except requests.exceptions.RequestException: self.logger.error("Can't download %s playlist!" % config.url); return False
        except: self.logger.error(traceback.format_exc()); return False

        return True

    def handle(self, connection, headers_only=False):
        play = False
        # 30 minutes cache
        if not self.playlist or (int(gevent.time.time()) - self.playlisttime > 30 * 60):
            self.updatelogos = p2pconfig.email != 're.place@me' and p2pconfig.password != 'ReplaceMe'
            if not self.Playlistparser(): connection.dieWithError(); return

        url = urlparse(connection.path)
        path = url.path[0:-1] if url.path.endswith('/') else url.path
        params = parse_qs(connection.query)

        if path.startswith('/allfon/channel/'):
            name = path.rsplit('.', 1)
            if not name[1]:
                connection.dieWithError(404, 'Invalid path: %s' % unquote(path), logging.ERROR)
                return
            name = unquote(name[0].rsplit('/', 1)[1])
            url = self.channels.get(ensure_text(name))

            if url is None:
                connection.dieWithError(404, 'Unknown channel: ' + name, logging.ERROR); return
            elif url.startswith('acestream://'):
                connection.path = '/content_id/%s/stream.ts' % url.split('/')[2]
            elif url.startswith('infohash://'):
                connection.path = '/infohash/%s/stream.ts' % url.split('/')[2]
            elif url.startswith(('http://', 'https://')) and url.endswith(('.acelive', '.acestream', '.acemedia')):
                connection.path = '/url/%s/stream.ts' % quote(url,'')
            connection.splittedpath = connection.path.split('/')
            connection.reqtype = connection.splittedpath[1].lower()
            play = True
        elif self.etag == connection.headers.get('If-None-Match'):
            self.logger.debug('ETag matches - returning 304')
            connection.send_response(304)
            connection.send_header('Connection', 'close')
            connection.end_headers()
            return
        else:
            hostport = connection.headers['Host']
            path = '' if len(self.channels) == 0 else '/allfon/channel'
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
