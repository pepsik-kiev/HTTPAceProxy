# -*-coding=utf-8-*-
'''
Rutor plugin configuration file

What is this plugin for?
 This plugin allows you to view a torrent without downloading from site Rutor.info
'''
__author__ = 'ex_trin'

# Rutor site URL
url = 'http://rutor.info/'

# Proxy settings.
# For example you can install tor browser and add in torrc SOCKSPort 9050
# proxies = {'http' : 'socks5h://127.0.0.1:9050','https' : 'socks5h://127.0.0.1:9050'}
# If your http-proxy need authentification - proxies = { 'https' : 'https://user:password@ip:port' }
useproxy = False
proxies = {'http' : 'socks5://127.0.0.1:9050',
           'https' : 'socks5://127.0.0.1:9050'}

# Отображать следующие категории
categories = [("0", u"Все"),
              ("1", u"Зарубежные фильмы"),
              ("5", u"Русские фильмы"),
              ("4", u"Сериалы"),
              ("7", u"Мультфильмы"),
              ("10", u"Аниме"),
              ("12", u"Научно-популярное"),
              ("6", u"ТВ"),
              ]

# Фильтры на отображение торрентов
# Минимальный размер файла в Mb
min_size = 3000
# Макимальный размер файла в Mb
max_size = 99999
# Минимальное количество пиров
min_peers = 10
# Максимальное количество пиров
max_peers = 99999
# Количество торрентов на одной странице
items_per_page = 15
