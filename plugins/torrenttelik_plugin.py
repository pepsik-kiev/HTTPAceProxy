# -*- coding: utf-8 -*- 
'''
Downloader for json-based playlists
Playlist format example:
{"channels":[
{"name":"Channel name 1","url":"blablablablablablablablablablablablablab","cat":"Group 1"},
{"name":"Channel name 2","url":"blablablablablablablablablablablablablab","cat":"Group 2"},
{"name":"Channel name 3","url":"blablablablablablablablablablablablablab","cat":"Group 3"},
......
...
..
.
{"name":"Channel name N","url":"blablablablablablablablablablablablablab","cat":"Group N"}
]}
'''

__author__ = 'miltador, Dorik1972'

import logging
from urlparse import parse_qs
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
        headers = {'User-Agent': 'Magic Browser'}
        proxies=config.proxies if config.useproxy else {}
        try:
            Torrenttelik.playlist = requests.get(url, headers=headers, proxies=proxies, timeout=30).json()
            Torrenttelik.playlisttime = int(time.time())
            Torrenttelik.logger.info('Torrent-telik playlist %s downloaded' % url)
        except requests.exceptions.ConnectionError:
            Torrenttelik.logger.error("Can't download Torrent-telik playlist!")
            return False
        else: return True

    def handle(self, connection, headers_only=False):

        hostport = connection.headers['Host']

        if headers_only:
            connection.send_response(200)
            connection.send_header('Content-Type', 'application/x-mpegurl')
            connection.send_header('Connection', 'close')
            connection.end_headers()
            return

        self.params = parse_qs(connection.query)

        # 15 minutes cache
        if not Torrenttelik.playlist or (int(time.time()) - Torrenttelik.playlisttime > 15 * 60):
            if not self.downloadPlaylist(config.url): connection.dieWithError(); return

        add_ts = True if connection.path.endswith('/ts') else False
        playlistgen = PlaylistGenerator(m3uchanneltemplate=config.m3uchanneltemplate)

        try:
            for channel in Torrenttelik.playlist['channels']:
                channel['group'] = channel.get('cat', '')
                channel['url'] = 'acestream://%s' % channel.get('url', '')
                playlistgen.addItem(channel)
        except Exception as e:
            Torrenttelik.logger.error("Can't parse JSON! %s" % repr(e))
            return

        header = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' %(config.tvgurl, config.tvgshift)
        exported = playlistgen.exportm3u(hostport, header=header, add_ts=add_ts, fmt=self.getparam('fmt')).encode('utf-8')

        connection.send_response(200)
        connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
        connection.send_header('Content-Length', str(len(exported)))
        connection.send_header('Connection', 'close')
        connection.end_headers()

        connection.wfile.write(exported)

    def getparam(self, key):
        return self.params[key][0] if key in self.params else None
