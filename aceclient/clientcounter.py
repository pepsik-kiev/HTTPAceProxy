'''
Client counter for BroadcastStreamer
'''
__author__ = 'ValdikSS, AndreyPavlenko, Dorik1972'

class ClientCounter(object):

    def __init__(self):
        self.streams = {}   # {'CID':[client1, client2,....]}
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
        try:
            client.ace = self.getClientsList(cid)[0].ace
            client.q = self.getClientsList(cid)[0].q.copy()
            self.idleAce.destroy()
        except: client.ace = self.idleAce
        finally:
            self.streams.setdefault(cid, []).append(client)
            self.idleAce = None

        return self.getClientsQuantity(cid)

    def deleteClient(self, cid, client):
        '''
        Remove client from the dictionary list by CID key
        '''
        clients = self.streams.get(cid,[])
        if not clients: return
        elif len(clients) > 1: self.streams[cid].remove(client)
        else:
            del self.streams[cid]
            try:
               client.ace.STOP()
               client.ace.reset()
               self.idleAce = client.ace
            except: self.idleAce = None
        return
