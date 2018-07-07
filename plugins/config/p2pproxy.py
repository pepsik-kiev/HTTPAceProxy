'''
P2pProxy plugin configuration file

What is this plugin for?
 It repeats the behavior of p2pproxy to support programs written for using p2pproxy

 Some of examples for what you can use this plugin:
    Comfort TV widget (++ version)
    Official TorrentTV widget for Smart TV
    Kodi (XBMC) p2pproxy pvr plugin
    etc...

!!! It requires some changes in aceconfig.py:
    set the httpport to 8081
'''
# Insert your email on torrent-tv.ru here
email = 're.place@me'
# Insert your torrent-tv account password
password ='ReplaceMe'

# Generate logo with full path (e.g. http://torrent-tv.ru/uploads/ornzQpk6WCW6xk0lyBhlwqH8u2QyU7.png)
# or put only the logo file name (e.g. ornzQpk6WCW6xk0lyBhlwqH8u2QyU7.png)
# This option is only for m3u playlists.
fullpathlogo = True

# TV Guide URL
tvgurl = 'http://1ttvapi.top/ttv.xmltv.xml.gz'
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
m3uheadertemplate = '#EXTM3U url-tvg="%s" tvg-shift=%d deinterlace=1 m3uautoload=1 cache=1000\n' % (tvgurl, tvgshift)
m3uchanneltemplate = '#EXTINF:-1 group-title="%(group)s" tvg-name="%(tvg)s" tvg-id="%(tvgid)s" tvg-logo="%(logo)s",%(name)s\n#EXTGRP:%(group)s\n%(url)s\n'

# Format of the tvg-id tag or empty string
tvgid='ttv%(id)s'
