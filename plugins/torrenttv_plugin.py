# -*- coding: utf-8 -*-
'''
Torrent-tv.ru Playlist Downloader Plugin
http://ip:port/ttvplaylist
'''
import logging, re
import time
import gevent
from urlparse import parse_qs
import hashlib
import traceback, threading
import requests
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
import config.torrenttv as config
import config.p2pproxy as p2pconfig
from torrenttv_api import TorrentTvApi

class Torrenttv(AceProxyPlugin):

    # ttvplaylist handler is obsolete
    handlers = ('torrenttv', 'ttvplaylist',)

    def __init__(self, AceConfig, AceStuff):
        self.logger = logging.getLogger('plugin_torrenttv')
        self.lock = threading.Lock()
        self.channels = None
        self.playlist = None
        self.playlisttime = None

        self.etag = None
        self.logomap = config.logomap
        self.updatelogos = p2pconfig.email != 're.place@me' and p2pconfig.password != 'ReplaceMe'

        if config.updateevery:
            gevent.spawn(self.playlistTimedDownloader)

    def playlistTimedDownloader(self):
        while True:
            time.sleep(10)
            with self.lock: self.downloadPlaylist()
            gevent.sleep(config.updateevery * 60)

    def downloadPlaylist(self):
        headers = {'User-Agent': 'Magic Browser', 'Accept-Encoding': 'gzip,deflate', 'Connection': 'close'}
        try:
            if config.useproxy:
                  origin = requests.get(config.url, headers=headers, proxies=config.proxies, timeout=30).text
            else: origin = requests.get(config.url, headers=headers, timeout=5).text

            self.logger.info('TTV playlist ' + config.url + ' downloaded')
            self.playlisttime = int(time.time())
            self.playlist = PlaylistGenerator()
            self.channels = dict()
            m = hashlib.md5()
            pattern = re.compile(r',(?P<name>\S.+) \((?P<group>.+)\)[\r\n]+(?P<url>[^\r\n]+)?')

            for match in pattern.finditer(origin.encode('UTF-8'), re.MULTILINE):
                itemdict = match.groupdict()
                encname = itemdict.get('name')
                name = encname.decode('UTF-8')
                logo = self.logomap.get(name)
                url = itemdict['url']
                if logo: itemdict['logo'] = logo

                if url.startswith(('acestream://', 'infohash://')) \
                      or (url.startswith(('http://','https://')) and url.endswith(('.acelive','.acestream','.acemedia'))):
                    self.channels[name] = url
                    itemdict['url'] = requests.utils.quote(encname, '') + '.mp4'
                self.playlist.addItem(itemdict)
                m.update(encname)

            self.etag = '"' + m.hexdigest() + '"'

        except requests.exceptions.ConnectionError:
            self.logger.error("Can't download TTV playlist!")
            return False

        if self.updatelogos:
            try:
                api = TorrentTvApi(p2pconfig.email, p2pconfig.password)
                translations = api.translations('all')
                logos = dict()

                for channel in translations:
                    name = channel.getAttribute('name').encode('utf-8')
                    logo = channel.getAttribute('logo').encode('utf-8')
                    logos[name] = config.logobase + logo

                self.logomap = logos
                self.logger.debug("Logos updated")
                self.updatelogos = False
            except: self.updatelogos = False # p2pproxy plugin seems not configured
        return True

    def handle(self, connection, headers_only=False):
        play = False
        with self.lock:
            # 30 minutes cache
            if not self.playlist or (int(time.time()) - self.playlisttime > 30 * 60):
                self.updatelogos = p2pconfig.email != 're.place@me' and p2pconfig.password != 'ReplaceMe'
                if not self.downloadPlaylist():
                    connection.dieWithError()
                    return

            url = requests.utils.urlparse(connection.path)
            path = url.path[0:-1] if url.path.endswith('/') else url.path
            params = parse_qs(url.query)
            fmt = params['fmt'][0] if 'fmt' in params else None

            if path.startswith('/torrenttv/channel/'):
                if not path.endswith('.mp4'):
                    connection.dieWithError(404, 'Invalid path: ' + requests.utils.unquote(path), logging.ERROR)
                    return

                name = requests.utils.unquote(path[19:-4]).decode('UTF8')
                url = self.channels.get(name)
                if not url:
                    connection.dieWithError(404, 'Unknown channel: ' + name, logging.ERROR)
                    return
                elif url.startswith('acestream://'):
                    connection.path = '/pid/' + url[12:] + '/stream.mp4'
                    connection.splittedpath = connection.path.split('/')
                    connection.reqtype = 'pid'
                elif url.startswith('infohash://'):
                    connection.path = '/infohash/' + url[11:] + '/stream.mp4'
                    connection.splittedpath = connection.path.split('/')
                    connection.reqtype = 'infohash'
                elif url.startswith(('http://', 'https://')) and url.endswith(('.acelive','.acestream', '.acemedia')):
                    connection.path = '/torrent/' + requests.utils.quote(url, '') + '/stream.mp4'
                    connection.splittedpath = connection.path.split('/')
                    connection.reqtype = 'torrent'
                play = True
            elif self.etag == connection.headers.get('If-None-Match'):
                self.logger.debug('ETag matches - returning 304')
                connection.send_response(304)
                connection.send_header('Connection', 'close')
                connection.end_headers()
                return
            else:
                hostport = connection.headers['Host']
                path = '' if len(self.channels) == 0 else '/torrenttv/channel'
                add_ts = True if path.endswith('/ts') else False
                header = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' % (config.tvgurl, config.tvgshift)
                exported = self.playlist.exportm3u(hostport, path, add_ts=add_ts, header=header, fmt=fmt)

                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('ETag', self.etag)
                connection.send_header('Content-Length', str(len(exported)))
                connection.send_header('Connection', 'close')
                connection.end_headers()

        if play: connection.handleRequest(headers_only, name, config.logomap.get(name), fmt=fmt)
        elif not headers_only: connection.wfile.write(exported)
