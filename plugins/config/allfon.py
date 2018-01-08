'''
Allfon.tv Playlist Downloader Plugin configuration file
'''
# Proxy settings.
# For example you can install tor browser and add in torrc SOCKSPort 9050
# proxies = {'http' : 'socks5h://127.0.0.1:9050','https' : 'socks5h://127.0.0.1:9050'}
# If your http-proxy need authentification - proxies = { 'https' : 'https://user:password@ip:port' }
useproxy = False
proxies = {'http' : 'socks5://127.0.0.1:9050',
           'https' : 'socks5://127.0.0.1:9050'}

# Insert your allfon.tv playlist URL here
url = 'http://allfon-tv.pro/autogenplaylist/allfontv.m3u'

# EPG urls & EPG timeshift
tvgurl = 'http://www.teleguide.info/download/new3/jtv.zip'
tvgshift = 0

# Channel template
m3uchanneltemplate = '#EXTINF:-1 tvg-name="%(tvg)s",%(name)s\n%(url)s\n'
