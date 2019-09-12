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
                 'url': 'LOADASYNC {request_id} TORRENT {url} {developer_id} {affiliate_id} {zone_id}',
                 'infohash': 'LOADASYNC {request_id} INFOHASH {infohash} {developer_id} {affiliate_id} {zone_id}',
                 'data': 'LOADASYNC {request_id} RAW {data} {developer_id} {affiliate_id} {zone_id}',
                 'content_id': 'LOADASYNC {request_id} PID {content_id}',
                 }

    START = {
             'url': 'START TORRENT {url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_id} {stream_type}',
             'infohash': 'START INFOHASH {infohash} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}',
             'content_id': 'START PID {content_id} {file_indexes} {stream_type}',
             'data': 'START RAW {data} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}',
             'direct_url': 'START URL {direct_url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}',
             'efile_url': 'START EFILE {efile_url} {stream_type}',
             }

class AceMessage(object):

    class request(object):
        # Events form client to engine
        @staticmethod
        def EVENT(command, params_dict={}):
            return 'EVENT {} {}'.format(command, ' '.join(['{}={}'.format(k,v) for k,v in params_dict.items()]))
        # End EVENT

        # Commands from client to acestream
        @staticmethod
        def HELLOBG(api_version=AceConst.APIVERSION):
            return 'HELLOBG version={}'.format(api_version)

        @staticmethod
        def READY(request_key='', product_key=AceConst.ACE_KEY):
            return 'READY key={}-{}'.format(product_key.split('-')[0], hashlib.sha1(ensure_binary(request_key+product_key)).hexdigest())
        # End READY

        @staticmethod
        def LOADASYNC(params_dict):
            return AceConst.LOADASYNC.get( (viewkeys(AceConst.LOADASYNC) & viewkeys(params_dict)).pop() ).format(**params_dict)

        @staticmethod
        def START(params_dict):
            return AceConst.START.get( (viewkeys(AceConst.START) & viewkeys(params_dict)).pop() ).format(**params_dict)
        # End START

        STOP = 'STOP'

        @staticmethod
        def GETCID(params_dict):
            return 'GETCID checksum={checksum} infohash={infohash} developer={developer_id} affiliate={affiliate_id} zone={zone_id}'.format(**params_dict)
        # End GETCID

        @staticmethod
        def GETADURL(params_dict):
            return 'GETADURL width={width} height={height} infohash={infohash} action={action}'.format(**params_dict)
        # End GETADURL

        @staticmethod
        def USERDATA(**params_dict):
            return 'USERDATA [{{"gender": {gender}}}, {{"age": {age}}}]'.format(**params_dict)
        # End USERDATA

        @staticmethod
        def SAVE(**params_dict):
            return 'SAVE infohash={infohash} index={index} path={path}'.format(**params_dict)
        # End SAVE

        @staticmethod
        def LIVESEEK(timestamp):
            return 'LIVESEEK {}'.format(timestamp)
        # End LIVESEEK

        SHUTDOWN = 'SHUTDOWN'

        @staticmethod
        def SETOPTIONS(params_dict):
            return 'SETOPTIONS {}'.format(' '.join(['{}={}'.format(k,v) for k,v in params_dict.items()]))
        # End SETOPTIONS
