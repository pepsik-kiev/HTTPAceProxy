'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

class ClientCounter(object):

    def __init__(self):
        self.clients = {} # existing broadcast dict {'CID':[client1, client2,....]}
        self.idleAce = None

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
        c = next(iter(self.getClientsList(client.CID)), None) # Get the first client of existing broadcast
        if c:
           client.q, client.ace = c.q.copy(), c.ace
           self.idleAce.destroy()
        else:
           client.ace, self.idleAce = self.idleAce, None
        self.clients.setdefault(client.CID, []).append(client)

        return len(self.getClientsList(client.CID))

    def deleteClient(self, client):
        '''
        Remove client from the list by CID key in broadcast dictionary
        '''
        try:
           (client,) = self.getClientsList(client.CID) # Get the last client of existing broadcast
           try:
              self.idleAce, client.ace = client.ace, None
              self.idleAce.STOP(); self.idleAce.reset()
           except: self.idleAce.destroy()
           finally: del self.clients[client.CID]
        except:
           self.clients[client.CID].remove(client)
