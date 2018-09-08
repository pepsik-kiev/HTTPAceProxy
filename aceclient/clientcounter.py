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
        self.clients = {} # {'CID': [client1, client2,....]}
        self.idleace = None
        self.idleSince = 30 # Send SHUTDOWN to AceEngine if it in IDLE more than
        self.total = 0 # Total clients сounter
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
            if clients: client.ace = clients[0].ace
            else:
                if self.idleace:
                    client.ace = self.idleace
                    self.idleace = None
                else:
                    try:
                        client.ace = self.createAce()
                    except Exception as e:
                        logging.error('Failed to create AceClient: %s' % repr(e))
                        return 0

            client.queue = client.ace._streamReaderQueue.copy()
            self.clients[cid].append(client) if cid in self.clients else self.clients.update({cid:[client]})

            self.total += 1
            return len(self.clients[cid])

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
                    client.ace._streamReaderState.clear()
                    if self.idleace: client.ace.destroy()
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
                clients[0].ace._streamReaderState.clear()
                if self.idleace: clients[0].ace.destroy()
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
                if self.idleace: self.idleace.destroy()
            finally: self.idleace = None

    def checkIdle(self):
        while 1:
            gevent.sleep(self.idleSince)
            if self.idleace and self.idleace._state.ready():
                STATE = self.idleace._state.get_nowait()
                if STATE[0] == '0' and (time.time() - STATE[1]) >= self.idleSince: self.destroyIdle()
