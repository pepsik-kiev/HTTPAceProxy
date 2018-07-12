# -*- coding: utf-8 -*-
'''
Allfon.tv Playlist Downloader Plugin
http://ip:port/allfon
'''

__author__ = 'miltador, Dorik1972'

import logging, re
import requests
import time
from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
import config.allfon as config

class Allfon(AceProxyPlugin):

    # ttvplaylist handler is obsolete
    handlers = ('allfon',)

    logger = logging.getLogger('plugin_allfon')
    playlist = None
    playlisttime = None

    def __init__(self, AceConfig, AceStuff): pass

    def downloadPlaylist(self):
        headers = {'User-Agent': 'Magic Browser'}
        try:
            Allfon.playlist = requests.get(config.url, headers=headers, proxies=config.proxies, timeout=30).text.encode('UTF-8')
            Allfon.logger.debug('AllFon playlist %s downloaded !' % config.url)
            Allfon.playlisttime = int(time.time())
        except requests.exceptions.ConnectionError:
            Allfon.logger.error("Can't download AllFonTV playlist!")
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

        # 15 minutes cache
        if not Allfon.playlist or (int(time.time()) - Allfon.playlisttime > 15 * 60):
            if not self.downloadPlaylist(): connection.dieWithError(); return

        add_ts = True if connection.path.endswith('/ts') else False
        playlistgen = PlaylistGenerator(m3uchanneltemplate=config.m3uchanneltemplate)

        Allfon.logger.debug('Generating requested m3u playlist')

        pattern = re.compile(r',(?P<name>\S.+)[\r\n].+[\r\n].+[\r\n](?P<url>[^\r\n]+)?')
        for match in pattern.finditer(Allfon.playlist, re.MULTILINE): playlistgen.addItem(match.groupdict())

        Allfon.logger.debug('Exporting m3u playlist')
        params = { k:[v] for k,v in (requests.compat.unquote(x).split('=') for x in [s2 for s1 in connection.query.split('&') for s2 in s1.split(';')] if '=' in x) }
        fmt = params['fmt'][0] if 'fmt' in params else None

        exported = playlistgen.exportm3u(hostport, header=config.m3uheadertemplate, add_ts=add_ts, fmt=fmt)

        connection.send_response(200)
        connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
        connection.send_header('Content-Length', str(len(exported)))
        connection.send_header('Connection', 'close')
        connection.end_headers()

        connection.wfile.write(exported)
