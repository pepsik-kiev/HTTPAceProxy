# -*-coding=utf-8-*-

'''
This is the example of plugin.
Rename this file to helloworld_plugin.py to enable it.
To use it, go to http://127.0.0.1:8000/helloworld
'''

import requests
import logging
import config.rutor as config
from urlparse import urlparse, parse_qs
from rutor_api import SearchN
from modules.PlaylistGenerator import PlaylistGenerator
from modules.PluginInterface import AceProxyPlugin

class Rutor(AceProxyPlugin):
    handlers = ('rutor',)

    def __init__(self, AceConfig, AceStuff):
        self.params = None
        self.AceStuff = AceStuff
        self.logger = logging.getLogger('rutor')

    def send_playlist(self, connection, playlist):
        hostport = connection.headers['Host']
        exported = playlist.exportxml(hostport)
        exported = exported.encode('utf-8')
        connection.send_response(200)
        connection.send_header('Content-Type', 'application/xml')
        connection.send_header('Content-Length', str(len(exported)))
        connection.end_headers()
        connection.wfile.write(exported)

    def handle(self, connection, headers_only=False):

        query = urlparse(connection.path).query
        self.params = parse_qs(query)

        if connection.reqtype == 'rutor':
            if len(connection.splittedpath) < 2:
                connection.send_response(404)
                connection.send_header('Connection', 'close')
                connection.end_headers()
                return
            if len(connection.splittedpath) in (2, 3):
                # View Categories
                playlist = PlaylistGenerator()
                for cat in config.categories:
                    Title = "[%s]" % cat[1]
                    itemdict = {'title': Title,
                                'url': '/rutor/category/%s/' % cat[0],
                                'description_title': Title,
                                'description': '',
                                'type': 'channel'
                                }
                    playlist.addItem(itemdict)
                self.send_playlist(connection, playlist)

            if len(connection.splittedpath) == 5:
                if connection.splittedpath[2] == 'category':
                    category = connection.splittedpath[3]
                    #Sort options '0' - date , '2' - cid, '6' - name
                    sort = '0'
                    text = '0'
                    try: page = self.params['page'][0]
                    except: page = '1'
                    try: sort = self.params['sort'][0]
                    except: sort = '0'
                    spr = ['', '', '', '', '', '']
                    playlist = get_rutor_playlist(category, sort, text, spr, page)
                    self.send_playlist(connection, playlist)

                if connection.splittedpath[2] == 'list':
                    playlist = PlaylistGenerator()
                    torrent_url = connection.splittedpath[3]
                    torrent_url_unquoted = requests.utils.unquote(connection.splittedpath[3])
                    contentinfo = None
                    with self.AceStuff.clientcounter.lock:
                        if not self.AceStuff.clientcounter.idleace:
                            self.AceStuff.clientcounter.idleace = self.AceStuff.clientcounter.createAce()
                        contentinfo = self.AceStuff.clientcounter.idleace.GETCONTENTINFO('torrent', torrent_url_unquoted)
                    if contentinfo and contentinfo.get('status') in (1, 2) and contentinfo.get('files'):
                        infohash = contentinfo.get('infohash')
                        files = contentinfo.get('files')
                        files.sort()
                        for filename, fid in files:
                            Title = "[%s]" % unicode(requests.utils.unquote(filename.encode('utf-8')), 'UTF-8')
                            itemdict = {'title': Title,
                                        'url': '/infohash/%s/%s/%s' % (infohash, fid, 'stream.mp4'),
                                        'description_title': Title,
                                        'description': '',
                                        'type': 'stream'
                                        }
                            playlist.addItem(itemdict)
                    else:
                        Title = "[Not found files for play]"
                        itemdict = {'title': Title,
                                    'url': '/rutor/list/%s/' % torrent_url,
                                    'description_title': Title,
                                    'description': '',
                                    'type': 'channel',
                                    }
                        playlist.addItem(itemdict)
                    hostport = connection.headers['Host']
                    exported = playlist.exportxml(hostport)
                    exported = exported.encode('utf-8')
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'application/xml')
                    connection.send_header('Content-Length', str(len(exported)))
                    connection.end_headers()
                    connection.wfile.write(exported)


def get_rutor_playlist(category, sort, text, spr, parent_page):

    items_per_page = config.items_per_page-1
    items = []
    page = 0

    while len(items) < items_per_page * int(parent_page):
        rutor_list = SearchN(category, sort, text, spr, str(page), min_size=config.min_size, max_size=config.max_size, min_seeds=config.min_seeds, max_seeds=config.max_seeds)
        page += 1
        items += rutor_list

    playlist = PlaylistGenerator()
    for d in items[(items_per_page * int(parent_page) - items_per_page):items_per_page * int(parent_page)]:
        playlist.addItem(d)

    Title = u"[НАЙТИ ЕЩЕ]"
    itemdict = {'title': Title,
                'url': '/rutor/category/%s/?page=%s' % (category, int(page) + 1),
                'description_title': Title,
                'description': '',
                'type': 'channel'
                }
    playlist.addItem(itemdict)

    return playlist
