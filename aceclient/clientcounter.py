# -*- coding: utf-8 -*-
'''
Simple Client Counter for VLC VLM
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
import logging
import time

from aceconfig import AceConfig
from aceclient import AceClient

class ClientCounter(object):

    def __init__(self):
        self.lock = gevent.lock.RLock()
        self.clients = {}
        self.idleace = None
        self.total = 0
        gevent.spawn(self.checkIdle)

    def createAce(self):
        logger = logging.getLogger('CreateAce')
        logger.debug('Create connection to AceEngine.....')
        ace = AceClient(AceConfig.acehostslist, AceConfig.aceconntimeout, AceConfig.aceresulttimeout)
        ace.aceInit(AceConfig.acesex, AceConfig.aceage, AceConfig.acekey)
        return ace

    def count(self, cid):
        with self.lock:
            clients = self.clients.get(cid)
            return len(clients) if clients else 0

    def getClients(self, cid):
        with self.lock: return self.clients.get(cid)

    def add(self, cid, client):
        with self.lock:
            clients = self.clients.get(cid)
            if clients:
                client.ace = clients[0].ace
                client.queue = client.ace._streamReaderQueue.copy()
                clients.append(client)
            else:
                if self.idleace is not None:
                    client.ace = self.idleace
                    self.idleace = None
                else:
                    try: client.ace = self.createAce()
                    except Exception as e:
                        logging.error('Failed to create AceClient: %s' % repr(e))
                        return 0

                clients = [client]
                self.clients[cid] = clients
            self.total += 1
            return len(clients)

    def delete(self, cid, client):
        with self.lock:
            if not cid in self.clients: return 0
            clients = self.clients[cid]
            if client not in clients: return len(clients)
            try:
                if len(clients) > 1:
                    clients.remove(client)
                    return len(clients)
                else:
                    del self.clients[cid]
                    if self.idleace is not None: client.ace.destroy()
                    else:
                        try:
                            client.ace.STOP()
                            self.idleace = client.ace
                            self.idleace.reset()
                        except: client.ace.destroy()
                    return 0
            finally: self.total -= 1

    def deleteAll(self, cid):
        clients = None
        try:
            with self.lock:
                if not cid in self.clients: return
                clients = self.clients[cid]
                del self.clients[cid]
                self.total -= len(clients)
                if self.idleace is not None: clients[0].ace.destroy()
                else:
                    try:
                        clients[0].ace.STOP()
                        self.idleace = clients[0].ace
                        self.idleace.reset()
                    except: clients[0].ace.destroy()
        finally:
                if clients:
                   for c in clients: c.destroy()

    def destroyIdle(self):
        with self.lock:
            try:
                if self.idleace is not None: self.idleace.destroy()
            finally: self.idleace = None

    def checkIdle(self):
        while 1:
            with self.lock:
                ace = self.idleace
                if ace and (ace._idleSince + 60.0 <= time.time()):
                    self.idleace = None
                    ace.destroy()
            gevent.sleep(60.0)
