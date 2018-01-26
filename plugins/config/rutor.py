# -*-coding=utf-8-*-
'''
Rutor plugin configuration file

What is this plugin for?
 This plugin allows you to view a torrent without downloading from site Rutor.info
'''
__author__ = 'ex_trin'

# Rutor site URL
siteurl = 'http://rutor.info/'

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
