'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

from itertools import chain

class ClientCounter(object):

    def __init__(self):
        self.clients = {} # existing broadcast dict {'infohash':[client1, client2,....]}
        self.idleAce = False

    def getAllClientsList(self):
        '''
        List of all connected clients for all infohash
        '''
        return set(chain.from_iterable(self.clients.values()))

    def getClientsList(self, infohash):
        '''
        List of Clients by infohash
        '''
        return self.clients.setdefault(infohash, set())

    def addClient(self, client):
        '''
        Adds client to the list by infohash key in broadcast dictionary
        Returns the number of clients of the current broadcast
        '''
        c = next(iter(self.getClientsList(client.infohash)), client) # Get the first client of existing broadcast
        if c is client:
           client.__dict__.update({'ace': self.idleAce})
           self.idleAce = False
        else:
           client.__dict__.update({'ace': c.ace, 'q': c.q.copy()})
           self.idleAce.ShutdownAce()

        self.clients[client.infohash].add(client)
        return self.clients[client.infohash].__len__()

    def deleteClient(self, client):
        '''
        Remove client from the list by infohash key in broadcast dictionary
        '''
        try:
           _, = self.getClientsList(client.infohash) # Try to get the last client of existing broadcast
           try:
              self.idleAce = self.clients.pop(client.infohash).pop().ace
              self.idleAce.StopBroadcast()
           except KeyError: self.idleAce = False
           except: self.idleAce.ShutdownAce()
        except:
           self.clients[client.infohash].discard(client)
