'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

from itertools import chain

class ClientCounter(object):

    def __init__(self):
        self.clients = {} # existing broadcast dict {'CID':[client1, client2,....]}
        self.idleAce = False

    def getAllClientsList(self):
        '''
        List of all connected clients for all CID
        '''
        return set(chain.from_iterable(self.clients.values()))

    def getClientsList(self, cid):
        '''
        List of Clients by CID
        '''
        return self.clients.setdefault(cid, set())

    def addClient(self, client):
        '''
        Adds client to the list by CID key in broadcast dictionary
        Returns the number of clients of the current broadcast
        '''
        c = next(iter(self.getClientsList(client.CID)), client) # Get the first client of existing broadcast
        if c is client:
           client.ace, self.idleAce = self.idleAce, False
        else:
           client.ace, client.q = c.ace, c.q.copy()
           self.idleAce.ShutdownAce()

        self.clients[client.CID].add(client)
        return self.clients[client.CID].__len__()

    def deleteClient(self, client):
        '''
        Remove client from the list by CID key in broadcast dictionary
        '''
        try:
           _, = self.getClientsList(client.CID) # Try to get the last client of existing broadcast
           try:
              self.idleAce = self.clients.pop(client.CID).pop().ace
              self.idleAce.StopBroadcast()
           except KeyError: self.idleAce = False
           except: self.idleAce.ShutdownAce()
        except:
           self.clients[client.CID].discard(client)
