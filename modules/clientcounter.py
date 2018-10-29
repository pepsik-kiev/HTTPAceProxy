'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

class ClientCounter(object):

    def __init__(self):
        self.streams = {}   # {'CID': [client1, client2,....]} dict of current broadcasts and clients
        self.idleAce = None

    def getClientsQuantity(self, cid):
        '''
        Quantity of clients in list by CID
        '''
        return len(self.getClientsList(cid))

    def getClientsList(self, cid):
        '''
        List of Clients by CID
        '''
        return self.streams.get(cid,[])

    def totalClients(self):
        '''
        Return total of clients for all CIDs
        '''
        return sum(self.getClientsQuantity(cid) for cid in self.streams)

    def addClient(self, cid, client):
        '''
        Adds client to the dictionary list by CID key and return their number
        '''
        clients = self.getClientsList(cid)
        if clients: client.ace = clients[0].ace; self.idleAce.destroy()
        else: client.ace = self.idleAce
        self.streams.setdefault(cid,[]).append(client)
        self.idleAce = None
        return self.getClientsQuantity(cid)

    def deleteClient(self, cid, client):
        '''
        Remove client from the dictionary list by CID key and return their number
        '''
        clients = self.getClientsList(cid)
        if not clients: return 0
        if client not in clients: return self.getClientsQuantity(cid)
        if self.getClientsQuantity(cid) > 1:
            clients.remove(client)
            return self.getClientsQuantity(cid)
        else:
            del self.streams[cid]
            try:
               client.ace.STOP()
               self.idleAce = client.ace
               self.idleAce.reset()
            except: self.idleAce = None
            finally: return 0

    def deleteAll(self, cid):
        '''
        Remove all Clients from dict by CID
        '''
        clients = self.getClientsList(cid)
        if not clients: return
        del self.streams[cid]
        if self.idleAce: clients[0].ace.destroy()
        else:
            try:
               clients[0].ace.STOP()
               self.idleAce = clients[0].ace
               self.idleAce.reset()
            except: self.idleAce = None
        for c in clients:
            if c.transcoder is not None:
               try: c.transcoder.kill()
               except: pass
