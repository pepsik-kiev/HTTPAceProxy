# -*- coding: utf-8 -*-
'''
Minimal Ace Stream client library to use with HTTP Proxy
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import hashlib
from urllib3.packages.six import viewkeys, ensure_binary
class AceConst(object):

    APIVERSION = 4

    AGE_LT_13 = 1
    AGE_13_17 = 2
    AGE_18_24 = 3
    AGE_25_34 = 4
    AGE_35_44 = 5
    AGE_45_54 = 6
    AGE_55_64 = 7
    AGE_GT_65 = 8

    SEX_MALE = 1
    SEX_FEMALE = 2
    ACE_KEY = 'n51LvQoTlJzNGaFxseRK-uvnvX-sD4Vm5Axwmc4UcoD-jruxmKsuJaH0eVgE'

    STATE = {
             '0': 'IDLE',
             '1': 'PREBUFFERING',
             '2': 'DOWNLOADING',
             '3': 'BUFFERING',
             '4': 'COMPLETED',
             '5': 'CHECKING',
             '6': 'ERROR',
            }

    STATUS = ('status',
              'total_progress',
              'immediate_progress',
              'speed_down',
              'http_speed_down',
              'speed_up',
              'peers',
              'http_peers',
              'downloaded',
              'http_downloaded',
              'uploaded')

    START_PARAMS = ('file_indexes',
                    'developer_id',
                    'affiliate_id',
                    'zone_id',
                    'stream_id')

    LOADASYNC = {
                 'url': 'LOADASYNC {sessionID} TORRENT {url} {developer_id} {affiliate_id} {zone_id}',
                 'infohash': 'LOADASYNC {sessionID} INFOHASH {infohash} {developer_id} {affiliate_id} {zone_id}',
                 'data': 'LOADASYNC {sessionID} RAW {data} {developer_id} {affiliate_id} {zone_id}',
                 'content_id': 'LOADASYNC {sessionID} PID {content_id}',
                 }

    START = {
             'url': 'START TORRENT {url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_id} {stream_type}',
             'infohash': 'START INFOHASH {infohash} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}',
             'content_id': 'START PID {content_id} {file_indexes} {stream_type}',
             'data': 'START RAW {data} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}',
             'direct_url': 'START URL {direct_url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}',
             'efile_url': 'START EFILE {efile_url} {stream_type}',
             }

class AceRequest(object):

    # Events form client to engine
    @staticmethod
    def EVENT(command, paramsdict={}):
        return 'EVENT {} {}'.format(command, ' '.join(['{}={}'.format(k,v) for k,v in paramsdict.items()]))
    # End EVENT

    # Commands from client to acestream
    @staticmethod
    def HELLOBG(api_version=AceConst.APIVERSION):
        return 'HELLOBG version={}'.format(api_version)

    @staticmethod
    def READY(request_key='', product_key=AceConst.ACE_KEY):
        return 'READY key={}-{}'.format(product_key.split('-')[0], hashlib.sha1(ensure_binary(request_key+product_key)).hexdigest())

    @staticmethod
    def LOADASYNC(paramsdict):
        return AceConst.LOADASYNC.get((viewkeys(AceConst.LOADASYNC) & viewkeys(paramsdict)).pop()).format(**paramsdict)

    @staticmethod
    def START(paramsdict):
        return AceConst.START.get((viewkeys(AceConst.START) & viewkeys(paramsdict)).pop()).format(**paramsdict)

    STOP = 'STOP'

    @staticmethod
    def GETCID(paramsdict):
        return 'GETCID checksum={checksum} infohash={infohash} developer={developer_id} affiliate={affiliate_id} zone={zone_id}'.format(**paramsdict)

    @staticmethod
    def GETADURL(paramsdict):
        return 'GETADURL width={width} height={height} infohash={infohash} action={action}'.format(**paramsdict)

    @staticmethod
    def USERDATA(paramsdict):
        return 'USERDATA [{{"gender": {gender}}}, {{"age": {age}}}]'.format(**paramsdict)

    @staticmethod
    def SAVE(paramsdict):
        return 'SAVE infohash={infohash} index={index} path={path}'.format(**paramsdict)

    @staticmethod
    def LIVESEEK(timestamp):
        return 'LIVESEEK {}'.format(timestamp)

    SHUTDOWN = 'SHUTDOWN'

    @staticmethod
    def SETOPTIONS(paramsdict):
        return 'SETOPTIONS {}'.format(' '.join(['{}={}'.format(k,v) for k,v in paramsdict.items()]))
