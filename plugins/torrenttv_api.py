# -*- coding: utf-8 -*-
"""
Torrent-TV API communication class
Forms requests to API, checks result for errors and returns in desired form (lists or raw data)
"""

__author__ = 'miltador, Dorik1972'

import requests
import xml.dom.minidom as dom
import logging
try: from ConfigParser import RawConfigParser
except: from configparser import RawConfigParser

requests.adapters.DEFAULT_RETRIES = 5

class TorrentTvApiException(Exception):
    """
    Exception from Torrent-TV API
    """
    pass

class TorrentTvApi(object):
    CATEGORIES = {
        1: u'Детские',
        2: u'Музыка',
        3: u'Фильмы',
        4: u'Спорт',
        5: u'Общие',
        6: u'Познавательные',
        7: u'Новостные',
        8: u'Развлекательные',
        9: u'Для взрослых',
        10: u'Мужские',
        11: u'Региональные',
        12: u'Религиозные'
    }

    API_URL = 'http://api.torrent-tv.ru/v3/' # http://1ttvxbmc.top/v3/ # http://1ttvapi.top/v3/

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.allTranslations = self.session = self.guid = None
        self.log = logging.getLogger("TTV API")
        self.conf = RawConfigParser()
        self.headers = {'User-Agent': 'Magic Browser'} # headers for connection to the TTV API

    def auth(self):
        """
        User authentication
        Returns user session that can be used for API requests

        :param email: user email string
        :param password: user password string
        :param raw: if True returns unprocessed data
        :return: unique session string
        """
        try:
            self.conf.read('.aceconfig')
            self.session = self.conf.get('torrenttv_api', 'session')
            self.guid = self.conf.get('torrenttv_api', 'guid')
            if self.conf.get('torrenttv_api', 'email') != self.email: raise
        except:
            from uuid import getnode
            self.session = None
            self.guid = ''.join('%02x' % ((getnode() >> 8*i) & 0xff) for i in reversed(list(range(6)))) # get device mac address

        if self.session is None or self.session == '':
            self.log.debug('Creating new session')
            url = TorrentTvApi.API_URL + 'auth.php'
            params = {'typeresult': 'json', 'username':self.email, 'password': self.password, 'application': 'tsproxy', 'guid': self.guid}
            result = self._jsoncheck(requests.get(url, params=params, headers=self.headers, timeout=5).json())
            self.session = result['session']
            self.log.debug("New session created: %s" % self.session)
            # Store session detales to config file
            if not self.conf.has_section('torrenttv_api'): self.conf.add_section('torrenttv_api')
            self.conf.set('torrenttv_api', 'email', self.email)
            self.conf.set('torrenttv_api', 'session', self.session)
            self.conf.set('torrenttv_api', 'guid', self.guid)
            with open('.aceconfig', 'w+') as config: self.conf.write(config)
        else: self.log.debug('Reusing saved session: %s' % self.session)

        return self.session

    def translations(self, translation_type, raw=False):
        """
        Gets list of translations
        Translations are basically TV channels

        :param session: valid user session required
        :param translation_type: playlist type, valid values: all|channel|moderation|translation|favourite
        :param raw: if True returns unprocessed data
        :return: translations list
        """
        request = 'translation_list.php'
        params = {'type': translation_type}
        if raw:
            try:
                res = self._xmlresult(request, params)
                self._checkxml(res)
            except TorrentTvApiException:
                res = self._xmlresult(request, params)
                self._checkxml(res)
            finally: return res
        else:
            res = self._checkedxmlresult(request, params)
            return res.getElementsByTagName('channel')

    def records(self, channel_id, date, raw=False):
        """
        Gets list of available record for given channel and date

        :param session: valid user session required
        :param channel_id: id of channel in channel list
        :param date: format %d-%m-%Y
        :param raw: if True returns unprocessed data
        :return: records list
        """
        request = 'arc_records.php'
        params = {'epg_id': channel_id, 'date': date.strftime('X%d-X%m-%Y').replace('X0','X').replace('X','')}
        if raw:
            try:
                res = self._xmlresult(request, params)
                self._checkxml(res)
            except TorrentTvApiException:
                res = self._xmlresult(request, params)
                self._checkxml(res)
            finally: return res
        else:
            res = self._checkedxmlresult(request, params)
            return res.getElementsByTagName('channel')

    def archive_channels(self, raw=False):
        """
        Gets the channels list for archive

        :param session: valid user session required
        :param raw: if True returns unprocessed data
        :return: archive channels list
        """
        request = 'arc_list.php'
        params = {}
        if raw:
            try:
                res = self._xmlresult(request, params)
                self._checkxml(res)
            except TorrentTvApiException:
                res = self._xmlresult(request, params)
                self._checkxml(res)
            finally: return res
        else:
            res = self._checkedxmlresult(request, params)
            return res.getElementsByTagName('channel')

    def stream_source(self, channel_id):
        """
        Gets the source for Ace Stream by channel id

        :param session: valid user session required
        :param channel_id: id of channel in translations list (see translations() method)
        :return: type of stream and source and translation list
        """
        request = 'translation_stream.php'
        params = {'channel_id': channel_id}

        res = self._checkedjsonresult(request, params)
        stream_type = res['type']
        source = res['source']
        allTranslations = self.allTranslations
        if not allTranslations:
            self.allTranslations = allTranslations = self.translations('all')
        return stream_type.encode('utf-8'), source.encode('utf-8'), allTranslations

    def archive_stream_source(self, record_id):
        """
        Gets stream source for archive record

        :param session: valid user session required
        :param record_id: id of record in records list (see records() method)
        :return: type of stream and source
        """
        request = 'arc_stream.php'
        params = {'record_id': record_id}

        res = self._checkedjsonresult(request, params)
        stream_type = res['type']
        source = res['source']
        return stream_type.encode('utf-8'), source.encode('utf-8')

    def _jsoncheck(self, jsonresult):
        """
        Validates received API answer
        Raises an exception if error detected

        :param jsonresult: API answer to check
        :return: minidom-parsed xmlresult
        :raise: TorrentTvApiException
        """
        success = jsonresult['success']
        if success == '0' or not success:
            error = jsonresult['error']
            raise TorrentTvApiException('API returned error: %s' % error)
        return jsonresult

    def _checkxml(self, xmlresult):
        """
        Validates received API answer
        Raises an exception if error detected

        :param xmlresult: API answer to check
        :return: minidom-parsed xmlresult
        :raise: TorrentTvApiException
        """
        res = dom.parseString(xmlresult).documentElement
        success = res.getElementsByTagName('success')[0].firstChild.data
        if success == '0' or not success:
            error = res.getElementsByTagName('error')[0].firstChild.data
            raise TorrentTvApiException('API returned error: %s' % error)
        return res

    def _checkedjsonresult(self, request, params):
        try: return self._jsoncheck(self._jsonresult(request, params))
        except TorrentTvApiException:
            self._resetSession()
            return self._jsoncheck(self._jsonresult(request, params))

    def _checkedxmlresult(self, request, params):
        try: return self._checkxml(self._xmlresult(request, params))
        except TorrentTvApiException:
            self._resetSession()
            return self._checkxml(self._xmlresult(request, params))

    def _jsonresult(self, request, params):
        """
        Sends request to API and returns the result in form of string

        :param request: API command string
        :return: result of request to API
        :raise: TorrentTvApiException
        """
        try:
            url = TorrentTvApi.API_URL + request
            params.update({'session': self.auth(), 'typeresult': 'json'})
            return requests.get(url, params=params, headers=self.headers, timeout=5).json()
        except requests.exceptions.ConnectionError as e:
            raise TorrentTvApiException('Error happened while trying to access API: %s' % repr(e))

    def _xmlresult(self, request, params):
        """
        Sends request to API and returns the result in form of string

        :param request: API command string
        :return: result of request to API
        :raise: TorrentTvApiException
        """
        try:
            url = TorrentTvApi.API_URL + request
            params.update({'session': self.auth(), 'typeresult': 'xml'})
            return requests.get(url, params=params, headers=self.headers, timeout=5).content
        except requests.exceptions.ConnectionError as e:
            raise TorrentTvApiException('Error happened while trying to access API: %s' % repr(e))

    def _resetSession(self):
        self.allTranslations = self.session = None
        try: self.conf.read('.aceconfig')
        except: pass
        if not self.conf.has_section('torrenttv_api'): self.conf.add_section('torrenttv_api')
        self.conf.set('torrenttv_api', 'session', '')
        with open('.aceconfig', 'w+') as config: self.conf.write(config)
        self.auth()
