# -*- coding: utf-8 -*-
class PlaylistConfig():

    # Default playlist format
    m3uemptyheader = '#EXTM3U\n'
    m3uheader = '#EXTM3U deinterlace=1 m3uautoload=1 cache=1000\n'
    # If you need the #EXTGRP field put this #EXTGRP:%(group)s\n after %(name)s\n.
    m3uchanneltemplate = \
       '#EXTINF:-1 group-title="%(group)s" tvg-name="%(tvg)s" tvg-id="%(tvgid)s" tvg-logo="%(logo)s",%(name)s\n#EXTGRP:%(group)s\n%(url)s\n'

    # Channel names mapping. You may use this to rename channels.
    m3uchannelnames = dict()
    # Examples:
    m3uchannelnames['A1'] = 'Amedia 1'
    m3uchannelnames['A2'] = 'Amedia 2'
    m3uchannelnames['Da Vinci'] = 'Da Vinci Learning'
    m3uchannelnames['5 канал'] = 'Пятый канал'
    m3uchannelnames['TV XXI'] = 'TV XXI (TV21)'
    m3uchannelnames['TV1000 Русское кино'] = 'TV 1000 Русское кино'
    m3uchannelnames['Travel+Adventure'] = 'Travel + Adventure'
    m3uchannelnames['Первый'] = 'Первый канал'
    m3uchannelnames['ТВ3'] = 'ТВ 3'
    m3uchannelnames['КХЛ'] = 'КХЛ ТВ'
    m3uchannelnames['Канал Disney'] = 'Disney Channel'
    m3uchannelnames['Бобёр']  = 'Бобер'
    m3uchannelnames['Наука'] = 'Наука 2.0'
    m3uchannelnames['Russian Travel Guide'] = 'RTG TV'
    m3uchannelnames['Иллюзион +'] = 'Иллюзион+'
    m3uchannelnames['РТВ - Любимое кино'] = 'Наше Любимое Кино'
    m3uchannelnames['ТВ Центр'] = 'ТВЦ'

    # Similar to m3uchannelnames but for groups
    m3ugroupnames = dict()

    # Channel name to tvg name mappings.
    m3utvgnames = dict()
    # m3utvgnames['Channel name'] = 'Tvg_name'

    # Playlist sorting options.
    sort = False
    sortByName = False
    sortByGroup = False

    # This comparator is used for the playlist sorting.
    @staticmethod
    def sortItems(itemlist):
        if PlaylistConfig.sortByGroup: return sorted(itemlist, key=lambda x:x['group'])
        elif PlaylistConfig.sortByName: return sorted(itemlist, key=lambda x:x['name'])
        else: return itemlist

    # This method can be used to change a channel info such as name, group etc.
    # The following fields can be changed:
    #
    #    name - channel name
    #    url - channel URL
    #    tvg - channel tvg name
    #    tvgid - channel tvg id
    #    group - channel group
    #    logo - channel logo
    @staticmethod
    def changeItem(item):
        PlaylistConfig._changeItemByDict(item, 'name', PlaylistConfig.m3uchannelnames)
        PlaylistConfig._changeItemByDict(item, 'group', PlaylistConfig.m3ugroupnames)
        PlaylistConfig._changeItemByDict(item, 'name', PlaylistConfig.m3utvgnames, 'tvg')

    @staticmethod
    def _changeItemByDict(item, key, replacementsDict, setKey=None):
        if len(replacementsDict) > 0:
            value = item[key]
            if not setKey: setKey = key

            if type(value) == str:
                value = replacementsDict.get(value)
                if value: item[setKey] = value
            elif type(value) == unicode:
                value = replacementsDict.get(value.encode('utf8'))
                if value: item[setKey] = value.decode('utf8')

    xml_template = """<?xml version="1.0" encoding="utf-8"?>
    <items>
    <playlist_name>Playlist</playlist_name>

    %(items)s

    </items>
    """

    xml_channel_template = """
    <channel>
      <title><![CDATA[%(title)s]]></title>
      <description><![CDATA[<tr><td>%(description_title)s</td></tr>]]></description>
      <playlist_url>%(hostport)s%(url)s</playlist_url>
    </channel>
    """

    xml_stream_template = """
    <channel>
      <title><![CDATA[%(title)s]]></title>
      <description><![CDATA[<tr><td>%(description_title)s</td></tr>]></description>
      <stream_url><![CDATA[%(hostport)s%(url)s]]></stream_url>
    </channel>
    """
