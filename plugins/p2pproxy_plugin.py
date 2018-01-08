# -*- coding: utf-8 -*- 
"""
P2pProxy response simulator
Uses torrent-tv API for it's work

What is this plugin for?
 It repeats the behavior of p2pproxy to support programs written for using p2pproxy

 Some of examples for what you can use this plugin:
    Comfort TV++ widget
    Official TorrentTV widget for Smart TV
    Kodi p2pproxy pvr plugin
    etc...

!!! It requires some changes in aceconfig.py:
    set the httpport to 8081
    set the vlcoutport to some other port (8082 for example)
"""
__author__ = 'miltador'

import logging
import re
import requests
import urlparse
import base64
from aceconfig import AceConfig
from torrenttv_api import TorrentTvApi
from datetime import date, timedelta
import time

from modules.PluginInterface import AceProxyPlugin
from modules.PlaylistGenerator import PlaylistGenerator
import config.p2pproxy as config


class P2pproxy(AceProxyPlugin):
    TTV = 'http://1ttv.org/'
    TTVU = TTV + 'uploads/'
    handlers = ('channels', 'channels.m3u', 'archive', 'xbmc.pvr', 'logos')
    logger = logging.getLogger('plugin_p2pproxy')

    def __init__(self, AceConfig, AceStuff):
        super(P2pproxy, self).__init__(AceConfig, AceStuff)
        self.params = None
        self.api = TorrentTvApi(config.email, config.password, config.sessiontimeout, config.zoneid)

    def handle(self, connection, headers_only=False):
        P2pproxy.logger.debug('Handling request')

        hostport = connection.headers['Host']

        query = urlparse.urlparse(connection.path).query
        self.params = urlparse.parse_qs(query)

        if connection.reqtype == 'channels' or connection.reqtype == 'channels.m3u':  # /channels/ branch
            if len(connection.splittedpath) == 3 and connection.splittedpath[2].split('?')[
                0] == 'play':  # /channels/play?id=[id]
                channel_id = self.get_param('id')
                if not channel_id:
                    # /channels/play?id=&_=[epoch timestamp] is Torrent-TV widget proxy check
                    # P2pProxy simply closes connection on this request sending Server header, so do we
                    if self.get_param('_'):
                        P2pproxy.logger.debug('Status check')
                        connection.send_response(200)
                        connection.send_header('Access-Control-Allow-Origin', '*')
                        connection.send_header('Connection', 'close')
                        connection.send_header('Content-Type', 'text/plain;charset=utf-8')
                        connection.send_header('Server', 'P2pProxy/1.0.4.4 AceProxy')
                        connection.wfile.write('\r\n')
                        return
                    else:
                        connection.dieWithError()  # Bad request
                        return

                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                    connection.end_headers()
                    return

                stream_url = None
                stream_type, stream, translations_list = self.api.stream_source(channel_id)
                name=logo=''

                for channel in translations_list:
                    if channel.getAttribute('id') == channel_id:
                        name = channel.getAttribute('name')
                        logo = channel.getAttribute('logo')
                        if config.fullpathlogo:
                            logo = P2pproxy.TTVU + logo
                        break

                if stream_type == 'torrent':
                    stream_url = re.sub('^(http.+)$',
                                        lambda match: '/torrent/' + requests.utils.quote(match.group(0), '') + '/stream.mp4',
                                        stream)
                elif stream_type == 'contentid':
                    stream_url = re.sub('^([0-9a-f]{40})',
                                        lambda match: '/pid/' + requests.utils.quote(match.group(0), '') + '/stream.mp4',
                                        stream)
                connection.path = stream_url
                connection.splittedpath = stream_url.split('/')
                connection.reqtype = connection.splittedpath[1].lower()
                connection.handleRequest(headers_only, name, logo, fmt=self.get_param('fmt'))
            elif connection.reqtype == 'channels.m3u' or self.get_param('type') == 'm3u':  # /channels/?filter=[filter]&group=[group]&type=m3u
                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                    connection.end_headers()
                    return

                param_group = self.params.get('group')
                param_filter = self.get_param('filter')
                if not param_filter:
                    param_filter = 'all'  # default filter
                if param_group:
                    if 'all' in param_group:
                        param_group = None
                    else:
                        tmp = []
                        for g in param_group:
                            tmp += g.split(',')
                        param_group = tmp

                translations_list = self.api.translations(param_filter)

                playlistgen = PlaylistGenerator()
                P2pproxy.logger.debug('Generating requested m3u playlist')
                for channel in translations_list:
                    group_id = channel.getAttribute('group')

                    if param_group and not group_id in param_group:  # filter channels by group
                        continue

                    name = channel.getAttribute('name')
                    group = TorrentTvApi.CATEGORIES[int(group_id)].decode('utf-8')
                    cid = channel.getAttribute('id')
                    logo = channel.getAttribute('logo')
                    if config.fullpathlogo:
                        logo = P2pproxy.TTVU + logo

                    fields = {'name': name, 'id': cid, 'url': cid, 'group': group, 'logo': logo}
                    fields['tvgid'] = config.tvgid % fields
                    playlistgen.addItem(fields)

                P2pproxy.logger.debug('Exporting')
                header = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' % (config.tvgurl, config.tvgshift)
                exported = playlistgen.exportm3u(hostport=hostport, header=header, fmt=self.get_param('fmt')).encode('utf-8')
                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)
            else:  # /channels/?filter=[filter]
                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Access-Control-Allow-Origin', '*')
                    connection.send_header('Connection', 'close')
                    connection.send_header('Content-Type', 'text/xml;charset=utf-8')
                    connection.end_headers()
                    return

                param_filter = self.get_param('filter')
                if not param_filter:
                    param_filter = 'all'  # default filter

                translations_list = self.api.translations(param_filter, True)

                P2pproxy.logger.debug('Exporting')
                connection.send_response(200)
                connection.send_header('Access-Control-Allow-Origin', '*')
                connection.send_header('Connection', 'close')
                connection.send_header('Content-Type', 'text/xml;charset=utf-8')
                connection.send_header('Content-Length', str(len(translations_list)))
                connection.end_headers()
                connection.wfile.write(translations_list)
        elif connection.reqtype == 'xbmc.pvr':  # same as /channels request
            if len(connection.splittedpath) == 3 and connection.splittedpath[2] == 'playlist':
                connection.send_response(200)
                connection.send_header('Access-Control-Allow-Origin', '*')
                connection.send_header('Connection', 'close')
                connection.send_header('Content-Type', 'text/xml;charset=utf-8')

                if headers_only:
                    connection.end_headers()
                    return

                translations_list = self.api.translations('all', True)
                connection.send_header('Content-Length', str(len(translations_list)))
                connection.end_headers()
                P2pproxy.logger.debug('Exporting')
                connection.wfile.write(translations_list)
        elif connection.reqtype == 'archive':  # /archive/ branch
            if len(connection.splittedpath) >= 3 and (connection.splittedpath[2] == 'dates' or connection.splittedpath[2] == 'dates.m3u'):  # /archive/dates.m3u
                d = date.today()
                delta = timedelta(days=1)
                playlistgen = PlaylistGenerator()
                hostport = connection.headers['Host']
                days = int(self.get_param('days')) if self.params.has_key('days') else 7
                suffix = '&suffix=' + self.get_param('suffix') if self.params.has_key('suffix') else ''
                for i in range(days):
                    dfmt = d.strftime('%d-%m-%Y')
                    url = 'http://%s/archive/playlist/?date=%s%s' % (hostport, dfmt, suffix) 
                    playlistgen.addItem({'group': '', 'tvg': '', 'name': dfmt, 'url': url})
                    d = d - delta
                exported = playlistgen.exportm3u(hostport, empty_header=True, process_url=False, fmt=self.get_param('fmt')).encode('utf-8')
                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)
                return
            elif len(connection.splittedpath) >= 3 and (connection.splittedpath[2] == 'playlist' or connection.splittedpath[2] == 'playlist.m3u'):  # /archive/playlist.m3u
                dates = list()

                if self.params.has_key('date'):
                    for d in self.params['date']:
                        dates.append(self.parse_date(d).strftime('%d-%m-%Y').replace('-0', '-'))
                else:
                    d = date.today()
                    delta = timedelta(days=1)
                    days = int(self.get_param('days')) if self.params.has_key('days') else 7
                    for i in range(days):
                        dates.append(d.strftime('%d-%m-%Y').replace('-0', '-'))
                        d = d - delta

                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')

                if headers_only:
                    connection.end_headers()
                    return

                channels_list = self.api.archive_channels()
                hostport = connection.headers['Host']
                playlistgen = PlaylistGenerator()
                suffix = '&suffix=' + self.get_param('suffix') if self.params.has_key('suffix') else ''

                for channel in channels_list:
                        epg_id = channel.getAttribute('epg_id')
                        name = channel.getAttribute('name')
                        logo = channel.getAttribute('logo')
                        if logo != '' and config.fullpathlogo:
                            logo = P2pproxy.TTVU + logo
                        for d in dates:
                            n = name + ' (' + d + ')' if len(dates) > 1 else name
                            url = 'http://%s/archive/?type=m3u&date=%s&channel_id=%s%s' % (hostport, d, epg_id, suffix)
                            playlistgen.addItem({'group': name, 'tvg': '', 'name': n, 'url': url, 'logo': logo})

                exported = playlistgen.exportm3u(hostport, empty_header=True, process_url=False, fmt=self.get_param('fmt')).encode('utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)
                return
            elif len(connection.splittedpath) == 3 and connection.splittedpath[2] == 'channels':  # /archive/channels
                connection.send_response(200)
                connection.send_header('Access-Control-Allow-Origin', '*')
                connection.send_header('Connection', 'close')
                connection.send_header('Content-Type', 'text/xml;charset=utf-8')

                if headers_only:
                    connection.end_headers()
                else:
                    archive_channels = self.api.archive_channels(True)
                    P2pproxy.logger.debug('Exporting')
                    connection.send_header('Content-Length', str(len(archive_channels)))
                    connection.end_headers()
                    connection.wfile.write(archive_channels)

                return
            if len(connection.splittedpath) == 3 and connection.splittedpath[2].split('?')[
                0] == 'play':  # /archive/play?id=[record_id]
                record_id = self.get_param('id')
                if not record_id:
                    connection.dieWithError()  # Bad request
                    return

                if headers_only:
                    connection.send_response(200)
                    connection.send_header("Content-Type", "video/mpeg")
                    connection.end_headers()
                    return

                stream_url = None

                stream_type, stream = self.api.archive_stream_source(record_id)

                if stream_type == 'torrent':
                    stream_url = re.sub('^(http.+)$',
                                        lambda match: '/torrent/' + requests.utils.quote(match.group(0), '') + '/stream.mp4',
                                        stream)
                elif stream_type == 'contentid':
                    stream_url = re.sub('^([0-9a-f]{40})',
                                        lambda match: '/pid/' + requests.utils.quote(match.group(0), '') + '/stream.mp4',
                                        stream)
                connection.path = stream_url
                connection.splittedpath = stream_url.split('/')
                connection.reqtype = connection.splittedpath[1].lower()
                connection.handleRequest(headers_only, fmt=self.get_param('fmt'))
            elif self.get_param('type') == 'm3u':  # /archive/?type=m3u&date=[param_date]&channel_id=[param_channel]
                d = self.get_date_param()

                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                    connection.end_headers()
                    return

                playlistgen = PlaylistGenerator()
                param_channel = self.get_param('channel_id')
                d = d.strftime('%d-%m-%Y').replace('-0', '-')

                if param_channel == '' or not param_channel:
                    channels_list = self.api.archive_channels()

                    for channel in channels_list:
                            channel_id = channel.getAttribute('epg_id')
                            try:
                                records_list = self.api.records(channel_id, d)
                                channel_name = channel.getAttribute('name')
                                logo = channel.getAttribute('logo')
                                if logo != '' and config.fullpathlogo:
                                    logo = P2pproxy.TTVU + logo

                                for record in records_list:
                                    name = record.getAttribute('name')
                                    record_id = record.getAttribute('record_id')
                                    playlistgen.addItem({'group': channel_name, 'tvg': '',
                                        'name': name, 'url': record_id, 'logo': logo})
                            except:
                                P2pproxy.logger.debug('Failed to load archive for ' + channel_id)

                else:
                    records_list = self.api.records(param_channel, d)
                    channels_list = self.api.archive_channels()
                    P2pproxy.logger.debug('Generating archive m3u playlist')

                    for record in records_list:
                        record_id = record.getAttribute('record_id')
                        channel_id = record.getAttribute('epg_id')
                        name = record.getAttribute('name')
                        d = time.localtime(float(record.getAttribute('time')))
                        n = '%.2d:%.2d %s' % (d.tm_hour, d.tm_min, name)
                        logo = ''
                        for channel in channels_list:
                            if channel.getAttribute('epg_id') == channel_id:
                                channel_name = channel.getAttribute('name')
                                logo = channel.getAttribute('logo')

                        if channel_name != '':
                            name = '(' + channel_name + ') ' + name
                        if logo != '' and config.fullpathlogo:
                            logo = P2pproxy.TTVU + logo

                        playlistgen.addItem({'group': channel_name, 'name': n, 'url': record_id, 'logo': logo, 'tvg': ''})

                P2pproxy.logger.debug('Exporting')
                exported = playlistgen.exportm3u(hostport, empty_header=True, archive=True, fmt=self.get_param('fmt')).encode('utf-8')

                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)
            else:  # /archive/?date=[param_date]&channel_id=[param_channel]
                param_date = self.get_param('date')
                if not param_date:
                    d = date.today()
                else:
                    try:
                        param_date = param_date.split('-')
                        d = date(int(param_date[2]), int(param_date[1]), int(param_date[0]))
                    except IndexError:
                        P2pproxy.logger.error('date param is not correct!')
                        connection.dieWithError()
                        return
                param_channel = self.get_param('channel_id')
                if param_channel == '' or not param_channel:
                    P2pproxy.logger.error('Got /archive/ request but no channel_id specified!')
                    connection.dieWithError()
                    return


                connection.send_response(200)
                connection.send_header('Access-Control-Allow-Origin', '*')
                connection.send_header('Connection', 'close')
                connection.send_header('Content-Type', 'text/xml;charset=utf-8')

                if headers_only:
                    connection.end_headers()
                else:
                    records_list = self.api.records(param_channel, d.strftime('%d-%m-%Y'), True)
                    P2pproxy.logger.debug('Exporting')
                    connection.send_header('Content-Length', str(len(records_list)))
                    connection.end_headers()
                    connection.wfile.write(records_list)
        elif connection.reqtype == 'logos':  # Used to generate logomap for the torrenttv plugin
            translations_list = self.api.translations('all')
            last = translations_list[-1]
            connection.send_response(200)
            connection.send_header('Content-Type', 'text/plain;charset=utf-8')
            connection.end_headers()
            connection.wfile.write("logobase = '" + P2pproxy.TTVU + "'\n")
            connection.wfile.write("logomap = {\n")

            for channel in translations_list:
                name = channel.getAttribute('name').encode('utf-8')
                logo = channel.getAttribute('logo').encode('utf-8')
                connection.wfile.write("    u'%s': logobase + '%s'" % (name, logo))
                if not channel == last:
                    connection.wfile.write(",\n")
                else:
                    connection.wfile.write("\n")

            connection.wfile.write("}\n")

    def get_param(self, key):
        if key in self.params:
            return self.params[key][0]
        else:
            return None

    def get_date_param(self):
        d = self.get_param('date')

        if not d:
            return date.today()
        else:
            return self.parse_date(d)

    def parse_date(self, d):
        try:
            param_date = d.split('-')
            return date(int(param_date[2]), int(param_date[1]), int(param_date[0]))
        except IndexError as e:
            P2pproxy.logger.error('date param is not correct!')
            raise e
