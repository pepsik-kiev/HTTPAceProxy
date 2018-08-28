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

    STATE = {0: 'IDLE',
             1: 'PREBUFFERING',
             2: 'DOWNLOADING',
             3: 'BUFFERING',
             4: 'COMPLETED',
             5: 'CHECKING',
             6: 'ERROR'
             }

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
            return 'READY key={}-{}'.format(product_key.split('-')[0], hashlib.sha1((request_key + product_key).encode('utf-8')).hexdigest())
        # End READY

        @staticmethod
        def LOADASYNC(command, request_id, params_dict):
            params_dict['request_id'] = request_id
            if command == 'URL':
                return 'LOADASYNC {request_id} TORRENT {url} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif command == 'INFOHASH':
                return 'LOADASYNC {request_id} INFOHASH {infohash} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif command == 'DATA':
                return 'LOADASYNC {request_id} RAW {data} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif command == 'CONTENT_ID':
                return 'LOADASYNC {request_id} PID {content_id}'.format(**params_dict)
        # End LOADASYNC

        @staticmethod
        def START(command, params_dict, stream_type):
            params_dict['stream_type'] = stream_type
            if command == 'URL':
                return 'START TORRENT {url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_id} {stream_type}'.format(**params_dict)

            elif command == 'INFOHASH':
                return 'START INFOHASH {infohash} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}'.format(**params_dict)

            elif command == 'CONTENT_ID':
                return 'START PID {content_id} {file_indexes} {stream_type}'.format(**params_dict)

            elif command == 'DATA':
                return 'START RAW {data} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}'.format(**params_dict)

            elif command == 'DIRECT_URL':
                return 'START URL {direct_url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_type}'.format(**params_dict)

            elif command == 'EFILE_URL':
                return 'START EFILE {efile_url} {stream_type}'.format(**params_dict)
        # End START

        STOP = 'STOP'

        @staticmethod
        def GETCID(params_dict):
            return 'GETCID %s' % ' '.join(['{}={}'.format(k,v) for k,v in params_dict.items()])
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
