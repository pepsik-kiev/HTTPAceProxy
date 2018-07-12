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
import threading
from requests.compat import unquote
from PluginInterface import AceProxyPlugin
import config.torrentfilms as config
from aceconfig import AceConfig

class Torrentfilms(AceProxyPlugin):

    handlers = ('films', 'proxyfilms')

    def __init__(self, AceConfig, AceStuff):
        self.logger = logging.getLogger('plugin_TorrentFilms')
        self.lock = threading.Lock()
        self.playlist = []
        self.videoextdefaults = ('.3gp','.aac','.ape','.asf','.avi','.dv','.divx','.flac','.flc','.flv','.m2ts','.m4a','.mka','.mkv',
                                 '.mpeg','.mpeg4','.mpegts','.mpg4','.mp3','.mp4','.mpg','.mov','.m4v','.ogg','.ogm','.ogv','.oga',
                                 '.ogx','.qt','.rm','.swf','.ts','.vob','.wmv','.wav','.webm')

        if config.updateevery:
            gevent.spawn(self.playlistTimedDownloader)

    def playlistTimedDownloader(self):
        while 1:
            time.sleep(15)
            with self.lock:
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
               infohash = hashlib.sha1(bencode.bencode(metainfo[b'info'])).hexdigest()
            except: logger.error('The file %s may be corrupted. BencodeDecodeError!' % filename)
            else:
               self.logger.debug('%s' % filename)
               if b'files'in metainfo[b'info']:
                  try:
                     for files in metainfo[b'info'][b'files']:
                        if ''.join(files[b'path']).endswith(self.videoextdefaults):
                           self.playlist.append([''.join(files[b'path']).translate(dict.fromkeys(list(map(ord, "%~}{][^$@*,-!?&`|><+=")))), infohash, str(idx), metainfo[b'info'][b'name']])
                           idx+=1
                  except Exception as e:
                     self.logger.error("Can't decode content of: %s\r\n%s" % (filename,repr(e)))
               else:
                    try:
                       self.playlist.append([metainfo[b'info'][b'name'].translate(dict.fromkeys(list(map(ord, "%~}{][^$@*,-!?&`|><=+")))), infohash, '0', 'Other'])
                    except:
                       self.playlist.append([filename.translate(dict.fromkeys(list(map(ord, "%~}{][^$@*,-!?&`|><+=")))), infohash, '0', 'Other'])

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
                  ln += 'http://%s:%s/ace/%s?infohash=%s&transcode_audio=%s&transcode_mp3=%s&transcode_ac3=%s&preferred_audio_language=%s&_idx=%s\n' % \
                        (AceConfig.acehostslist[0][0] if not AceConfig.acehost else AceConfig.acehost ,
                         AceConfig.acehostslist[0][2] if not AceConfig.aceHTTPport else AceConfig.aceHTTPport,
                         config.streamtype, infohash,AceConfig.transcode_audio, AceConfig.transcode_mp3,
                         AceConfig.transcode_ac3, AceConfig.preferred_audio_language, key)

        self.logger.info('Torrent  playlist created')
        return ln

    def handle(self, connection, headers_only=False):

        with self.lock:

            if headers_only:
               connection.send_response(200)
               connection.send_header('Content-Type', 'application/x-mpegurl')
               connection.send_header('Connection', 'close')
               connection.end_headers()
               return

            params = { k:[v] for k,v in (unquote(x).split('=') for x in [s2 for s1 in connection.query.split('&') for s2 in s1.split(';')] if '=' in x) }
            fmt = params['fmt'][0] if 'fmt' in params else None

            exported = self.createPlaylist(connection.headers['Host'], connection.reqtype, fmt).encode('utf-8')

            connection.send_response(200)
            connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
            connection.send_header('Content-Length', str(len(exported)))
            connection.send_header('Connection', 'close')
            connection.end_headers()

            connection.wfile.write(exported)
