#-*- coding: utf-8 -*-
'''
Torrent-tv.ru Playlist Downloader Plugin
http://ip:port/torrenttv
'''

__author__ = 'AndreyPavlenko, Dorik1972'

import traceback
import gevent, requests, os
import logging, zlib
from urllib3.packages.six.moves.urllib.parse import urlparse, parse_qs, quote, unquote
from urllib3.packages.six import ensure_str, ensure_text
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
from requests_file import FileAdapter
import config.torrenttv as config
import config.picons.torrenttv as picons

class Torrenttv(AceProxyPlugin):

    # ttvplaylist handler is obsolete
    handlers = ('torrenttv', 'ttvplaylist')

    def __init__(self, AceConfig, AceProxy):
        self.logger = logging.getLogger('torrenttv_plugin')
        self.picons = self.channels = self.playlist = self.etag = None
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
                 pattern = requests.auth.re.compile(r',(?P<name>.+) \((?P<group>.+)\)[\r\n]+(?P<url>[^\r\n]+)?')
                 for match in pattern.finditer(r.text, requests.auth.re.MULTILINE):
                    itemdict = match.groupdict()
                    name = itemdict.get('name', '')
                    itemdict['logo'] = self.picons[name] = itemdict.get('logo', picons.logomap.get(name))

                    url = itemdict['url']
                    if url.startswith(('acestream://', 'infohash://')) \
                         or (url.startswith(('http://','https://')) and url.endswith(('.acelive', '.acestream', '.acemedia', '.torrent'))):
                       self.channels[name] = url
                       itemdict['url'] = quote(ensure_str(name), '')

                    self.playlist.addItem(itemdict)
                    m.update(name.encode('utf-8'))

                 self.etag = '"' + m.hexdigest() + '"'
                 self.logger.debug('torrenttv.m3u playlist generated')

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
        ext = parse_qs(connection.query).get('ext', ['ts'])[0]
        if path.startswith('/%s/channel/' % connection.reqtype):
           if not path.endswith(ext):
              connection.dieWithError(404, 'Invalid path: %s' % unquote(path), logging.ERROR)
              return
           name = ensure_text(unquote(os.path.splitext(os.path.basename(path))[0]))
           url = self.channels.get(name)
           if url is None:
              connection.dieWithError(404, 'Unknown channel: %s' % name, logging.ERROR)
              return
           params = {'name': name, 'value': url.split('/')[2], 'ext': ext}
           if url.startswith('acestream://'):
              connection.path = u'/content_id/{value}/{name}.{ext}'.format(**params)
           elif url.startswith('infohash://'):
              connection.path = u'/infohash/{value}/{name}.{ext}'.format(**params)
           elif url.startswith(('http://', 'https://')) and url.endswith(('.acelive', '.acestream', '.acemedia', '.torrent')):
              params.update({'value': quote(url,'')})
              connection.path = u'/url/{value}/{name}.{ext}'.format(**params)
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
           path = '' if not self.channels else '/%s/channel' % connection.reqtype
           exported = self.playlist.exportm3u(hostport=hostport, path=path, header=config.m3uheadertemplate, query=connection.query)
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

        if play: connection.handleRequest(headers_only=headers_only, channelName=name, channelIcon=self.picons.get(name))
        elif not headers_only:
           self.logger.debug('Exporting torrenttv.m3u playlist')
           connection.wfile.write(exported)
