#!/usr/bin/python
# -*- coding: utf-8 -*-

import requests, logging
import config.rutor as config

logger = logging.getLogger("Rutor API")

def cleartext(text):
    text = text.replace('%s' % config.url, '/s/')
    text = text.replace('</td><td ><a class="downgif" href="', "', '")
    text = text.replace('"><img src="/s/i/d.gif" alt="D" /></a><a href="magnet:?xt=', "', '")
    text = text.replace('alt="M" /></a><a href="/torrent/', "', '")
    text = text.replace('</a></td> <td align="right">', "', '")
    text = text.replace('<img src="/s/i/com.gif" alt="C" /></td><td align="right">', "', '")
    text = text.replace('</td><td align="center"><span class="green"><img src="/s/t/arrowup.gif" alt="S" />', "', '")
    text = text.replace('</span><img src="/s/t/arrowdown.gif" alt="L" /><span class="red">', "', '")
    text = text.replace('">', "', '")
    text = text.replace('</span></td></tr>', "']")
    text = text.replace('</span>', "']")
    text = text.replace("</table>", "\r")
    return text

def formtext(http):
    http = http.replace(chr(10), "")
    http = http.replace('&#039;', "").replace('colspan = "2"', "").replace('&nbsp;', "")
    http = http.replace('</td></tr><tr class="gai"><td>', "\rflag1 ['")
    http = http.replace('</td></tr><tr class="gai">', "\rflag1 ")
    http = http.replace('<tr class="tum"><td>', "\rflag1 ['").replace('<tr class="gai"><td>', "\rflag1 ['")
    http = cleartext(http)
    return http


def upd(category, sort, text, page_num):
    try: page_num = str(int(page_num))
    except: page_num = '0'
    if text == '0': stext = ''
    elif text == '1': stext = text
    elif text <> '': stext = text
    stext = stext.replace("%", "%20").replace(" ", "%20").replace("?", "%20").replace("#", "%20")
    if stext == '': categoryUrl = '%s/browse/%s/%s/0/%s' % (config.url, page_num, category, sort)
    else:
        if text == '1': categoryUrl = '%s/search/%s/%s/000/%s/%s' % (config.url, page_num, category, sort, stext)
        else: categoryUrl = config.url + '%s/search/%s/%s/110/%s/%s' % (config.url, page_num, category, sort, stext)

    headers ={'User-Agent':'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)','Connection':'close'}
    try:
        if config.useproxy:
          http = requests.get(categoryUrl, headers=headers, proxies=config.proxies, timeout=30)
        else:
          http = requests.get(categoryUrl, headers=headers, timeout=10)
        http = formtext(http.content)
        LL = http.splitlines()
        return LL
    except requests.exceptions.RequestException:
        logger.error("Can't access to %s" % categoryUrl)
        return None

def format_list(L):
    if not L:
        return ['', '', '', '', '', '', '', '','']
    else:
        Ln = []
        i = 0
        for itm in L:
            i += 1
            if len(itm) > 6:
                if itm[:5] == "flag1":
                    try:Ln.append(eval(itm[6:]))
                    except: pass
        return Ln

def SearchN(category, sort, text, filtr, page='0', min_size=0, max_size=0, min_seeds=0, max_seeds=0):

    RL = upd(category, sort, text, page)
    RootList = format_list(RL)
    items = []

# Title = [0,1,2,3,4,5,6,7,8,9]
# 0 - Дата торрента
# 1 - Ссылка на торрент файл
# 2 - ссылка на magnet
# 3 - ссылка на иконку magnet
# 4 - /torrent/ссылка_на_описание_и_торренты
# 5 - наименование фиьма кирилица/латиница | допинфо
# 6 - кол-во комментариев к торренту
# 7 - размер торрента MB/GB
# 8 - Кол-во раздающих
# 9 - Кол-во скачивающих

    for tTitle in RootList:

        if len(tTitle) == 9:
            tTitle.insert(6, " ")

        if len(tTitle) == 10 and int(tTitle[8]) > 0:

            size = tTitle[7]
            if size[-2:] == "MB": size = size[:-5] + "MB"

            if min_size or max_size:
                csize = 0
                if size[-2:] == "MB":
                    try:
                        csize = float(size[:-2])
                    except:
                        csize = 0
                elif size[-2:] == "GB":
                    csize = size[:-2]
                    try:
                        csize = float(size[:-2]) * 1024
                    except:
                        csize = 0
                if csize:
                    if not (min_size <= csize <= max_size):
                        continue

            seeds = tTitle[8] # Кол-во раздающих
            peers = tTitle[9] # Кол-во скачивающих

            if min_seeds or max_seeds:
                try:
                    if not (min_seeds <= int(seeds) <= max_seeds):
                        continue
                except Exception, e:
                    logger.error("Exception: %s" % repr(e))

            Title = "[ %s | %s ]" % (size, unicode(tTitle[5], 'UTF-8', 'ignore'))
            description_title = "Seeds: %s \ Peers: %s</br> File size: %s</br> %s" %(seeds, peers, size, unicode(tTitle[5], 'UTF-8', 'ignore'))

            itemdict = {'title': Title,
                        'url': '/rutor/list/%s/' % requests.utils.quote(tTitle[1],''),
                        'description_title': description_title,
                        'description': '',
                        'type': 'channel'}

            items.append(itemdict)

    return items
