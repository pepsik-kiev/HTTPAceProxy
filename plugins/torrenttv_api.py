# -*- coding: utf-8 -*- 
"""
Torrent-TV API communication class
Forms requests to API, checks result for errors and returns in desired form (lists or raw data)
"""
__author__ = 'miltador'

import requests
import random
import xml.dom.minidom as dom
import logging
import time
import threading

class TorrentTvApiException(Exception):
    """
    Exception from Torrent-TV API
    """
    pass

class TorrentTvApi(object):
    CATEGORIES = {
        1: 'Детские',
        2: 'Музыка',
        3: 'Фильмы',
        4: 'Спорт',
        5: 'Общие',
        6: 'Познавательные',
        7: 'Новостные',
        8: 'Развлекательные',
        9: 'Для взрослых',
        10: 'Мужские',
        11: 'Региональные',
        12: 'Религиозные'
    }

    API_URL = 'http://api.torrent-tv.ru/v3/'

    def __init__(self, email, password, maxIdle, zoneid='1'):
        self.email = email
        self.password = password
        self.maxIdle = maxIdle
        self.zoneid = zoneid
        self.session = None
        self.allTranslations = None
        self.lastActive = 0.0
        self.lock = threading.RLock()
        self.log = logging.getLogger("TTV API")

    def auth(self):
        """
        User authentication
        Returns user session that can be used for API requests

        :param email: user email string
        :param password: user password string
        :param raw: if True returns unprocessed data
        :return: unique session string
        """
        with self.lock:
            if self.session and (time.time() - self.lastActive) < self.maxIdle:
                self.lastActive = time.time()
                self.log.debug("Reusing previous session: " + self.session)
                return self.session

            self.log.debug("Creating new session")
            self.session = None
            params = {'typeresult': 'json','username': self.email,'password': self.password,'application': 'tsproxy','guid': str(random.randint(100000000,199999999))}
            result = self._jsoncheck(requests.get(TorrentTvApi.API_URL+'auth.php', params=params,timeout=10).json())
            self.session = result['session']
            self.lastActive = time.time()
            self.log.debug("New session created: " + self.session)

            params={'session': self.session,'typeresult': 'json'}
            result = self._jsoncheck(requests.get(TorrentTvApi.API_URL+'userinfo.php', params=params, timeout=10).json())
            self.log.debug("Session details : VipStatus - " + ("Yes" if str(result['vip_status'])=='1' else "No") + "; Balance - " + str(result['balance']))

            params = {'session': self.session,'zone': self.zoneid}
            result = self._jsoncheck(requests.get(TorrentTvApi.API_URL+'set_zone.php', params=params, timeout=10).json())
            self.log.debug("HTTP streaming ZoneID set to : " + self.zoneid)

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

        query = '&type=' + translation_type

        if raw:
            try:
                res = self._xmlresult('translation_list.php', query)
                self._checkxml(res)
                return res
            except TorrentTvApiException:
                res = self._xmlresult('translation_list.php', query)
                self._checkxml(res)
                return res
        else:
            res = self._checkedxmlresult('translation_list.php', query)
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
        date = date.replace('-0', '-')

        if raw:
            try:
                res = self._xmlresult('arc_records.php', '&epg_id=' + channel_id + '&date=' + date)
                self._checkxml(res)
                return res
            except TorrentTvApiException:
                res = self._xmlresult('arc_records.php', '&epg_id=' + channel_id + '&date=' + date)
                self._checkxml(res)
                return res
        else:
            res = self._checkedxmlresult('arc_records.php', '&epg_id=' + channel_id + '&date=' + date)
            return res.getElementsByTagName('channel')

    def archive_channels(self, raw=False):
        """
        Gets the channels list for archive

        :param session: valid user session required
        :param raw: if True returns unprocessed data
        :return: archive channels list
        """

        if raw:
            try:
                res = self._xmlresult('arc_list.php', '')
                self._checkxml(res)
                return res
            except TorrentTvApiException:
                res = self._xmlresult('arc_list.php', '')
                self._checkxml(res)
                return res
        else:
            res = self._checkedxmlresult('arc_list.php', '')
            return res.getElementsByTagName('channel')

    def stream_source(self, channel_id):
        """
        Gets the source for Ace Stream by channel id

        :param session: valid user session required
        :param channel_id: id of channel in translations list (see translations() method)
        :return: type of stream and source and translation list
        """

        res = self._checkedjsonresult('translation_stream.php', '&channel_id=' + channel_id)
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

        res = self._checkedjsonresult('arc_stream.php', '&record_id=' + record_id)
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
            raise TorrentTvApiException('API returned error: ' + error)
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
            raise TorrentTvApiException('API returned error: ' + error)
        return res

    def _checkedjsonresult(self, request, params):
        try:
            return self._jsoncheck(self._jsonresult(request, params))
        except TorrentTvApiException:
            self._resetSession()
            return self._jsoncheck(self._jsonresult(request, params))

    def _checkedxmlresult(self, request, params):
        try:
            return self._checkxml(self._xmlresult(request, params))
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
            url = TorrentTvApi.API_URL + request + '?session=' + self.auth() + '&typeresult=json' + params
            self.log.debug(url)
            return requests.get(url, timeout=10).json()
        except requests.exceptions.ConnectionError as e:
            raise TorrentTvApiException('Error happened while trying to access API: ' + repr(e))

    def _xmlresult(self, request, params):
        """
        Sends request to API and returns the result in form of string

        :param request: API command string
        :return: result of request to API
        :raise: TorrentTvApiException
        """
        try:
            url = TorrentTvApi.API_URL + request + '?session=' + self.auth() + '&typeresult=xml' + params
            self.log.debug(url)
            return requests.get(url,timeout=10).content
        except requests.exceptions.ConnectionError as e:
            raise TorrentTvApiException('Error happened while trying to access API: ' + repr(e))

    def _resetSession(self):
        with self.lock:
            self.session = None
            self.allTranslations = None
            self.auth()
