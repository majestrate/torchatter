import torchatter

class bot_client(torchatter.base_client):
    
    def __init__(self,parent):
        torchatter.base_client.__init__(self,parent)
    
    def connected(self,conn):
        """
        client has connected
        """
        self.dbg('connected!')

    def on_add_me(self,conn):
        conn.chat('connected to bot')

    def tell_all(self):
        """
        broadcast to all open clients
        """
        self.chat_all('global message')

    def on_chat(self,conn):
        """
        called when we get new messages
        """
        # iterate through all new messages
        for msg in conn.messages():
            # print debug
            self.dbg('message [%s] %s'%(conn.onion,msg))
            msg = 'you are %s and said "%s"'%(conn.onion,msg)
            self.dbg(msg)
            self.chat(conn.onion,msg)

def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('--onion',type=str,required=True,help='torchat id (without the .onion')
    ap.add_argument('--tc-port',type=int,default=11009,help='port to bind torchat on')
    ap.add_argument('--ts-port',type=int,default=9150,help='tor socks port')
    args = ap.parse_args()

    torchatter.torchat(args.onion,bot_client,port=args.tc_port,torsocks_port=args.ts_port,debug=True).dbg('running')
    torchatter.run()

if __name__ == '__main__':
    main()
