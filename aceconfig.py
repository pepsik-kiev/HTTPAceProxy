''' AceProxy configuration scrip Edit this file. '''

import acedefconfig, logging
from aceclient.acemessages import AceConst

class AceConfig(acedefconfig.AceDefConfig):
    # ----------------------------------------------------
    # Ace Stream Engine configuration
    # ----------------------------------------------------
    #
    # Spawn Ace Stream Engine automatically
    acespawn = True
    # Ace Stream cmd line (use `--log-file filepath` to write log)
    # You need to set it only on Linux based systems. Autodetect for Windows!
    # acecmd = 'acestreamengine --client-console --live-buffer 25 --vod-buffer 10 --vod-drop-max-age 120'
    acecmd = "/storage/ttv/acestream.engine/acestream.start"
    # Ace Stream API key
    # You probably shouldn't touch this
    acekey = 'n51LvQoTlJzNGaFxseRK-uvnvX-sD4Vm5Axwmc4UcoD-jruxmKsuJaH0eVgE'
    # By default Ace Stream Engine listens only Localhost IP, so if you want to use a running
    # somewhere (remotely) AceEngine - start it  with --bind-all parameter, set acespawn=False
    # and enter your settings below
    ace = { 'aceHostIP': '127.0.0.1', 'aceAPIport': '62062', 'aceHTTPport': '6878' }
    # Ace Stream age parameter (LT_13, 13_17, 18_24, 25_34, 35_44, 45_54,
    # 55_64, GT_65)
    aceage = AceConst.AGE_35_44
    # Ace Stream sex parameter (MALE or FEMALE)
    acesex = AceConst.SEX_MALE
    # Ace Stream Engine startup timeout
    # On Windows Ace Engine refreshes acestream.port file only after loading GUI
    # Loading takes about ~10-15 seconds and we need to wait before taking port out of it
    # Set this to 0 if you don't use proxy at startup or don't need to wait
    acestartuptimeout = 15
    # Ace Stream Engine connection timeout
    aceconntimeout = 5
    # Ace Stream Engine authentication result & API port answers timeout
    aceresulttimeout = 10
    # ----------------------------------------------------
    # Ace Stream Engine stream type hls or http
    # ----------------------------------------------------
    # Since version 3.1.x is implemented HTTP API
    # Useed AceStream API method False - Engine API, True - HTTP API
    new_api = False
    # For HLS transcode options is avalible:
    # Transcode All audio to AAC (transcode_audio=1)
    # Transcode MP3 (use only when transcode_audio=1)
    # Transcode only AC3 to AAC (use only when transcode_audio=0)
    acestreamtype = {'output_format': 'http'}
    #acestreamtype = {'output_format': 'hls', 'transcode_audio': 0, 'transcode_mp3': 0, 'transcode_ac3': 0, 'preferred_audio_language': 'rus'}
    # ----------------------------------------------------
    # Seek back feature.
    # Seeks stream back for specified amount of seconds.
    # Greatly helps fighing AceSteam lags, but introduce video stream delay.
    # Set it to 30 or so. Works only with the newest versions of AceEngine!
    # !!!!! Don't use with streamtype = 'hls' !!!!!
    videoseekback = 0
    # Waiting time response from AceEngine server for playable url or data In seconds.
    videotimeout = 60
    # ----------------------------------------------------
    # HTTP AceProxy configuration
    # ----------------------------------------------------
    #
    # HTTP Server host.
    # 'auto' - autodetect
    # '0.0.0.0' - listen on all addresses
    # Or change to whatever IP you want to listen on this IP only
    httphost = 'auto'
    # HTTP Server port (8081 is recommended when using the plugin p2pproxy with TTV widget on SmartTV)
    httpport = 8000
    # If started as root, drop privileges to this user.
    # Leave empty to disable.
    aceproxyuser = ''
    # Enable firewall
    firewall = False
    # Firewall mode. True for blackilst, False for whitelis
    firewallblacklistmode = False
    # Network ranges. Please don't forget about comma in the end
    # of every range, especially if there is only one.
    firewallnetranges = (
        '127.0.0.1',
        '192.168.0.0/16',
        )
    # Maximum concurrent connections (video clients)
    maxconns = 10
    # Use 'Transfer-encoding: chunked' in HTTP AceProxy responses
    use_chunked = True
    #
    # ----------------------------------------------------
    #       Transcoding configuration for HTTP AceProxy
    # (Lnux based OS Only!!! This solution didn't work on Windows OS)
    # ----------------------------------------------------
    # Transcoding Dictionary with a set of transcoding commands. Transcoding command is an executable commandline expression
    # that reads an input stream from STDIN and writes a transcoded stream to STDOUT. The commands are selected
    # according to the value of the 'fmt' request parameter. For example, the following url:
    # http://loclahost:8000/channels/?type=m3u&fmt=mp2
    # contains the fmt=mp2. It means that the 'mp2' command will be used for transcoding. You may add any number
    # of commands to this dictionary.
    # !!!!!! Ffmpeg instaled is required !!!!!!
    transcodecmd = {}
    #transcodecmd['100k'] = 'ffmpeg -i - -c:a copy -b 100k -f mpegts -'.split()
    #transcodecmd['mp2'] = 'ffmpeg -i - -c:a mp2 -c:v mpeg2video -f mpegts -qscale:v 2 -'.split()
    #transcodecmd['mkv'] = 'ffmpeg -i - -map 0 -c:v copy -c:a copy -f matroska -'.split()
    #transcodecmd['default'] = 'ffmpeg -i - -map 0 -c:a copy -c:v copy -f mpegts -'.split()
    #
    # ----------------------------------------------------
    # Other settings
    # ----------------------------------------------------
    #
    # Logging configuration
    #
    # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    loglevel = logging.INFO
    # Log message format
    logfmt = '%(filename)-20s [LINE:%(lineno)-4s]# %(levelname)-8s [%(asctime)s] %(message)s'
    #logfmt = '%(filename)s - %(name)s - %(threadName)s - [LINE:%(lineno)s]# - %(levelname)s - [%(asctime)s] - %(message)s' # for debug
    #logfmt = '%(asctime)s{%(name)s}%(filename)s[line:%(lineno)d]<%(funcName)s> pid:%(process)d %(threadName)s %(levelname)s : %(message)s'
    # Log date format
    logdatefmt = '%d.%m %H:%M:%S'
    # Full path to a log file
    # For Windows OS something like that logfile = "c:\\Python27\\log_AceHttp.txt"
    logfile = None
    #
    # This method is used to detect fake requests. Some players send such
    # requests in order to detect the MIME type and/or check the stream availability.
    # Some video players (mostly STBs and Smart TVs) can generate dummy requests
    # to detect MIME-type or something before playing which Ace Stream handles badly.
    # We send them 200 OK and do nothing.
    # We add their User-Agents here
    #
    fakeuas = ('Mozilla/5.0 IMC plugin Macintosh', )
    #
    @staticmethod
    def isFakeRequest(path, params, headers):
        useragent = headers.get('User-Agent')

        if not useragent:
            return False
        elif useragent in AceConfig.fakeuas:
            return True
       # Samsung ES series
        elif useragent == 'Lavf/55.33.100' and headers.get('Range') != 'bytes=0-':
            return True
        # Samsung H series
        elif useragent == 'Lavf52.104.0' and headers.get('Range') != 'bytes=0-':
            return True
        # LG Netacast 2013 year series
        elif useragent == 'GStreamer souphttpsrc (compatible; LG NetCast.TV-2013) libsoup/2.34.2' and headers.get('icy-metadata') != '1':
            return True
        # Samsung K series
        elif useragent == 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/2.4.0 TV Safari/538.1' and 'Range' in headers and not 'accept-encoding' in headers:
            return True
        elif useragent == 'samsung-agent/1.1' and 'Range' in headers and not 'accept-encoding' in headers:
            return True
        # Samsung N series
        elif useragent == 'Mozilla/5.0 (SMART-TV; LINUX; Tizen 4.0) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 TV Safari/537.36' and 'Range' in headers and not 'accept-encoding' in headers:
            return True
         # Dune 301
        elif useragent == 'DuneHD/1.0' and headers.get('Range') != 'bytes=0-':
            return True
         # MX Player 1.10.xx for Android
        elif 'MXPlayer/1.10.' in useragent and 'Accept-Encoding' in headers:
            return True
