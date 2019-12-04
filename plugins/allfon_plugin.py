#-*- coding: utf-8 -*-
'''
AllFonTV Playlist Downloader Plugin
http://ip:port/allfon
'''

__author__ = 'AndreyPavlenko, Dorik1972'

import traceback
import gevent, requests, os
import logging, zlib
from urllib3.packages.six.moves.urllib.parse import urlparse, quote, unquote
from urllib3.packages.six import ensure_str, ensure_text, ensure_binary
from PlaylistGenerator import PlaylistGenerator
from requests_file import FileAdapter
from utils import schedule, query_get
import config.allfon as config
import config.picons.allfon as picons

class Allfon(object):

    handlers = ('allfon',)

    def __init__(self, AceConfig, AceProxy):
        self.picons = self.channels = self.playlist = self.etag = self.last_modified = None
        self.playlisttime = gevent.time.time()
        self.headers = {'User-Agent': 'Magic Browser'}
        if config.updateevery: schedule(config.updateevery * 60, self.Playlistparser)

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
                 logging.info('[%s]: playlist %s downloaded' % (self.__class__.__name__, config.url))
                 pattern = requests.utils.re.compile(r',(?P<name>.+)[\r\n].+[\r\n].+[\r\n](?P<url>[^\r\n]+)?')
                 urlpattern = requests.utils.re.compile(r'^(acestream|infohash)://[0-9a-f]{40}$|^(http|https)://.*.(acelive|acestream|acemedia|torrent)$')
                 for match in pattern.finditer(r.text, requests.auth.re.MULTILINE):
                    itemdict = match.groupdict()
                    name = itemdict.get('name', '').replace(' (allfon)','')
                    url = itemdict['url']
                    itemdict['logo'] = self.picons[name] = itemdict.get('logo', picons.logomap.get(name))

                    if requests.utils.re.search(urlpattern, url):
                       self.channels[name] = url
                       itemdict['url'] = quote(ensure_str(name),'')

                    self.playlist.addItem(itemdict)
                    m.update(ensure_binary(name))

                 self.etag = '"' + m.hexdigest() + '"'
                 logging.debug('[%s]: plugin playlist generated' % self.__class__.__name__)

              self.playlisttime = gevent.time.time()

        except requests.exceptions.RequestException:
           logging.error("[%s]: can't download %s playlist!" % (self.__class__.__name__, config.url))
           return False
        except: logging.error(traceback.format_exc()); return False

        return True

    def handle(self, connection):
        # 30 minutes cache
        if not self.playlist or (gevent.time.time() - self.playlisttime > 30 * 60):
           if not self.Playlistparser(): connection.send_error()

        connection.ext = query_get(connection.query, 'ext', 'ts')
        if connection.path.startswith('/{reqtype}/channel/'.format(**connection.__dict__)):
           if not connection.path.endswith(connection.ext):
              connection.send_error(404, 'Invalid path: {path}'.format(**connection.__dict__), logging.ERROR)
           name = ensure_text(unquote(os.path.splitext(os.path.basename(connection.path))[0]))
           url = self.channels.get(name)
           if url is None:
              connection.send_error(404, '[%s]: unknown channel: %s' % (self.__class__.__name__, name), logging.ERROR)
           connection.__dict__.update({'channelName': name,
                                       'channelIcon': self.picons.get(name),
                                       'path': {'acestream': '/content_id/%s/%s.%s' % (urlparse(url).netloc, name, connection.ext),
                                                'infohash' : '/infohash/%s/%s.%s' % (urlparse(url).netloc, name, connection.ext),
                                                'http'     : '/url/%s/%s.%s' % (quote(url,''), name, connection.ext),
                                                'https'    : '/url/%s/%s.%s' % (quote(url,''), name, connection.ext),
                                               }[urlparse(url).scheme]})
           connection.__dict__.update({'splittedpath': connection.path.split('/')})
           connection.__dict__.update({'reqtype': connection.splittedpath[1].lower()})
           return

        elif self.etag == connection.headers.get('If-None-Match'):
           logging.debug('[%s]: ETag matches. Return 304 to [%s]' % (self.__class__.__name__, connection.clientip))
           connection.send_response(304)
           connection.send_header('Connection', 'close')
           connection.end_headers()
           return

        else:
           exported = self.playlist.exportm3u( hostport=connection.headers['Host'],
                                               path='' if not self.channels else '/{reqtype}/channel'.format(**connection.__dict__),
                                               header=config.m3uheadertemplate,
                                               query=connection.query
                                              )
           response_headers = {'Content-Type': 'audio/mpegurl; charset=utf-8', 'Connection': 'close', 'Access-Control-Allow-Origin': '*'}
           try:
              h = connection.headers.get('Accept-Encoding').split(',')[0]
              compress_method = { 'zlib': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS),
                                  'deflate': zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS),
                                  'gzip': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16) }
              exported = compress_method[h].compress(exported) + compress_method[h].flush()
              response_headers['Content-Encoding'] = h
           except: pass
           response_headers['Content-Length'] = len(exported)
           if connection.request_version == 'HTTP/1.1':
              response_headers['ETag'] = self.etag
           connection.send_response(200)
           gevent.joinall([gevent.spawn(connection.send_header, k, v) for (k,v) in response_headers.items()])
           connection.end_headers()
           connection.wfile.write(exported)
           logging.debug('[%s]: plugin sent playlist to [%s]' % (self.__class__.__name__, connection.clientip))
