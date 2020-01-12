'''
Configuration file for json-based playlists downloader

Playlist format example:
{"channels":[
{"name":"Channel name 1","url":"blablablablablablablablablablablablablab","cat":"Group 1"},
{"name":"Channel name 2","url":"blablablablablablablablablablablablablab","cat":"Group 2"},
{"name":"Channel name 3","url":"blablablablablablablablablablablablablab","cat":"Group 3"},
......
...
..
.
{"name":"Channel name N","url":"blablablablablablablablablablablablablab","cat":"Group N"}
]}

'''
# Proxy settings.
# For example you can install tor browser and add in torrc SOCKSPort 9050
# if you use tor on the same machine with AceProxy -  proxies = { 'https' : 'socks5h://127.0.0.1:9050' }
# If your http-proxy need authentification - proxies = {https' : 'https://user:password@ip:port'}

proxies = {}
#proxies = {'http' : 'socks5h://192.168.1.1:9100',
#           'https' : 'socks5h://192.168.1.1:9100'}

# Channels urls or path to file ('file:///path/to/file' or 'file:///C://path//to//file' for Windows OS)
url = 'http://frytv.pp.ua/frytv.json'

# EPG urls
tvgurl = 'https://iptvx.one/epg/epg.xml.gz'

# Shift the TV Guide time to the specified number of hours
tvgshift = 0

# Download playlist every N minutes to keep it fresh
# 0 = disabled
updateevery = 10

# Channel playlist template
# The following values are allowed:
# name - channel name
# url - channel URL
# tvg - channel tvg-name (optional)
# tvgid - channel tvg-id (optional)
# group - channel playlist group-title (optional)
# logo - channel picon file tvg-logo (optional)
m3uheadertemplate = u'#EXTM3U url-tvg={} tvg-shift={} deinterlace=1 m3uautoload=1 cache=1000\n'.format(tvgurl, tvgshift)
m3uchanneltemplate = u'#EXTINF:-1 group-title="{group}" tvg-name="{tvg}" tvg-logo="{logo}",{name}\n#EXTGRP:{group}\n{url}\n'
