HTTPAceProxy
===========================================
HTTPAceProxy allows you to watch [Ace Stream](http://acestream.org/) live streams or BitTorrent files over HTTP.
It's written in Python and work on any OS where a python >=2.7.10 with required dependencies 
gevent and psutil are installed. Installed ffmpeg is an optional, but highly recommended, 
for fine tuning for yourself.

HTTPAceProxy supports Ace Stream Content-ID hashes (PIDs), .acelive files, infohash, usual torrent files
and has a different plugins for simple use with SmartTV, KODI, VLC etc. for [TorrentTV](http://torrent-tv.ru/), [AllFon](http://allfon-tv.com/),
[Torrent monitor](https://github.com/ElizarovEugene/TorrentMonitor) and other.

To build the docker image: ```docker build -t httpaceproxy .```
The docker image is for ARMv7 systems. In case you're on traditional x64 machines, replace the FROM with ```FROM python:2```.
