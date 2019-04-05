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
        c_list = self.clients.setdefault(client.CID, []) # Get a list of clients for a given broadcast
        if c_list:
           client.q, client.ace = c_list[0].q.copy(), c_list[0].ace
           self.idleAce.destroy()
        else:
           client.ace, self.idleAce = self.idleAce, None
        c_list.append(client)

        return len(c_list)

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
