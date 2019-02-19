# -*- coding: utf-8 -*-
'''
Playlist Generator
This module can generate .m3u playlists with tv guide
and groups
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

from urllib3.packages.six.moves.urllib.parse import quote
from urllib3.packages.six import ensure_str
from playlist import PlaylistConfig as config

class PlaylistGenerator(object):

    def __init__(self,
                 m3uemptyheader=config.m3uemptyheader,
                 m3uheader=config.m3uheader,
                 m3uchanneltemplate=config.m3uchanneltemplate,
                 changeItem=config.changeItem,
                 sort=config.sortItems if config.sort else None):
        self.itemlist = list()
        self.m3uemptyheader = m3uemptyheader
        self.m3uheader = m3uheader
        self.m3uchanneltemplate = m3uchanneltemplate
        self.changeItem = changeItem
        self.sort = sort

    def addItem(self, itemdict):
        '''
        Adds and remap item to the list
        itemdict is a dictionary with the following fields:

        name - channel name
        url - channel URL
        tvg - channel tvg-name (optional)
        tvgid - channel tvg-id (optional)
        group - channel playlist group-title (optional)
        logo - channel picon file tvg-logo (optional)
        '''
        # Remap items
        self.changeItem(itemdict)
        # Check and add missing items and their values
        itemdict['tvg'] = itemdict['tvg'] if itemdict.get('tvg') else itemdict.get('name')
        if not itemdict.get('tvgid'): itemdict['tvgid'] = itemdict['tvg']
        if not itemdict.get('group'): itemdict['group'] = ''
        if not itemdict.get('logo'): itemdict['logo'] = 'http://static.acestream.net/sites/acestream/img/ACE-logo.png'
        # Add items
        self.itemlist.append(itemdict)

    def exportm3u(self, hostport, path='', add_ts=False, empty_header=False, archive=False,
                     process_url=True, header=None, fmt=None, _bytearray=bytearray):
        '''
        Exports m3u playlist
        '''
        if add_ts: hostport = 'ts://%s' % hostport  # Adding ts:// after http:// for some players

        if header is None: itemlist = self.m3uheader if not empty_header else self.m3uemptyheader
        else: itemlist = header

        items = self.sort(self.itemlist) if self.sort else self.itemlist
        for i in items:
           item = i # {'group': XXX, 'tvg': XXX, 'logo': XXX, 'name': XXX, 'tvgid': XXX}
           name = quote(ensure_str(item.get('name').replace('"', "'").replace(',', '.')),'')
           url = item['url']
           if process_url:
              if url.startswith(('http://', 'https://')) and url.endswith(('.acelive', '.acestream', '.acemedia', '.torrent')): # For .acelive and .torrent
                 item['url'] = 'http://%s/url/%s/%s.ts' % (hostport, quote(url,''), name)
              elif url.startswith('infohash://'): # For INFOHASHes
                 item['url'] = 'http://%s/infohash/%s/%s.ts' % (hostport, url.split('/')[2], name)
              elif url.startswith('acestream://'): # For PIDs
                 item['url'] = 'http://%s/content_id/%s/%s.ts' % (hostport, url.split('/')[2], name)
              elif archive and url.isdigit(): # For archive channel id's
                 item['url'] = 'http://%s/archive/play?id=%s' % (hostport, url)
              elif not archive and url.isdigit(): # For channel id's
                 item['url'] = 'http://%s/channels/play?id=%s' % (hostport, url)
              elif path.endswith('channel'): # For plugins  channel name maping
                 item['url'] = 'http://%s%s/%s' % (hostport, path, url)

           if fmt: item['url'] += '&fmt=%s' % fmt if '?' in item['url'] else '/?fmt=%s' % fmt

           itemlist += self.m3uchanneltemplate % item #Generates EXTINF line with url

        return _bytearray(itemlist, 'utf-8')

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
