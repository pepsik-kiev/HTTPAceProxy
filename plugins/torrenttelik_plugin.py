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
import requests
import time
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
try: from urlparse import parse_qs
except: from urllib.parse import parse_qs
import config.torrenttelik as config

class Torrenttelik(AceProxyPlugin):

    handlers = ('torrent-telik', )

    logger = logging.getLogger('plugin_torrenttelik')
    playlist = None
    playlisttime = None

    def downloadPlaylist(self, url):
        headers = {'User-Agent': 'Magic Browser'}
        try:
            Torrenttelik.playlist = requests.get(url, headers=headers, proxies=config.proxies, timeout=30).json()
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
            connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
            connection.send_header('Connection', 'close')
            connection.end_headers()
            return

        params = parse_qs(connection.query)
        # 15 minutes cache
        if not Torrenttelik.playlist or (int(time.time()) - Torrenttelik.playlisttime > 15 * 60):
            if not self.downloadPlaylist(config.url): connection.dieWithError(); return

        add_ts = True if connection.path.endswith('/ts') else False
        playlistgen = PlaylistGenerator(m3uchanneltemplate=config.m3uchanneltemplate)
        Torrenttelik.logger.debug('Generating requested m3u playlist')

        try:
            for channel in Torrenttelik.playlist['channels']:
                channel['group'] = channel.get('cat', '')
                channel['url'] = 'acestream://%s' % channel.get('url', '')
                playlistgen.addItem(channel)
        except Exception as e:
            Torrenttelik.logger.error("Can't parse JSON! %s" % repr(e))
            return

        Torrenttelik.logger.debug('Exporting m3u playlist')
        exported = playlistgen.exportm3u(hostport, header=config.m3uheadertemplate, add_ts=add_ts, fmt=params.get('fmt', [''])[0]).encode('utf-8')

        connection.send_response(200)
        connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
        connection.send_header('Access-Control-Allow-Origin', '*')
        connection.send_header('Content-Length', str(len(exported)))
        connection.send_header('Connection', 'close')
        connection.end_headers()

        connection.wfile.write(exported)
