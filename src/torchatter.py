#
# torchatter base module
# implements basic torchat stuff
#
import socket, time, random, threading, struct
from asynchat import async_chat as chat
from asyncore import dispatcher, loop

class base_client:
    def __init__(self,parent):
        self.dbg = parent.dbg
        self.onions = {}
        self.parent = parent

    def connected(self,conn):
        pass

    def disconnected(self,conn):
        pass

    def on_status(self,conn):
        pass

    def on_chat(self,conn):
        pass

    def on_add_me(self,conn):
        self.connected(conn)
        conn.send_status()

    def connect(self,onion_id):
        self.parent.connect_out

    def chat_all(self,msg):
        for onion in self.onions:
            self.onions[onion].chat(str(msg))

    def chat(self,onion_id,msg):
        onion_id = str(onion_id)
        if onion_id in self.onions:
            self.onions[onion_id].chat(str(msg))
            return True
        self.dbg('did not find '+onion_id)
        return False
        
    def _not_impl(self):
        raise NotImplemented()

class dummy_client(base_client):

    def __init__(self,parent):
        base_client.__init__(self,parent)

    def connected(self,connection):
        pass
    def disconnected(self,connection):
        pass
    def on_status(self,connection):
        pass
    def on_chat(self,connection):
        pass
    def on_add_me(self,connections):
        pass

class handler(chat):
    '''
    generic connection handler
    '''
    def __init__(self,sock,parent):
        chat.__init__(self,sock)
        self.handle_error = parent.handle_error
        self.parent = parent
        self.set_terminator(b'\n')
        self._ibuffer = []
        self._inq = []
        self.client = None
        self.version = None
        self.status = 'offline'
        self._client = parent._client
        self.dbg = parent.dbg
        self._ready = True
        self.get_last_msg = self._pop_chat

    def chat(self,msg):
        self.send_msg(msg)

    def messages(self):
        while self._has_chat():
            yield self._pop_chat()

    def collect_incoming_data(self,data):
        self._ibuffer.append(data)

    def found_terminator(self):
        line = ''
        for part in self._ibuffer:
            line += part.decode('utf-8',errors='replace')
        self._ibuffer = []
        self.dbg('%s got line %s'%(self,[line]))
        line = self._unescape(line)
        self.got_line(line)

    def got_line(self,line):
        """
        handle line
        """
        parts = line.split(' ')
        cmd = parts[0]
        if hasattr(self,'on_'+cmd):
            getattr(self,'on_'+cmd)(' '.join(parts[1:]))
        if hasattr(self._client,'on_'+cmd):
            getattr(self._client,'on_'+cmd)(self)
        return hasattr(self,'on_'+cmd)

    def send_msg(self,line):
        """
        send chat message
        """
        self.send_line('message '+line)
    
    def _escape(self,line):
        return str(line).replace("\\", "\\/").replace("\n", "\\n")

    def _unescape(self,line):
        return str(line).replace("\\n", "\n").replace("\\/", "\\")

    def send_line(self,line):
        """
        send line
        """
        line = self._escape(line).encode('utf-8',errors='replace')
        self.dbg('%s send line %s'%(self,[line]))
        self.push(line)
        self.push(b'\n')

    def handle_close(self):
        self._client.disconnected(self)
        self.close()

    def on_add_me(self,string):
        self._client.on_add_me(self)

    def on_client(self,string):
        if self.client is None:
            self.client = string

    def on_version(self,string):
        if self.version is None:
            self.version = string

    def on_pong(self,string):
        pass

    def on_ping(self,string):
        pass
            
    def on_message(self,string):
        for line in string.split('\n'):
            self._inq.append(line)
        self._client.on_chat(self)
            
    def on_status(self,string):
        self.status = string
        self._client.on_status(self)

    def _has_chat(self):
        return len(self._inq) > 0
    
    def _pop_chat(self):
        if self._has_chat():
            return self._inq.pop()

    def send_ping(self):
        self.send_line('ping '+self.parent.tc_onion+' '+self.cookie)

    def send_pong(self,cookie):
        self.send_line('pong %s'%(self.cookie))

    def readable(self):
        if int(time.time()) % 4 == 0:
            self.send_update()
        return chat.readable(self)
    
    def send_update(self):
        pass

    def send_status(self):
        self.send_pong(self.cookie)
        self.send_line('client '+self.parent.tc_client_name)
        self.send_line('version '+self.parent.tc_version)
        self.send_line('add_me')
        self.send_line('status available')

    def is_out(self):
        """
        is this connection an outgoing connection?
        """
        return True
  
class _in_handler(handler):
    '''
    inbound chat handler
    '''
    def __init__(self,sock,parent):
        handler.__init__(self,sock,parent)
        self.dbg('inbound handler made')
        self.onion = parent.tc_onion

    def got_line(self,line):
        if not handler.got_line(self,line):
            self.send_line('not_implemented')

    def on_pong(self,string):
        self.onion = self.parent.cookies[string].onion
        out = self.parent.cookies.pop(string)
        out.send_pong(self.cookie)
        out.send_status()
        self._client.onions[self.onion] = out

    def on_ping(self,string):
        onion, cookie = tuple(string.split(' '))
        self.dbg('tc ping cookie='+cookie+' onion='+onion)
        if onion not in self.parent.onions:
            self.parent.connect_out(onion,cookie)
            self.cookie = cookie

class _out_handler(handler):
    '''
    outgoing chat handler
    '''
    def __init__(self,cookie,onion,parent):
        client = parent._client
        self.onion = onion.replace('.onion','')
        # blocks
        sock = parent.tor_connect(onion,11009)
        if sock is None:
            raise Exception()

        handler.__init__(self,sock,parent)
        self.cookie = cookie
        self.dbg('new out with cookie='+self.cookie)
        self.parent.cookies[self.cookie] = self
        self.send_ping()
        self.dbg('outbound handler made')

    def send_update(self):
        self.send_line('status available')
        

class torchat(dispatcher):
    
    def __init__(self,onion,client_class,host='127.0.0.1',port=11009,torsocks_host='127.0.0.1',torsocks_port=9050,debug=False):
        dispatcher.__init__(self)        
        self.create_socket(socket.AF_INET,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host,port))
        self.listen(5)

        self.tc_client_name = 'TorChatter'
        self.tc_version = '0.0.1'
        self.tc_onion = onion
        self.onions = {}
        self.cookies = {}
        self._ts_addr = (torsocks_host,torsocks_port)

        self._client = client_class(self)
        self._debug = debug
        self.dbg('torchat made client=%s'%client_class.__name__)

    def dbg(self,msg):
        """
        print debug message
        """
        print ('[%d] %s'%(time.time(),msg))
    
    def tor_connect(self,host,port):
        sock = socket.socket()
        self.dbg('tor connect to %s:%s'%(host,port)+ ' via %s:%s'%self._ts_addr)
        sock.connect(self._ts_addr)
        sock.send(struct.pack('BB',4,1))
        sock.send(struct.pack('!H',port))
        sock.send(struct.pack('BBBB',0,0,0,1))
        sock.send(b'proxy\x00')
        sock.send(host.encode('ascii'))
        sock.send(b'\x00')
        d = sock.recv(8)
        if len(d) != 8 or d[0] != 0 or d[1] != 90:
            return None
        self.dbg('tor connected to %s:%s'%(host,port))
        return sock
            
    def gen_cookie(self):
        cookie = ''
        for n in range(35):
            cookie += str(random.randint(0,n+1))
        return cookie
    
    def handle_accepted(self,sock,addr):
        self.dbg('got connection')
        _in_handler(sock,self)

    def connect_onion(self,onion):
        self.dbg('connect to %s'%onion)
        self.connect_out(onion,None,self._client)

    def connect_out(self,onion,cookie):
        def func(onion,cookie,client):
            onion += '.onion'
            self.dbg('tc connect to '+onion+' cookie='+str(cookie))
            o = onion.replace('.onion','')
            self.dbg('tc got outcon to '+onion)
            while True:
                time.sleep(1)
                self.dbg(onion+' try connection')
                try:
                    self.onions[o] = None
                    self.onions[o] = _out_handler(cookie,onion,self)
                except Exception as e:
                    self.dbg(e)
                    continue
                outcon = self.onions[o]
                self.cookies[cookie] = outcon
                break
            self.dbg('done connecting')
        if onion not in self.onions:
            threading.Thread(target=func,args=(onion,cookie,self._client)).start()
        

run = loop
