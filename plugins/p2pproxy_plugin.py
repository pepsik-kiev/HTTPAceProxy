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
"""
__author__ = 'miltador, Dorik1972'

import logging
from requests.compat import quote, unquote
from torrenttv_api import TorrentTvApi
from datetime import timedelta, datetime

from PluginInterface import AceProxyPlugin
from PlaylistGenerator import PlaylistGenerator
try: from urlparse import parse_qs
except: from urllib.parse import parse_qs
import config.p2pproxy as config

class P2pproxy(AceProxyPlugin):
    TTV = 'http://1ttv.org/'
    TTVU = TTV + 'uploads/'
    handlers = ('channels', 'channels.m3u', 'archive', 'xbmc.pvr', 'logos')
    logger = logging.getLogger('plugin_p2pproxy')

    def __init__(self, AceConfig, AceStuff): pass

    def handle(self, connection, headers_only=False):
        P2pproxy.logger.debug('Handling request')

        hostport = connection.headers['Host']
        self.params = parse_qs(connection.query)

        # /channels/ branch
        if connection.reqtype in ('channels', 'channels.m3u'):

            if connection.path.endswith('play'):  # /channels/play?id=[id]
                channel_id = self.params.get('id', [''])[0]
                if not channel_id:
                    # /channels/play?id=&_=[epoch timestamp] is Torrent-TV widget proxy check
                    # P2pProxy simply closes connection on this request sending Server header, so do we
                    if self.params.get('_', [''])[0]:
                        P2pproxy.logger.debug('Status check')
                        response_headers = {'Content-Type': 'text/plain;charset=utf-8', 'Server': 'P2pProxy/1.0.4.4 HTTPAceProxy',
                                            'Access-Control-Allow-Origin': '*', 'Connection': 'close'}
                        connection.send_response(200)
                        for k,v in list(response_headers.items()): connection.send_header(k,v)
                        connection.wfile.write('\r\n')
                        return
                    else:
                        connection.dieWithError(400, 'Bad request')  # Bad request
                        return

                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'video/mpeg')
                    connection.end_headers()
                    return

                stream_type, stream, translations_list = TorrentTvApi(config.email, config.password).stream_source(channel_id)
                name=logo=''

                for channel in translations_list:
                    if channel.getAttribute('id') == channel_id:
                        name = channel.getAttribute('name')
                        logo = channel.getAttribute('logo')
                        if logo != '' and config.fullpathlogo: logo = P2pproxy.TTVU + logo
                        break

                if stream_type not in (b'torrent', b'contentid'):
                    connection.dieWithError(404, 'Unknown stream type: %s' % stream_type, logging.ERROR); return
                elif stream_type == b'torrent': connection.path = '/url/%s/stream.mp4' % quote(stream,'')
                elif stream_type == b'contentid': connection.path = '/content_id/%s/stream.mp4' % stream

                connection.splittedpath = connection.path.split('/')
                connection.reqtype = connection.splittedpath[1].lower()
                connection.handleRequest(headers_only, name, logo, fmt=self.params.get('fmt', [''])[0])

            # /channels/?filter=[filter]&group=[group]&type=m3u
            elif connection.reqtype == 'channels.m3u' or self.params.get('type', [''])[0] == 'm3u':
                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                    connection.end_headers()
                    return

                param_group = self.params.get('group', [''])[0]
                if param_group and 'all' in param_group: param_group = None

                translations_list = TorrentTvApi(config.email, config.password).translations(self.params.get('filter', ['all'])[0])

                playlistgen = PlaylistGenerator(m3uchanneltemplate=config.m3uchanneltemplate)
                P2pproxy.logger.debug('Generating requested m3u playlist')
                for channel in translations_list:
                    group_id = channel.getAttribute('group')
                    if param_group and not group_id in param_group: continue # filter channels by &group=1,2,5...

                    name = channel.getAttribute('name')
                    group = TorrentTvApi.CATEGORIES[int(group_id)]
                    cid = channel.getAttribute('id')
                    logo = channel.getAttribute('logo')
                    if logo != '' and config.fullpathlogo: logo = P2pproxy.TTVU + logo

                    fields = {'name': name, 'id': cid, 'url': cid, 'group': group, 'logo': logo}
                    if channel.getAttribute('epg_id') != '0': fields['tvgid'] = config.tvgid % fields
                    playlistgen.addItem(fields)

                P2pproxy.logger.debug('Exporting m3u playlist')
                exported = playlistgen.exportm3u(hostport=hostport, header=config.m3uheadertemplate, fmt=self.params.get('fmt', [''])[0]).encode('utf-8')
                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)

            # /channels/?filter=[filter]
            else:
                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Access-Control-Allow-Origin', '*')
                    connection.send_header('Connection', 'close')
                    connection.send_header('Content-Type', 'text/xml;charset=utf-8')
                    connection.end_headers()
                    return

                translations_list = TorrentTvApi(config.email, config.password).translations(self.params.get('filter', ['all'])[0], True)

                P2pproxy.logger.debug('Exporting m3u playlist')
                response_headers = {'Access-Control-Allow-Origin': '*', 'Connection': 'close',
                                    'Content-Type': 'text/xml;charset=utf-8', 'Content-Length': str(len(translations_list)) }
                connection.send_response(200)
                for k,v in list(response_headers.items()): connection.send_header(k,v)
                connection.end_headers()
                connection.wfile.write(translations_list)

        # same as /channels request
        elif connection.reqtype == 'xbmc.pvr' and connection.path.endswith('playlist'):
            connection.send_response(200)
            connection.send_header('Access-Control-Allow-Origin', '*')
            connection.send_header('Connection', 'close')
            connection.send_header('Content-Type', 'text/xml;charset=utf-8')

            if headers_only:
                connection.end_headers()
                return

            translations_list = TorrentTvApi(config.email, config.password).translations('all', True)
            connection.send_header('Content-Length', str(len(translations_list)))
            connection.end_headers()
            P2pproxy.logger.debug('Exporting m3u playlist')
            connection.wfile.write(translations_list)

        # /archive/ branch
        elif connection.reqtype == 'archive':
            if connection.path.endswith(('dates', 'dates.m3u')):  # /archive/dates.m3u
                d = datetime.now()
                delta = timedelta(days=1)
                playlistgen = PlaylistGenerator()
                hostport = connection.headers['Host']
                days = int(self.params.get('days', ['7'])[0])
                suffix = '&suffix=%s' % self.params.get('suffix', [''])[0]
                for i in range(days):
                    dfmt = d.strftime('%d-%m-%Y')
                    url = 'http://%s/archive/playlist/?date=%s%s' % (hostport, dfmt, suffix)
                    playlistgen.addItem({'group': '', 'tvg': '', 'name': dfmt, 'url': url})
                    d -= delta
                exported = playlistgen.exportm3u(hostport, empty_header=True, process_url=False, fmt=self.params.get('fmt', [''])[0]).encode('utf-8')
                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)
                return

            elif connection.path.endswith(('playlist', 'playlist.m3u')):  # /archive/playlist.m3u
                dates = list()

                if 'date' in self.params:
                    for d in self.params['date']:
                        dates.append(self.parse_date(d).strftime('%d-%m-%Y'))
                else:
                    d = datetime.now()
                    delta = timedelta(days=1)
                    days = int(self.params.get('days', ['7'])[0])
                    for i in range(days):
                        dates.append(d.strftime('%d-%m-%Y'))
                        d -= delta

                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')

                if headers_only:
                    connection.end_headers()
                    return

                channels_list = TorrentTvApi(config.email, config.password).archive_channels()
                hostport = connection.headers['Host']
                playlistgen = PlaylistGenerator()
                suffix = '&suffix=%s' % self.params.get('suffix', [''])[0]

                for channel in channels_list:
                        epg_id = channel.getAttribute('epg_id')
                        name = channel.getAttribute('name')
                        logo = channel.getAttribute('logo')
                        if logo != '' and config.fullpathlogo: logo = P2pproxy.TTVU + logo
                        for d in dates:
                            n = name + ' (' + d + ')' if len(dates) > 1 else name
                            url = 'http://%s/archive/?type=m3u&date=%s&channel_id=%s%s' % (hostport, d, epg_id, suffix)
                            playlistgen.addItem({'group': name, 'tvg': '', 'name': n, 'url': url, 'logo': logo})

                exported = playlistgen.exportm3u(hostport, empty_header=True, process_url=False, fmt=self.params.get('fmt', [''])[0]).encode('utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)
                return

            elif connection.path.endswith('channels'):  # /archive/channels
                connection.send_response(200)
                connection.send_header('Access-Control-Allow-Origin', '*')
                connection.send_header('Connection', 'close')
                connection.send_header('Content-Type', 'text/xml;charset=utf-8')

                if headers_only: connection.end_headers()
                else:
                    archive_channels = TorrentTvApi(config.email, config.password).archive_channels(True)
                    P2pproxy.logger.debug('Exporting m3u playlist')
                    connection.send_header('Content-Length', str(len(archive_channels)))
                    connection.end_headers()
                    connection.wfile.write(archive_channels)
                return

            if connection.path.endswith('play'):  # /archive/play?id=[record_id]
                record_id = self.params.get('id', [''])[0]
                if not record_id:
                    connection.dieWithError(400, 'Bad request')  # Bad request
                    return

                if headers_only:
                    connection.send_response(200)
                    connection.send_header("Content-Type", "video/mpeg")
                    connection.end_headers()
                    return

                stream_type, stream = TorrentTvApi(config.email, config.password).archive_stream_source(record_id)

                if stream_type not in (b'torrent', b'contentid'):
                    connection.dieWithError(404, 'Unknown stream type: %s' % stream_type, logging.ERROR); return
                elif stream_type == b'torrent': connection.path = '/url/%s/stream.mp4' % quote(stream,'')
                elif stream_type == b'contentid': connection.path = '/content_id/%s/stream.mp4' % stream

                connection.splittedpath = connection.path.split('/')
                connection.reqtype = connection.splittedpath[1].lower()
                connection.handleRequest(headers_only, fmt=self.params.get('fmt', [''])[0])

            # /archive/?type=m3u&date=[param_date]&channel_id=[param_channel]
            elif self.params.get('type', [''])[0] == 'm3u':

                if headers_only:
                    connection.send_response(200)
                    connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                    connection.end_headers()
                    return

                playlistgen = PlaylistGenerator()
                param_channel = self.params.get('channel_id', [''])[0]
                d = self.get_date_param()

                if not param_channel:
                    channels_list = TorrentTvApi(config.email, config.password).archive_channels()

                    for channel in channels_list:
                            channel_id = channel.getAttribute('epg_id')
                            try:
                                records_list = TorrentTvApi(config.email, config.password).records(channel_id, d)
                                channel_name = channel.getAttribute('name')
                                logo = channel.getAttribute('logo')
                                if logo != '' and config.fullpathlogo: logo = P2pproxy.TTVU + logo

                                for record in records_list:
                                    name = record.getAttribute('name')
                                    record_id = record.getAttribute('record_id')
                                    playlistgen.addItem({'group': channel_name, 'tvg': '',
                                                         'name': name, 'url': record_id, 'logo': logo})
                            except: P2pproxy.logger.debug('Failed to load archive for %s' % channel_id)

                else:
                    records_list = TorrentTvApi(config.email, config.password).records(param_channel, d)
                    channels_list = TorrentTvApi(config.email, config.password).archive_channels()
                    P2pproxy.logger.debug('Generating archive m3u playlist')

                    for record in records_list:
                        record_id = record.getAttribute('record_id')
                        channel_id = record.getAttribute('epg_id')
                        name = record.getAttribute('name')
                        d = datetime.fromtimestamp(float(record.getAttribute('time'))).strftime('%H:%M')
                        n = '%s %s' % (d, name)
                        logo = ''
                        for channel in channels_list:
                            if channel.getAttribute('epg_id') == channel_id:
                                channel_name = channel.getAttribute('name')
                                logo = channel.getAttribute('logo')

                        if channel_name != '': name = '(' + channel_name + ') ' + name
                        if logo != '' and config.fullpathlogo: logo = P2pproxy.TTVU + logo

                        playlistgen.addItem({'group': channel_name, 'name': n, 'url': record_id, 'logo': logo, 'tvg': ''})

                P2pproxy.logger.debug('Exporting m3u playlist')
                exported = playlistgen.exportm3u(hostport, empty_header=True, archive=True, fmt=self.params.get('fmt', [''])[0]).encode('utf-8')

                connection.send_response(200)
                connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
                connection.send_header('Content-Length', str(len(exported)))
                connection.end_headers()
                connection.wfile.write(exported)

            # /archive/?date=[param_date]&channel_id=[param_channel]
            else:
                param_date = self.params.get('date', [''])[0]
                if not param_date: d = datetime.now()
                else:
                    try: d = parse_date(param_date)
                    except: return
                param_channel = self.params.get('channel_id', [''])[0]
                if not param_channel:
                    connection.dieWithError(500, 'Got /archive/ request but no channel_id specified!', logging.ERROR)
                    return

                connection.send_response(200)
                connection.send_header('Access-Control-Allow-Origin', '*')
                connection.send_header('Connection', 'close')
                connection.send_header('Content-Type', 'text/xml;charset=utf-8')

                if headers_only: connection.end_headers()
                else:
                    records_list = TorrentTvApi(config.email, config.password).records(param_channel, d.strftime('%d-%m-%Y'), True)
                    P2pproxy.logger.debug('Exporting m3u playlist')
                    connection.send_header('Content-Length', str(len(records_list)))
                    connection.end_headers()
                    connection.wfile.write(records_list)

        # Used to generate logomap for the torrenttv plugin
        elif connection.reqtype == 'logos':
            translations_list = TorrentTvApi(config.email, config.password).translations('all')
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
                connection.wfile.write(",\n") if not channel == last else connection.wfile.write("\n")

            connection.wfile.write("}\n")

    def get_date_param(self):
        d = self.params.get('date', [''])[0]
        return datetime.now() if not d else self.parse_date(d)

    def parse_date(self, d):
        try: return datetime.strptime(d, '%d-%m-%Y')
        except IndexError as e:
            P2pproxy.logger.error('date param is not correct!')
            raise e
