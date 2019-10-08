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
import gevent
import zlib
from utils import schedule, query_get
import config.torrentfilms as config

class Torrentfilms(object):

    handlers = ('films', 'proxyfilms')

    def __init__(self, AceConfig, AceProxy):
        self.config = AceConfig
        self.logger = logging.getLogger('plugin_TorrentFilms')
        self.playlist = []
        self.videoextdefaults = ('.3gp','.aac','.ape','.asf','.avi','.dv','.divx','.flac','.flc','.flv','.m2ts','.m4a','.mka','.mkv',
                                 '.mpeg','.mpeg4','.mpegts','.mpg4','.mp3','.mp4','.mpg','.mov','.m4v','.ogg','.ogm','.ogv','.oga',
                                 '.ogx','.qt','.rm','.swf','.ts','.vob','.wmv','.wav','.webm')
        if config.updateevery: schedule(config.updateevery * 60, self.playlistdata)

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

    def handle(self, connection):

        exported = self.createPlaylist(connection.headers['Host'], connection.reqtype, query_get(connection.query, 'fmt')).encode('utf-8')

        connection.send_response(200)
        connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
        connection.send_header('Access-Control-Allow-Origin', '*')
        try:
           h = connection.headers.get('Accept-Encoding').split(',')[0]
           compress_method = { 'zlib': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS),
                               'deflate': zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS),
                               'gzip': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16) }
           exported = compress_method[h].compress(exported) + compress_method[h].flush()
           connection.send_header('Content-Encoding', h)
        except: pass
        connection.send_header('Content-Length', len(exported))
        connection.send_header('Connection', 'close')
        connection.end_headers()
        connection.wfile.write(exported)
