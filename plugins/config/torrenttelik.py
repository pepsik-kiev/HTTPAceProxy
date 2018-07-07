'''
Torrent-telik.com. Configuration file for json-based playlists downloader
'''
# Proxy settings.
# For example you can install tor browser and add in torrc SOCKSPort 9050
# if you use tor on the same machine with AceProxy -  proxies = { 'https' : 'socks5h://127.0.0.1:9050' }
# If your http-proxy need authentification - proxies = {https' : 'https://user:password@ip:port'}
proxies = None

# Channels urls
url = ''

# EPG urls & EPG timeshift
tvgurl = 'http://www.teleguide.info/download/new3/jtv.zip'
# Shift the TV Guide time to the specified number of hours
tvgshift = 0

# Channel playlist template
# The following values are allowed:
# name - channel name
# url - channel URL
# tvg - channel tvg name (optional)
# tvgid - channel tvg id (optional)
# group - channel playlist group (optional)
# logo - channel logo file name (optional)
m3uheadertemplate = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' %(tvgurl, tvgshift)
m3uchanneltemplate = '#EXTINF:-1 tvg-name="%(tvg)s",%(name)s\n%(url)s\n'
