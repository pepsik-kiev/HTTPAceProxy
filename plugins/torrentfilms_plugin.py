# -*- coding: utf-8 -*-
'''
Torrent Films Playlist Plugin
http://ip:port/proxyfilms - for use with AceProxy as proxy
http://ip:port/films - for use with bulit-in AceStream proxy
(C) Dorik1972
!!! NEED TO INSTALL BENCODE MODULE !!!
'''
import os
import logging
import requests
import bencode, hashlib
import time
import urlparse
import gevent
import threading
from modules.PluginInterface import AceProxyPlugin
import config.torrentfilms as config
from aceconfig import AceConfig

class Torrentfilms(AceProxyPlugin):

    handlers = ('films','proxyfilms')

    def __init__(self, AceConfig, AceStuff):
        self.logger = logging.getLogger('plugin_TorrentFilms')
        self.lock = threading.Lock()
        self.playlist = []

        if config.updateevery:
            gevent.spawn(self.playlistTimedDownloader)

    def playlistTimedDownloader(self):
        while True:
            with self.lock:
                 self.playlistdata()
            gevent.sleep(config.updateevery * 60)

    def playlistdata(self):
        self.playlist = []
        try:
             filelist = filter(lambda x: x.endswith(('.torrent','.torrent.added')), os.listdir(unicode(config.directory)))
        except:
             self.logger.error("Can't load torrent files from "+config.directory)
             return False

        for filename in filelist:
             infohash = self.getInfohash(config.directory+'/'+filename)
             self.logger.debug(filename + ' : ' + infohash)
             if infohash != None:
                  try:
                     result = requests.get('http://'+AceConfig.acehost+':'+str(AceConfig.aceHTTPport)+'/server/api?method=get_media_files&infohash='+infohash, headers={'Connection':'close'}).json()['result']
                     for key in result:
                        self.playlist.append([result[key].translate(dict.fromkeys(map(ord, "%~}{][^$@*,-!?&`|><"))),
                                              infohash, key])
                  except:
                     self.playlist.append([filename.translate(dict.fromkeys(map(ord, "%~}{][^$@*,-!?&`|><"))),
                                           infohash, '0'])
        return True

    def getInfohash(self, filename):
        infohash = None
        try:
            with open(filename, "rb") as torrent_file:
                 metainfo = bencode.bdecode(torrent_file.read())
            infohash = hashlib.sha1(bencode.bencode(metainfo['info'])).hexdigest()
        except:
            self.logger.error("Failed to get Infohash from " + filename)
            pass
        return infohash

    def createPlaylist(self, hostport, reqtype, fmt):

        if config.updateevery == 0:
             self.playlistdata()
        self.playlist.sort(key=lambda data: data[0])

        ln = '#EXTM3U deinterlace=1 m3uautoload=1 cache=1000\n'
        for data in self.playlist:
             name = data[0]
             infohash  = data[1]
             key = data[2]
             ln += '#EXTINF:-1 group-title="TorrentFilms",' + name + '\n'
             if reqtype == 'proxyfilms':
                 ln += 'http://' + hostport + '/infohash/' + infohash + '/' + key
                 if fmt:
                    ln += '/stream.mp4/?fmt=' + fmt +'\n'
                 else:
                    ln += '/stream.mp4\n'
             else:
                  ln += 'http://' + AceConfig.acehost + ':'+str(AceConfig.aceHTTPport)+'/ace/' + config.streamtype + '?infohash=' + infohash + \
                        '&transcode_audio=' + str(AceConfig.transcode_audio) + \
                        '&transcode_mp3=' + str(AceConfig.transcode_mp3) + \
                        '&transcode_ac3=' + str(AceConfig.transcode_ac3) + \
                        '&preferred_audio_language=' + AceConfig.preferred_audio_language + '&_idx=' + key + '\n'

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
            url = urlparse.urlparse(connection.path)
            params = urlparse.parse_qs(url.query)
            fmt = params['fmt'][0] if params.has_key('fmt') else None

            exported = self.createPlaylist(connection.headers['Host'], connection.reqtype, fmt).encode('utf-8')

            connection.send_response(200)
            connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
            connection.send_header('Content-Length', str(len(exported)))
            connection.send_header('Connection', 'close')
            connection.end_headers()

            connection.wfile.write(exported)
