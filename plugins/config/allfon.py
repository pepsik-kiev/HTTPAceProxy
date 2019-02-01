'''
Allfon.tv Playlist Downloader Plugin configuration file
'''
# Proxy settings.
# For example you can install tor browser and add in torrc SOCKSPort 9050
# proxies = {'http' : 'socks5h://127.0.0.1:9050','https' : 'socks5h://127.0.0.1:9050'}
# If your http-proxy need authentification - proxies = { 'https' : 'https://user:password@ip:port' }

#proxies = {'http' : 'socks5h://192.168.2.1:9100', 'https' : 'socks5h://192.168.2.1:9100'}
proxies = None

# Insert your allfon.tv playlist URL here
url = 'http://allfon-tv.com/autogenplaylist/allfontv.m3u'

# EPG urls & EPG timeshift
tvgurl = 'http://epg.do.am/tv.gz'

# Shift the TV Guide time to the specified number of hours
tvgshift = 0

# Download playlist every N minutes to keep it fresh
updateevery = 180

# Channel playlist template
# The following values are allowed:
# name - channel name
# url - channel URL
# tvg - channel tvg-name (optional)
# tvgid - channel tvg-id (optional)
# group - channel playlist group-title (optional)
# logo - channel picon file tvg-logo (optional)
m3uheadertemplate = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' % (tvgurl, tvgshift)
m3uchanneltemplate = '#EXTINF:-1 group-title="%(group)s" tvg-name="%(tvg)s" tvg-logo="%(logo)s",%(name)s\n%(url)s\n'
