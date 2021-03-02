import socket
import json
import threading

import time
import logging
import yaml
from readerwriterlock import rwlock
from pathlib import Path
from utils import file_hash

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

class Client():
    def __init__(self, config_file_path):
        # reach out to server to share config
        # self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with open(config_file_path,'r') as f:
            config = yaml.load(f, Loader = yaml.Loader)
        print(config)
        input()
        self.client_id = config['CLIENTID']
        self.file_vector = config['FILE_VECTOR']
        self.my_port = config['MYPORT']
        self.serv_port = config['SERVERPORT']
        self.file_loca = Path(config_file_path).parent
        self.down_loca = (self.file_loca/'downloads')
        self.down_loca.mkdir(parents = True, exist_ok = True)
        
        self.client_file_mgr = ClientFile(self.file_vector, self.file_loca)
        logging.info("Done with config initialization")




        # self.serv_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.serv_conn.settimeout(10)
        # try:
        #     self.serv_conn.connect((socket.gethostname(),5000))
        # except socket.timeout as e:
        #     raise TimeoutError("Server connection timeout")
        # except Exception as e:
        #     print(e)

        # self._send_init_to_serv(self.serv_conn)

        # then start listening on port
        self.my_server = myUDPServer(self.my_port, self.client_file_mgr)
        if (not self.my_server.check_success()):
            return 
        x = threading.Thread(target = self.my_server.listen)
        x.start()

        # open user input
        self.user_input()

    def request_file(self, filename, addr, writer):
        client_sock = myUDPClient(addr)

        data = (0).to_bytes(1, 'big') + (0).to_bytes(1, 'big') + int(filename).to_bytes(1, 'big')
        client_sock.send(data)
        retries = 10
        begin_seq = 0
        next_seq = 0
        connEnd = False

        while retries:
            try:
                data = client_sock.recv()
                if (data[1] == 2): #connection ended
                    client_sock.send_ack(data[0], True)

                if (data[0] == next_seq): #if sequence number is as expected
                    hash = (data[2:].decode(encoding='utf-8'))
                    print(hash)
                    # next_seq = (next_seq + 1)%4
                    # client_sock.send(((data[0]+1)%3).to_bytes(1, "big") +(1).to_bytes(1, 'big'))
                    client_sock.send_ack(1)
                break
            except ConnectionError:
                retries -= 1
        if retries == 0:
            logger.error(f"Failed P2P connection to {addr}")
            print(f"Failed P2P connection to {addr}")
        else: #start up client sliding window
            pass
        

    

    def user_input(self):
        while(True):
            file_name, port = input().split(' ')
            self.request_file(file_name, (socket.gethostbyname(socket.gethostname()), int(port)), self.client_file_mgr.newWrite(self.down_loca/file_name))

    def __del__(self):
        pass

class myUDPClient():
    def __init__(self, addr):
        self.clnt_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = addr

    def send(self, message):
        self.clnt_socket.sendto(message, self.addr)
        logger.info(f"Sent data: {message} to {self.addr}")

    def send_ack(self, seq_no, end = False):
        data_type = 1
        if (end):
            data_type = 3
        data = int(seq_no).to_bytes(1, "big") + int(data_type).to_bytes(1, "big")
        self.send(data)

    def recv(self):
        self.clnt_socket.settimeout(0.4)
        retries = 10
        while(retries>=0):
            try:
                data, address = self.clnt_socket.recvfrom(4096)
                return data
            except socket.timeout:
                retries -= 1
        raise ConnectionError

    def __del__(self):
        self.clnt_socket.close()

class myUDPServer():
    def __init__(self, port, file_mgr):
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.serv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.serv_success = False
        try:
            self.serv_socket.bind((socket.gethostbyname(socket.gethostname()), port))
            logger.info(f"Started server successfully at address: {(socket.gethostbyname(socket.gethostname()),port)}")
        except OSError as e:
            logger.error(f"Failed P2P init: Address {port} already in use :{e}")
            print(f"Failed P2P init: Port {port} is already in use")
            return
        self.init_close = False
        self.file_mgr = file_mgr
        self.serv_success = True

    def check_success(self):
        return self.serv_success

    def set_close(self):
        self.init_close = True

    def listen(self):
        while True:
            data, addr = self.serv_socket.recvfrom(4096)
            with self.clients_lock:
                if (data[1] == 3): # end request
                    if not self.clients.get(addr, None):
                        del self.clients[addr]
                elif (data[0] == 0 and data[1] == 0): # new client
                    reader = self.file_mgr.newRead(int(data[2]))
                    self.clients[addr] = { 'requested_file' : data[2], 'reader' : reader, 'window' : {}, 'retries' : 10, 'lock': threading.Lock()}
                    self.load_window(addr, -1) #initialize
                    self.send_window(addr)
                    self.clients[addr]['timer'] = threading.Timer(10.0, self.resend, addr)
                    self.clients[addr]['timer'].start()
                    # print(self.clients[addr]['window'])

                elif (data[1] == 1): # this is an ack
                    logger.info(f"Received ACK from {addr} for seq_no: {data[0]}")
                    with self.clients[addr]['lock']:
                        self.clients[addr]['retries'] = 10
                        self.clients[addr]['window'][data[0]][2] = 1
                        self.clients[addr]['timer'].cancel()
                        self.send_window(addr)
                        self.clients[addr]['top'] = data[0]
                        self.clients[addr]['timer'] = threading.Timer(10.0, self.resend, addr)
                        self.clients[addr]['timer'].start()
                        # print(self.clients[addr]['window'])
                    

                    # print(self.clients[addr])


    def _send_window(self, addr):
        # print(self.clients[addr]['window'])
        print(self.clients[addr]['window'].keys())
        for i in self.clients[addr]['window'].keys():
            # print(self.clients[addr]['window'][i])
            if self.clients[addr]['window'][i][2] == 0:
                seq_no = int(i).to_bytes(1, "big")
                data_type = (self.clients[addr]['window'][i][1]).to_bytes(1, "big")
                data = self.clients[addr]['window'][i][0]
                # print(data)
                payload = seq_no + data_type + data
                self.serv_socket.sendto(payload, addr)
                time.sleep(0.1)

    def send_window(self, addr):
        # print(self.clients[addr]['last_ack']-self.clients[addr]['top'])
        # if(self.clients[addr]['last_ack']-self.clients[addr]['top']==0): #dont add anything to the window, resend window
        #     self._send_window(addr)
        # else:
        delFlag = True
        endFlag = False
        seq_no = list(self.clients[addr]['window'].keys())[-1]
        for i in list(self.clients[addr]['window'].keys()):
            if self.clients[addr]['window'][i][1] == 2:
                endFlag = True
            if self.clients[addr]['window'][i][2] == 1 and delFlag:
                print('deleting')
                del self.clients[addr]['window'][i]
            else:
                delFlag = False
            
        if not endFlag:
            self.load_window(addr, seq_no)
        self._send_window(addr)

    def load_window(self, addr, seq_no):
        seq_no = (seq_no + 1)%4
        while len(self.clients[addr]['window']) < 2:

            try:
                self.clients[addr]['window'][seq_no] = [next(self.clients[addr]['reader']),0,0]
                # print(self.clients[addr]['window'])
                # self.clients[addr]['window'].append((next(self.clients[addr]['reader']),0,0))
            except StopIteration as e:
                # self.clients['window'].append((e,2,0))
                self.clients[addr]['window'][seq_no] = [e,2,0]
            seq_no = (seq_no + 1)%4
            

    def resend(self, *args):
        addr = (args[0],args[1])
        if self.clients[addr]['lock'].acquire(False): # if it is not able to acquire this lock immediately, then it must be locked by receiving thread
            print('resend called')
            logger.warning(f"Resend called for {addr} as no ack received. Retry count: {self.clients[addr]['retries']}")
            lock = self.clients[addr]['lock']
            try:
                if self.clients[addr]['retries'] == 0: #declare client dead
                    with self.clients_lock:
                        logger.warning(f"Client with address {addr} declared dead.")
                        del self.clients[addr]
                else:
                    self.clients[addr]['retries'] -= 1
                    self.send_window(addr)
                    self.clients[addr]['timer'] = threading.Timer(10.0, self.resend, (addr))
                    self.clients[addr]['timer'].start()
            finally:
                lock.release()
        else:
            logger.debug("Cancelled timer called.")
        # if the lock is being used by server receive thread then do nothing

    def __del__(self):
        # self.serv_socket.shutdown(1)
        self.serv_socket.close()
class ClientFile():
    '''
    Class to handle files of the client
    '''
    def __init__(self, filevector, file_location):
        '''
        Initialize the file handler for the client
        '''
        self.filedict = {}
        for i in range(len(filevector)):
            if filevector[i] == '1':
                file_i_location = file_location/(str(i)+'.txt')
                print(file_i_location)
                if not Path(file_i_location).is_file():
                    raise FileNotFoundError
                self.filedict[i] = file_i_location

    def newRead(self, i):
        return ReadObj(self.filedict[i]).read()

    def newWrite(self, loc):
        return WriteObj(loc)

class ReadObj():
    '''
    Class for a file read object. Keeps track of current position and reads in 4094 bytes at a time
    '''
    def __init__(self, file_location):
        self.file_obj = open(file_location, 'rb')
        self.file_hash = bytes(file_hash(file_location), encoding='utf-8')


    def read(self):
        # print(self.file_hash)
        yield self.file_hash
        while (block:=self.file_obj.read(4094)):
            if len(block) < 4094:
                return block
            yield block

    def __del__(self):
        self.file_obj.close()

class WriteObj():
    '''
    Class for a file write object. Keeps track of current position and writes in 4094 bytes at a time
    '''
    def __init__(self, file_location):
        self.file_obj = open(file_location, 'wb')

    def write(self, block):
        self.file_obj.write(block)

    def __del__(self):
        self.file_obj.close()

if __name__ == "__main__":
    # parser = argparse.ArgumentParser(description= "Client ")
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s", filename = "./logs/client.log" )
    client = Client('./configs/clients/2/2.yaml')
    # client.send_msg("Hello from Client 1", socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (socket.gethostname(),5000))