# -*- coding: utf-8 -*-
'''
Simple Client Counter for VLC VLM
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

import gevent
import logging
import time

class ClientCounter(object):

    def __init__(self):
        self.lock = gevent.lock.RLock()
        self.streams = {}   # {'CID': [client1, client2,....]} dict of current broadcasts and clients
        self.idleace = None
        self.idleSince = 30 # Send SHUTDOWN to AceEngine if it in IDLE more than
        self.total = 0      # Client counter total
        gevent.spawn(self.checkIdle)

    def count(self, cid):
        with self.lock:
            clients = self.streams.get(cid)
            return len(clients) if clients else 0

    def getClients(self, cid):
        with self.lock: return self.streams.get(cid)

    def add(self, cid, client):
        with self.lock:
            clients = self.streams.get(cid)
            if clients: client.ace = clients[0].ace
            else: client.ace = self.idleace
            self.idleace = None

            client.queue = client.ace._streamReaderQueue.copy()
            self.streams[cid].append(client) if cid in self.streams else self.streams.update({cid:[client]})

            self.total += 1
            return len(self.streams[cid])

    def delete(self, cid, client):
        with self.lock:
            if not cid in self.streams: return 0
            clients = self.streams[cid]
            if client not in clients: return len(clients)
            try:
                if len(clients) > 1:
                    clients.remove(client)
                    return len(clients)
                else:
                    del self.streams[cid]
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
                if not cid in self.streams: return
                clients = self.streams[cid]
                del self.streams[cid]
                self.total -= len(clients)
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
