# -*- coding: utf-8 -*- 
__author__ = 'miltador'
'''
Torrent-telik.com Playlist Downloader Plugin
(based on ytv plugin by ValdikSS)
http://ip:port/torrent-telik || http://ip:port/torrent-telik/?type=ttv = torrent-tv playlist
http://ip:port/torrent-telik/?type=mob_ttv = torrent-tv mobile playlist
http://ip:port/torrent-telik/?type=allfon = allfon playlist
'''

import logging
from urlparse import urlparse, parse_qs
import requests
import time
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
import config.torrenttelik as config

class Torrenttelik(AceProxyPlugin):

    handlers = ('torrent-telik', )

    logger = logging.getLogger('plugin_torrenttelik')
    playlist = None
    playlisttime = None

    def downloadPlaylist(self, url):
        headers = {'User-Agent': 'Magic Browser', 'Accept-Encoding': 'gzip,deflate', 'Connection': 'close'}
        try:
            if config.useproxy:
                  Torrenttelik.playlist = requests.get(url, headers=headers, proxies=config.proxies, timeout=30)
            else: Torrenttelik.playlist = requests.get(url, headers=headers, timeout=5)
            Torrenttelik.playlisttime = int(time.time())
            Torrenttelik.logger.info('Torrent-telik playlist %s downloaded' % url)

        except requests.exceptions.ConnectionError:
            Torrenttelik.logger.error("Can't download Torrent-telik playlist!")
            return False

        return True

    def handle(self, connection, headers_only=False):

        hostport = connection.headers['Host']

        if headers_only:
            connection.send_response(200)
            connection.send_header('Content-Type', 'application/x-mpegurl')
            connection.send_header('Connection', 'close')
            connection.end_headers()
            return

        query = urlparse(connection.path).query
        self.params = parse_qs(query)

        url = None
        list_type = self.getparam('type')
        if not list_type or list_type.startswith('ttv'): url = config.url_ttv
        elif list_type.startswith('mob_ttv'): url = config.url_mob_ttv
        elif list_type.startswith('allfon'): url = config.url_allfon

        # 15 minutes cache
        if not Torrenttelik.playlist or (int(time.time()) - Torrenttelik.playlisttime > 15 * 60):
            if not self.downloadPlaylist(url):
                connection.dieWithError()
                return
        try: channels = Torrenttelik.playlist.json()['channels']
        except Exception as e:
            Torrenttelik.logger.error("Can't parse JSON! %s" % repr(e))
            return

        add_ts = False
        try:
            if connection.splittedpath[2].lower() == 'ts': add_ts = True
        except: pass

        playlistgen = PlaylistGenerator()

        for channel in channels:
            channel['group'] = channel.get('cat', '')
            playlistgen.addItem(channel)

        header = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' %(config.tvgurl, config.tvgshift)
        exported = playlistgen.exportm3u(hostport, header=header, add_ts=add_ts, fmt=self.getparam('fmt')).encode('utf-8')

        connection.send_response(200)
        connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
        connection.send_header('Content-Length', str(len(exported)))
        connection.send_header('Connection', 'close')
        connection.end_headers()

        connection.wfile.write(exported)

    def getparam(self, key):
        if key in self.params: return self.params[key][0]
        else: return None
