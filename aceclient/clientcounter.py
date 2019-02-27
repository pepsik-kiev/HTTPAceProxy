'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

class ClientCounter(object):

    def __init__(self):
        self.clients = {}   # {'CID':[client1, client2,....]}
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
        Adds client to the dictionary list by CID key and returns their number
        '''
        clients = self.getClientsList(client.CID)
        if clients:
           existing_client = clients[0]
           client.ace = existing_client.ace
           client.q = existing_client.q.copy()
           self.idleAce.destroy()
        else: client.ace = self.idleAce

        self.clients.setdefault(client.CID, []).append(client)
        self.idleAce = None

        return len(self.getClientsList(client.CID))

    def deleteClient(self, client):
        '''
        Remove client from the dictionary list by CID key
        '''
        clients = self.getClientsList(client.CID)
        if not clients: return
        if len(clients) > 1: self.clients[client.CID].remove(client)
        else:
            del self.clients[client.CID]
            try:
               client.ace.STOP()
               client.ace.reset()
               self.idleAce = client.ace
            except: self.idleAce = None
        return
