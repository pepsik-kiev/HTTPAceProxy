'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

class ClientCounter(object):

    def __init__(self):
        self.clients = {} # existing broadcast dict {'CID':[client1, client2,....]}
        self.idleAce = False

    def getAllClientsList(self):
        '''
        List of all connected clients for all CID
        '''
        return [item for sublist in self.clients.values() for item in sublist]

    def getClientsList(self, cid):
        '''
        List of Clients by CID
        '''
        return self.clients.get(cid,[])

    def addClient(self, client):
        '''
        Adds client to the list by CID key in broadcast dictionary
        Returns the number of clients of the current broadcast
        '''
        clients = self.clients.setdefault(client.CID, []) # Get a list of clients for a given broadcast
        if clients:
           client.ace, client.broadcast = clients[0].ace, clients[0].broadcast
           self.idleAce.ShutdownAce()
        else:
           client.ace, self.idleAce = self.idleAce, False
        clients.append(client)
        return len(clients)

    def deleteClient(self, client):
        '''
        Remove client from the list by CID key in broadcast dictionary
        '''
        try:
           (client,) = self.getClientsList(client.CID) # Get the last client of existing broadcast
           try:
              self.idleAce = client.ace
              self.idleAce.StopBroadcast()
              client.broadcast.kill()
           except: self.idleAce.ShutdownAce()
           finally: del self.clients[client.CID]
        except:
           self.clients[client.CID].remove(client)
