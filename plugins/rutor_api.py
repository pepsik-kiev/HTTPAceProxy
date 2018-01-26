#!/usr/bin/python
# -*- coding: utf-8 -*-


import requests, logging
import config.rutor as config

logger = logging.getLogger("RUTOR API")

def ru(x):return unicode(x, 'utf8', 'ignore')


def GET(target, referer, post=None):
    headers ={'User-Agent':'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)','Connection':'close'}
    try:
        if config.useproxy:
          r = requests.get(target, headers=headers, proxies=config.proxies, data=post, timeout=30)
        else:
          r = requests.get(target, headers=headers, data=post, timeout=10)
        return r.content
    except requests.exceptions.RequestException:
        logger.error("Can't access to %s" % target)

def cleartext(text):
    text = text.replace("http://s.rutor.info/", '/s/')
    text = text.replace('</td><td ><a class="downgif" href="', "', '")
    text = text.replace('"><img src="/s/t/d.gif" alt="D" /></a><a href="magnet:?xt=', "', '")
    text = text.replace('alt="M" /></a><a href="/torrent/', "', '")
    text = text.replace('</a></td> <td align="right">', "', '")
    text = text.replace('<img src="/s/t/com.gif" alt="C" /></td><td align="right">', "', '")
    text = text.replace('</td><td align="center"><span class="green"><img src="/s/t/arrowup.gif" alt="S" />', "', '")
    text = text.replace('</span><img src="/s/t/arrowdown.gif" alt="L" /><span class="red">', "', '")
    text = text.replace('">', "', '")
    text = text.replace('</span></td></tr>', "']")
    text = text.replace('</span>', "']")
    text = text.replace("</table>", "\r")
    return text

def formtext(http):
    http = http.replace(chr(10), "")
    http = http.replace('&#039;', "").replace('colspan = "2"', "").replace('&nbsp;', "")  # исключить
    http = http.replace('</td></tr><tr class="gai"><td>', "\rflag1 ['")
    http = http.replace('</td></tr><tr class="gai">', "\rflag1 ")  # начало
    http = http.replace('<tr class="tum"><td>', "\rflag1 ['").replace('<tr class="gai"><td>', "\rflag1 ['")  # разделить
    http = cleartext(http)
    return http


def upd(category, sort, text, n):
    try: n = str(int(n))
    except: n = "0"
    if text == '0':stext = ""
    elif text == '1':stext = text
    elif text <> '':stext = text
    stext = stext.replace("%", "%20").replace(" ", "%20").replace("?", "%20").replace("#", "%20")
    if stext == "":
        categoryUrl = config.url + '/browse/' + n + '/' + category + '/0/' + sort
    else:
        if text == '1':categoryUrl = config.url + '/search/' + n + '/' + category + '/000/' + sort + '/' + stext
        else: categoryUrl = config.url + '/search/' + n + '/' + category + '/110/' + sort + '/' + stext

    # Get Category
    http = GET(categoryUrl, config.url, None)

    if http == None:
        logger.warning('Сервер  %s не отвечает' % config.url)
        return None
    else:
        http = formtext(http)
        LL = http.splitlines()
        return LL


def format_list(L):
    if L == None:
        return ["", "", "", "", "", "", "", "", ""]
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

def rulower(text):
    text = text.strip()
    text = text.lower()
    return text


def SearchN(category, sort, text, filtr, page='0', min_size=0, max_size=0, min_peers=0, max_peers=0):

    # Hide CAMRip, TS, CamRIP, DVDScr  Video
    HideScr = 'true'
    # Hide TS sound video
    HideTSnd = 'true'
    # Filter mode options
    TitleMode = '1'
    EnabledFiltr = 'false'
    Filtr = ''

    RL = upd(category, sort, text, page)
    RootList = format_list(RL)
    k = 0
    TLD = []

    items = []

    defekt = 0
    for tTitle in RootList:
        if len(tTitle) == 9:
            tTitle.insert(6, " ")

        if len(tTitle) == 10 and int(tTitle[8]) > 0:

            size = tTitle[7]
            if size[-2:] == "MB":size = size[:-5] + "MB"

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

            if len(tTitle[8]) == 1:sids = tTitle[8].center(9)
            elif len(tTitle[8]) == 2:sids = tTitle[8].center(8)
            elif len(tTitle[8]) == 3:sids = tTitle[8].center(7)
            elif len(tTitle[8]) == 4:sids = tTitle[8].center(6)
            else:sids = tTitle[8]

            if min_peers or max_peers:
                try:
                    if not (min_peers <= int(sids) <= max_peers):
                        continue
                except Exception, e:
                    logger.error("Exception: %s" % repr(e))
            #------------------------------------------------
            k += 1
            nnn = tTitle[1].rfind("/") + 1
            ntor = tTitle[1][nnn:]
            #------------------------------------------------
            Title = "|" + sids + "|  " + tTitle[5]

            flt4 = 0
            flt2 = 0
            flt3 = 0
            ltl = rulower(Title)
            if filtr[4] == "" or ltl.find(rulower(filtr[4])) > 0: flt4 = 1
            if filtr[2] == "" or tTitle[5].find(filtr[2].replace("1990", "199").replace("1980", "198").replace("1970", "197").replace("1960", "196").replace("1950", "195").replace("1940", "194").replace("1930", "193")) > 0: flt2 = 1
            if filtr[3] == "" or Title.find(filtr[3]) > 0: flt3 = 1
            Sflt = flt4 + flt2 + flt3


            if HideScr == 'true':
                nH1 = Title.find("CAMRip")
                nH2 = Title.find(") TS")
                nH3 = Title.find("CamRip")
                nH4 = Title.find(" DVDScr")
                nH = nH1 + nH2 + nH3 + nH4
            else:
                nH = -1

            if HideTSnd == 'true':
                sH = Title.find("Звук с TS")
            else:
                sH = -1

            if TitleMode == '1':
                k1 = Title.find('/')
                if k1 < 0: k1 = Title.find('(')
                tmp1 = Title[:k1]
                n1 = Title.find('(')
                k2 = Title.find(' от ')
                if k2 < 0: k2 = None
                tmp2 = Title[n1:k2]
                Title = tmp1 + tmp2
                Title = Title.replace("| Лицензия", "")
                Title = Title.replace("| лицензия", "")
                Title = Title.replace("| ЛицензиЯ", "")


            tTitle5 = ru(tTitle[5].strip().replace("ё", "е"))
            nc = tTitle5.find(") ")
            nc2 = tTitle5.find("/ ")
            if nc2 < nc and nc2 > 0: nc = nc2
            CT = rulower(tTitle5[:nc]).strip()

            # Title=CT
            if Sflt == 3 and nH < 0 and sH < 0 and (CT not in TLD):

                dict_info = {}
                dict_info['ntor'] = ntor
                UF = 0
                if EnabledFiltr == 'true' and Filtr <> "":
                    Fnu = Filtr.replace(",", '","')
                    Fnu = Fnu.replace('" ', '"')
                    F1 = eval('["' + Fnu + '", "4565646dsfs546546"]')
                    Tlo = rulower(Title)
                    try:Glo = rulower(dict_info['genre'])
                    except: Glo = "45664sdgd6546546"
                    for Fi in F1:
                        if Tlo.find(rulower(Fi)) >= 0:UF += 1
                        if Glo.find(rulower(Fi)) >= 0:UF += 1
                Tresh = ["Repack", " PC ", "XBOX", "RePack", "FB2", "TXT", "DOC", " MP3", " JPG", " PNG", " SCR"]
                for TRi in Tresh:
                    if tTitle[5].find(TRi) >= 0:UF += 1
                if UF == 0:
                    TLD.append(CT)
                    row_url = tTitle[1]
                    Title = Title.replace("&quot;", '"')

                    Title = "[%s]" % unicode(str(sids.strip() + " | " + size.strip() + " | " + tTitle[5].strip()), 'utf-8')

                    itemdict = {'title': Title,
                                'url': '/rutor/list/%s/' % requests.utils.quote(row_url,''),
                                'description_title': Title,
                                'description': '',
                                'type': 'channel'
                                }
                    items.append(itemdict)
                else: defekt += 1
            else: defekt += 1

    return items
