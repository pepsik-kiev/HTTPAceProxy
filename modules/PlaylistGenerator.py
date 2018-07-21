# -*- coding: utf-8 -*-
'''
Playlist Generator
This module can generate .m3u playlists with tv guide
and groups
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

from requests.compat import quote, urlparse
from playlist import PlaylistConfig as config

class PlaylistGenerator(object):

    def __init__(self,
                 m3uemptyheader=config.m3uemptyheader,
                 m3uheader=config.m3uheader,
                 m3uchanneltemplate=config.m3uchanneltemplate,
                 changeItem=config.changeItem,
                 comparator=config.compareItems if config.sort else None):
        self.itemlist = list()
        self.m3uemptyheader = m3uemptyheader
        self.m3uheader = m3uheader
        self.m3uchanneltemplate = m3uchanneltemplate
        self.changeItem = changeItem
        self.comparator = comparator

    def addItem(self, itemdict):
        '''
        Adds item to the list
        itemdict is a dictionary with the following fields:
            name - item name
            url - item URL
            tvg - item tvg name (optional)
            tvgid - item tvg id (optional)
            group - item playlist group (optional)
            logo - item logo file name (optional)
        '''
        self.itemlist.append(itemdict)

    def _generatem3uline(self, item):
        '''
        Generates EXTINF line with url
        '''
        return self.m3uchanneltemplate % item

    def _changeItems(self):
        for item in self.itemlist:
            self.changeItem(item)
            if not 'tvg' in item: item['tvg'] = item.get('name').replace(' ', '_')
            if not 'tvgid' in item: item['tvgid'] = ''
            if not 'group' in item: item['group'] = ''
            if not 'logo' in item: item['logo'] = ''

    def exportm3u(self, hostport, path='', add_ts=False, empty_header=False, archive=False, process_url=True, header=None, fmt=None):
        '''
        Exports m3u playlist
        '''
        if add_ts: hostport = 'ts://%s' % hostport  # Adding ts:// after http:// for some players

        if header is None: itemlist = self.m3uheader if not empty_header else self.m3uemptyheader
        else: itemlist = header

        self._changeItems()
        items = sorted(self.itemlist, cmp=self.comparator) if self.comparator else self.itemlist

        for i in items:
            item = i.copy()
            item['name'] = item['name'].replace('"', "'").replace(',', '.')
            url = item['url']
            if process_url and url:
                if url.endswith(('.acelive', '.acestream', '.acemedia', '.torrent')): # For .acelive and .torrent
                   item['url'] = 'http://%s/url/%s/stream.mp4' % (hostport, quote(url,''))
                elif url.startswith('infohash://'): # For INFOHASHes
                   item['url'] = 'http://%s/infohash/%s/stream.mp4' % (hostport, urlparse(url).netloc)
                elif url.startswith('acestream://'): # For PIDs
                   item['url'] = 'http://%s/content_id/%s/stream.mp4' % (hostport, urlparse(url).netloc)
                elif archive and url.isdigit(): # For archive channel id's
                   item['url'] = 'http://%s/archive/play?id=%s' % (hostport, url)
                elif not archive and url.isdigit(): # For channel id's
                   item['url'] = 'http://%s/channels/play?id=%s' % (hostport, url)
                elif path == '/torrenttv/channel' : # For channel name fot torrenttv_pugin
                   item['url'] = 'http://%s%s/%s' % (hostport, path, url)

            if fmt: item['url'] += '&fmt=%s' % fmt if '?' in item['url'] else '/?fmt=%s' % fmt
            itemlist += self._generatem3uline(item)

        return itemlist

    def exportxml(self, hostport, path='',):

        try:
            chans = ''
            for i in self.itemlist:
                i['hostport'] = 'http://%s%s' % (hostport, path)
                try:
                    if i['type'] == 'channel': chans += config.xml_channel_template % i
                    else: chans += config.xml_stream_template % i
                except: chans += config.xml_channel_template % i
            return config.xml_template % {'items': chans}
        except: return ''
