import socket
import json
import threading

import time
import logging
import yaml
from readerwriterlock import rwlock
from pathlib import Path
from utils import file_hash


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
        
        x = threading.Thread(target = self.my_server.listen)
        x.start()

        # open user input
        self.user_input()

    def request_file(self, filename, addr, writer):
        client_sock = myUDPClient(addr)

        data = (0).to_bytes(1, 'big') + (0).to_bytes(1, 'big') + int(filename).to_bytes(1, 'big')
        client_sock.send(data)
        try:
            data = client_sock.recv()
            print(data[2:].decode(encoding='utf-8'))
            client_sock.send(((data[0]+1)%3).to_bytes(1, "big") +(1).to_bytes(1, 'big'))
        except ConnectionError:
            print("Connection failed")

    def user_input(self):
        while(True):
            file_name, port = input().split(' ')
            self.request_file(file_name, (socket.gethostname(), int(port)), self.client_file_mgr.newWrite(self.down_loca/file_name))
    
    def __del__(self):
        pass

class myUDPClient():
    def __init__(self, addr):
        self.clnt_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = addr

    def send(self, message):
        self.clnt_socket.sendto(message, self.addr)

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
        self.serv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.serv_socket.bind((socket.gethostname(), port))
        self.init_close = False
        self.file_mgr = file_mgr

    def listen(self):
        while True:
            data, addr = self.serv_socket.recvfrom(4096)
            if (data[1] == 3): # end request
                if not self.clients.get(addr, None):
                    del self.clients[addr]
            elif (data[0] == 0 and data[1] == 0): # new client
                reader = self.file_mgr.newRead(int(data[2]))
                self.clients[addr] = { 'requested_file' : data[2], 'reader' : reader, 'window' : [], 
                                             'retries' : 10, 'top': 0, 'last_ack': 0}
                self.load_window(addr)
                self.send_window(addr)
                self.clients[addr]['timer'] = threading.Timer(10.0, self.resend, addr)
            elif (data[1] == 1): # this is an ack
                self.clients[addr]['timer'].cancel()

                self.clients[addr]['last_ack'] = data[0]
                self.send_window(addr)
                self.clients[addr]['top'] = data[0]
                self.clients[addr]['timer'] = threading.Timer(10.0, self.resend, addr)

                print(self.clients[addr])


    def _send_window(self, addr):
        j = 0
        # print(self.clients[addr]['window'])
        for i in range(len(self.clients[addr]['window'])):
            seq_no = ((self.clients[addr]['last_ack'] + j)%3).to_bytes(1, "big")
            data_type = (self.clients[addr]['window'][i][1]).to_bytes(1, "big")
            data = self.clients[addr]['window'][i][0]
            # print(data)
            payload = seq_no + data_type + data
            self.serv_socket.sendto(payload, addr)
            time.sleep(0.2)
            i += 1

    def send_window(self, addr):
        print(self.clients[addr]['last_ack']-self.clients[addr]['top'])
        if(self.clients[addr]['last_ack']-self.clients[addr]['top']==0): #dont add anything to the window, resend window
            self._send_window(addr)
        else:
            print('deleting')
            i = self.clients[addr]['top']
            while i!=self.clients[addr]['last_ack']:
                if self.clients[addr]['window'][1] == 2:
                    self._send_window(addr)
                    return
                self.clients[addr]['window'].pop(0)
                i = (i+1)%3
            self.load_window(addr)
            self._send_window(addr)

    def load_window(self, addr):
        while len(self.clients[addr]['window']) <2:
            try:
                self.clients[addr]['window'].append((next(self.clients[addr]['reader']),0))
            except StopIteration as e:
                self.clients['window'].append((e,2))


    def resend(self, addr):
        pass


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
        print(self.file_hash)
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
    client = Client('./configs/clients/1/1.yaml')
    # client.send_msg("Hello from Client 1", socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (socket.gethostname(),5000))