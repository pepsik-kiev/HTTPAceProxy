'''
AceProxy default configuration script
DO NOT EDIT THIS FILE!
Copy this file to aceconfig.py and change only needed options.
'''

import logging
import platform
from aceclient.acemessages import AceConst

# Loggin level for requests module
logging.getLogger("urllib3").setLevel(logging.WARNING)

class AceDefConfig(object):
    acespawn = False
    acecmd = "acestreamengine --client-console"
    acekey = 'n51LvQoTlJzNGaFxseRK-uvnvX-sD4Vm5Axwmc4UcoD-jruxmKsuJaH0eVgE'
    acehost=aceAPIport=aceHTTPport=None
    acehostslist = (['127.0.0.1', '62062', '6878'])
    aceage = AceConst.AGE_18_24
    acesex = AceConst.SEX_MALE
    acestartuptimeout = 10
    aceconntimeout = 5
    aceresulttimeout = 5
    httphost='0.0.0.0'
    httpport = 8000
    readchunksize = 8192
    readcachesize = 1024
    aceproxyuser = ''
    firewall = False
    firewallblacklistmode = False
    firewallnetranges = (
        '127.0.0.1',
        '192.168.0.0/16',
        )
    maxconns = 10
    streamtype = 'http'
    transcode = False
    transcodecmd = dict()
    transcodecmd['default'] = 'ffmpeg -i - -c:a copy -c:v copy -f mpegts -'.split()
    transcode_audio = 0
    transcode_mp3 = 0
    transcode_ac3 = 0
    preferred_audio_language = 'rus'
    videoseekback = 0
    videotimeout = 30
    useacelive = True
    fakeuas = ('Mozilla/5.0 IMC plugin Macintosh', )
    fakeheaderuas = ('HLS Client/2.0 (compatible; LG NetCast.TV-2012)',
                     'Mozilla/5.0 (DirectFB; Linux armv7l) AppleWebKit/534.26+ (KHTML, like Gecko) Version/5.0 Safari/534.26+ LG Browser/5.00.00(+mouse+3D+SCREEN+TUNER; LGE; 42LM670T-ZA; 04.41.03; 0x00000001;); LG NetCast.TV-2012 0'
                     )
    loglevel = logging.DEBUG
    logfmt = '%(filename)-20s [LINE:%(lineno)-4s]# %(levelname)-8s [%(asctime)s]  %(message)s'
    logdatefmt='%d.%m %H:%M:%S'
    logfile = None
    @staticmethod
    def isFakeRequest(path, params, headers):
        useragent = headers.get('User-Agent')

        if not useragent:
            return False
        elif useragent in AceConfig.fakeuas:
            return True
        elif useragent == 'Lavf/55.33.100' and not headers.has_key('Range'):
            return True
        elif useragent == 'GStreamer souphttpsrc (compatible; LG NetCast.TV-2013) libsoup/2.34.2' and headers.get('icy-metadata') != '1':
            return True

    osplatform = platform.system()