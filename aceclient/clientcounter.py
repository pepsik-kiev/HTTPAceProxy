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
        return list(chain.from_iterable(self.clients.values()))

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
        try:
           c, *_ = self.getClientsList(client.CID) # Get the first client of existing broadcast
           client.ace, client.q, client.b = c.ace, c.q.copy(), c.b
           self.idleAce.ShutdownAce()
        except:
           client.ace, self.idleAce = self.idleAce, False
        finally:
           self.clients[client.CID].add(client)
           return len(self.clients[client.CID])

    def deleteClient(self, client):
        '''
        Remove client from the list by CID key in broadcast dictionary
        '''
        try:
           (client,) = self.getClientsList(client.CID) # Get the last client of existing broadcast
           try:
              self.idleAce = client.ace
              self.idleAce.StopBroadcast()
           except: self.idleAce.ShutdownAce()
           finally:
              del self.clients[client.CID]
              if hasattr(client, 'b'): client.b.kill()
        except:
           self.clients[client.CID].discard(client)
