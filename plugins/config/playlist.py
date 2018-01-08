# -*- coding: utf-8 -*-
class PlaylistConfig():

    # Default playlist format
    m3uemptyheader = '#EXTM3U\n'
    m3uheader = '#EXTM3U url-tvg="http://1ttvapi.top/ttv.xmltv.xml.gz" deinterlace=1 m3uautoload=1 cache=1000\n'
    # If you need the #EXTGRP field put this #EXTGRP:%(group)s\n after %(name)s\n.
    m3uchanneltemplate = \
       '#EXTINF:-1 group-title="%(group)s" tvg-name="%(tvg)s" tvg-id="%(tvgid)s" tvg-logo="%(logo)s",%(name)s\n#EXTGRP:%(group)s\n%(url)s\n'

    # Channel names mapping. You may use this to rename channels.
    # Examples:
    # m3uchannelnames['Canal+ HD (France)'] = 'Canal+ HD'
    # m3uchannelnames['Sky Sport 1 HD (Italy)'] = 'Sky Sport 1 HD'
    m3uchannelnames = dict()

    # Similar to m3uchannelnames but for groups
    m3ugroupnames = dict()

    # Channel name to tvg name mappings.
    m3utvgnames = dict()
    # m3utvgnames['Channel name'] = 'Tvg_name'

    # Playlist sorting options.
    sort = False
    sortByName = False
    sortByGroupName = False

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
            if not setKey:
                setKey = key

            if isinstance(value, str):
                value = replacementsDict.get(value)
                if value:
                    item[setKey] = value
            elif isinstance(value, unicode):
                value = replacementsDict.get(value.encode('utf8'))
                if value:
                    item[setKey] = value.decode('utf8')

    # This comparator is used for the playlist sorting.
    @staticmethod
    def compareItems(i1, i2):
        result = -1
        if PlaylistConfig.sortByGroupName:
            result = cmp(i1.get('group', ''), i2.get('group', ''))
            if result != 0:
                return result
        if PlaylistConfig.sortByName:
            result = cmp(i1.get('name', ''), i2.get('name', ''))
        return result
