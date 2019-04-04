# -*- coding: utf-8 -*-
'''
Minimal Ace Stream client library to use with HTTP Proxy
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import hashlib

class AceConst(object):
    APIVERSION = 3

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

    STATE = {'0': 'IDLE',
             '1': 'PREBUFFERING',
             '2': 'DOWNLOADING',
             '3': 'BUFFERING',
             '4': 'COMPLETED',
             '5': 'CHECKING',
             '6': 'ERROR'}

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

class AceMessage(object):

    class request(object):
        # Events form client to engine
        @staticmethod
        def EVENT(command, params_dict={}):
            return 'EVENT %s %s' % (command, ' '.join(['{}={}'.format(k,v) for k,v in params_dict.items()]))
        # End EVENT

        # Commands from client to acestream
        HELLO = 'HELLOBG version=%s' % AceConst.APIVERSION

        @staticmethod
        def READY(request_key='', product_key=''):
            return 'READY key={}-{}'.format(product_key.split('-')[0], hashlib.sha1((request_key+product_key).encode('utf-8')).hexdigest())
        # End READY

        @staticmethod
        def LOADASYNC(params_dict):
            if 'url' in params_dict:
                return 'LOADASYNC {request_id} TORRENT {url} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif 'infohash' in params_dict:
                return 'LOADASYNC {request_id} INFOHASH {infohash} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif 'data' in params_dict:
                return 'LOADASYNC {request_id} RAW {data} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif 'content_id' in params_dict:
                return 'LOADASYNC {request_id} PID {content_id}'.format(**params_dict)
        # End LOADASYNC

        @staticmethod
        def START(params_dict):
            if 'url' in params_dict:
                return 'START TORRENT {url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_id} {stream_type}'.format(**params_dict)

            elif 'infohash' in params_dict:
                return 'START INFOHASH {infohash} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}'.format(**params_dict)

            elif 'content_id' in params_dict:
                return 'START PID {content_id} {file_indexes} {stream_type}'.format(**params_dict)

            elif 'data' in params_dict:
                return 'START RAW {data} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}'.format(**params_dict)

            elif 'direct_url' in params_dict:
                return 'START URL {direct_url} {stream_type}'.format(**params_dict)

            elif 'efile_url' in params_dict:
                return 'START EFILE {efile_url} {stream_type}'.format(**params_dict)
        # End START

        STOP = 'STOP'

        @staticmethod
        def GETCID(params_dict):
            return 'GETCID checksum={checksum} infohash={infohash} developer={developer_id} affiliate={affiliate_id} zone={zone_id}'.format(**params_dict)
        # End GETCID

        @staticmethod
        def GETADURL(width, height, infohash, action): pass
        # End GETADURL

        @staticmethod
        def USERDATA(gender, age):
            return 'USERDATA [{"gender": %s}, {"age": %s}]' % (gender, age)
        # End USERDATA

        @staticmethod
        def SAVE(infohash, index, path): pass
        # End SAVE

        @staticmethod
        def LIVESEEK(timestamp):
            return 'LIVESEEK %s' % timestamp
        # End LIVESEEK

        SHUTDOWN = 'SHUTDOWN'

        @staticmethod
        def SETOPTIONS(params_dict):
            return 'SETOPTIONS %s' % ' '.join(['{}={}'.format(k,v) for k,v in params_dict.items()])
        # End SETOPTIONS
