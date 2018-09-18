# -*- coding: utf-8 -*-
'''
Torrent Films Playlist Plugin
http://ip:port/proxyfilms - for use with AceProxy as proxy
http://ip:port/films - for use with bulit-in AceStream proxy
'''

__author__ = 'Dorik1972'

import os
import logging
import bencode, hashlib
import time
import gevent
from requests.compat import unquote
from PluginInterface import AceProxyPlugin
try: from urlparse import parse_qs
except: from urllib.parse import parse_qs
import config.torrentfilms as config

class Torrentfilms(AceProxyPlugin):

    handlers = ('films', 'proxyfilms')

    def __init__(self, AceConfig, AceStuff):
        self.config = AceConfig
        self.logger = logging.getLogger('plugin_TorrentFilms')
        self.playlist = []
        self.videoextdefaults = ('.3gp','.aac','.ape','.asf','.avi','.dv','.divx','.flac','.flc','.flv','.m2ts','.m4a','.mka','.mkv',
                                 '.mpeg','.mpeg4','.mpegts','.mpg4','.mp3','.mp4','.mpg','.mov','.m4v','.ogg','.ogm','.ogv','.oga',
                                 '.ogx','.qt','.rm','.swf','.ts','.vob','.wmv','.wav','.webm')

        if config.updateevery:
            gevent.spawn(self.playlistTimedDownloader)

    def playlistTimedDownloader(self):
        while 1:
            self.playlistdata()
            gevent.sleep(config.updateevery * 60)

    def playlistdata(self):
        self.playlist = []
        try:
            filelist = [x for x in os.listdir(str(config.directory)) if x.endswith(('.torrent','.torrent.added'))]
        except:
            self.logger.error("Can't load torrent files from %s" % config.directory)
            return False

        for filename in filelist:
            infohash = None
            idx = 0
            try:
               with open('%s/%s' % (config.directory, filename), "rb") as torrent_file: metainfo = bencode.bdecode(torrent_file.read())
               infohash = hashlib.sha1(bencode.bencode(metainfo['info'])).hexdigest()
            except: self.logger.error('The file %s may be corrupted. BencodeDecodeError!' % filename)
            else:
               self.logger.debug('%s' % filename)
               if 'files'in metainfo['info']:
                  try:
                     for files in metainfo['info']['files']:
                        if ''.join(files['path']).endswith(self.videoextdefaults):
                           self.playlist.append([''.join(files['path']).translate({ord(c): None for c in '%~}{][^$#@*,-!?&`|><+='}), infohash, str(idx), metainfo['info']['name']])
                           idx+=1
                  except Exception as e:
                     self.logger.error("Can't decode content of: %s\r\n%s" % (filename,repr(e)))
               else:
                    try:
                       self.playlist.append([metainfo['info']['name'].translate({ord(c): None for c in '%~}{][^$#@*,-!?&`|><+='}), infohash, '0', 'Other'])
                    except:
                       try:
                           self.playlist.append([filename.decode('utf-8').translate({ord(c): None for c in '%~}{][^$#@*,-!?&`|><+='}), infohash, '0', 'Other'])
                       except AttributeError:
                           self.playlist.append([filename.translate({ord(c): None for c in '%~}{][^$#@*,-!?&`|><+='}), infohash, '0', 'Other'])

        self.playlist.sort(key=lambda data: (data[3], data[0]))
        return True

    def createPlaylist(self, hostport, reqtype, fmt):

        if config.updateevery == 0: self.playlistdata()
        ln = '#EXTM3U deinterlace=1 m3uautoload=1 cache=1000\n'
        for data in self.playlist:
             name = data[0]
             infohash  = data[1]
             key = data[2]
             group = data[3]
             ln += '#EXTINF:-1 group-title="' + group + '",' + name + '\n'
             if reqtype == 'proxyfilms':
                 ln += 'http://' + hostport + '/infohash/' + infohash + '/' + key
                 if fmt: ln += '/stream.mp4/?fmt=' + fmt +'\n'
                 else: ln += '/stream.mp4\n'
             else:
                  ln += 'http://%s:%s/ace/%s?infohash=%s&_idx=%s\n' % \
                        (self.config.httphost, self.config.ace['aceHTTPport'], config.streamtype, infohash, key)

        self.logger.info('Torrent  playlist created')
        return ln

    def handle(self, connection, headers_only=False):

        if headers_only:
           connection.send_response(200)
           connection.send_header('Content-Type', 'application/x-mpegurl')
           connection.send_header('Connection', 'close')
           connection.end_headers()
           return

        params = parse_qs(connection.query)
        exported = self.createPlaylist(connection.headers['Host'], connection.reqtype, params.get('fmt', [''])[0]).encode('utf-8')

        connection.send_response(200)
        connection.send_header('Content-Type', 'application/x-mpegurl')
        connection.send_header('Access-Control-Allow-Origin', '*')
        connection.send_header('Content-Length', str(len(exported)))
        connection.send_header('Connection', 'close')
        connection.end_headers()

        connection.wfile.write(exported)
