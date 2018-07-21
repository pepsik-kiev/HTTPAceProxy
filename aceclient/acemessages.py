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
        # Requests (from client to acestream)
        # API Version
        HELLO = 'HELLOBG version=%s' % AceConst.APIVERSION  # Hello
        READY_nokey = 'READY'  # Sent when ready
        SHUTDOWN = 'SHUTDOWN'
        SETOPTIONS = 'SETOPTIONS use_stop_notifications=1'
        STOP = 'STOP'
        # Events form client to engine
        PAUSEEVENT = 'EVENT pause'
        PLAYEVENT  = 'EVENT play'
        STOPEVENT  = 'EVENT stop'
        SEEKEVENT  = 'EVENT seek'

        @staticmethod
        def READY_key(request_key, product_key):
            return 'READY key={}-{}'.format(product_key.split('-')[0], hashlib.sha1(request_key + product_key).hexdigest())
        # End READY_KEY

        @staticmethod
        def LOADASYNC(command, request_id, params_dict):
            if command == 'URL':
                return 'LOADASYNC %s TORRENT ' % request_id + '{url} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif command == 'INFOHASH':
                return 'LOADASYNC %s INFOHASH ' % request_id + '{infohash} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif command == 'DATA':
                return 'LOADASYNC %s RAW ' % request_id + '{data} {developer_id} {affiliate_id} {zone_id}'.format(**params_dict)

            elif command == 'CONTENT_ID':
                return 'LOADASYNC %s PID ' % request_id + '{content_id}'.format(**params_dict)
        # End LOADASYNC

        @staticmethod
        def START(command, params_dict, stream_type):
            if command == 'URL':
                return 'START TORRENT {url} {file_indexes} {developer_id} {affiliate_id} {zone_id} {stream_id} '.format(**params_dict)+stream_type

            elif command == 'INFOHASH':
                return 'START INFOHASH {infohash} {file_indexes} {developer_id} {affiliate_id} {zone_id} '.format(**params_dict)+stream_type

            elif command == 'CONTENT_ID':
                return 'START PID {content_id} {file_indexes} '.format(**params_dict)+stream_type

            elif command == 'DATA':
                return 'START RAW {data} {file_indexes} {developer_id} {affiliate_id} {zone_id} '.format(**params_dict)+stream_type

            elif command == 'DIRECT_URL':
                return 'START URL {direct_url} {file_indexes} {developer_id} {affiliate_id} {zone_id} '.format(**params_dict)+stream_type

            elif command == 'EFILE_URL':
                return 'START EFILE {efile_url} '.format(**params_dict)+stream_type
        # End START

        @staticmethod
        def GETCID(checksum, infohash, developer, affiliate, zone):
            return 'GETCID checksum=%s infohash=%s developer=%s affilate=%s zone=%s' % (checksum, infohash, developer, affiliate, zone)

        @staticmethod
        def USERDATA(gender, age):
            return 'USERDATA [{"gender": %s}, {"age": %s}]' % (gender, age)

        @staticmethod
        def LIVESEEK(timestamp):
            return 'LIVESEEK %s' % timestamp

    class response(object):
        # Responses (from acestream to client)
        HELLO = 'HELLOTS'
        NOTREADY = 'NOTREADY'
        START = 'START'
        STOP = 'STOP'
        PAUSE = 'PAUSE'
        RESUME = 'RESUME'
        LOADRESP = 'LOADRESP'
        SHUTDOWN = 'SHUTDOWN'
        # Events (from AceEngine to client)
        AUTH = 'AUTH'
        GETUSERDATA = 'EVENT getuserdata'
        LIVEPOS = 'EVENT livepos'
        DOWNLOADSTOP = 'EVENT download_stopped'
        SHOWURL = 'EVENT showurl'
        CANSAVE = 'EVENT cansave'
        STATE = 'STATE'
        STATUS = 'STATUS'
        INFO = 'INFO'
