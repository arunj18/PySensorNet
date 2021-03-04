import socket
import json
import threading
import os
import time
import logging
from typing import Sequence
import yaml
from readerwriterlock import rwlock
from pathlib import Path
from utils import file_hash, verify_hash

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)


WINDOW_SIZE = 2
MAX_SEQ_NO = 2*WINDOW_SIZE

SERVER_MAX_RETRIES = 10
SERVER_RECV_TIMEOUT = 1.0
SERVER_TIMER_THREAD_TIMEOUT = 1.0
SERVER_FILE_NOT_FOUND = 5
SERVER_END_PACKET = 2
SERVER_END_ABNORMAL = 3
SERVER_BUFFER_SIZE = 4096


CLIENT_MAX_RETRIES = 10
CLIENT_REQUEST_RETRIES = 2
CLIENT_RECV_TIMEOUT = 0.4
CLIENT_BUFFER_SIZE = 4096


DATA_PAYLOAD_SIZE = CLIENT_BUFFER_SIZE - 2
DATA_PACKET = 0
DATA_ACK = 1

END_CONNECTION_ACK = 4




class Client():
    def __init__(self, config_file_path):
        # reach out to server to share config
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

        self.serv_conn_status = True
        self.user_shutdown = False


        # then start listening on port
        self.my_server = myUDPServer(self.my_port, self.client_file_mgr)
        if (not self.my_server.check_success()):
            return 
        x = threading.Thread(target = self.my_server.listen)
        x.start()

        # open user input
        self.user_input()
        x.join()

    def move_window(self, seq_nos):
        '''
        Function to move the client window
        param seq_nos : dictionary with window of current sequence numbers
        '''
        for i in range(len(seq_nos)):
            seq_nos[i] = (seq_nos[i] + 1)%MAX_SEQ_NO

    def write_buffer(self, buffer, writer):
        '''
        Function to writer buffer to writer object
        param buffer : list of byte buffers to write to disk
        param writer : writer object of type WriteObj used to write to file
        '''
        for i in range(len(buffer)):
            writer.write(buffer[i])
        buffer.clear()

    def request_cleanup(self, hash, writer, abnormal = False):
        '''
        Function to do cleanup after request is complete
        param hash : hash of the file, if hash is None, consider it as empty file
        param writer : writer object of type WriteObj used to write to file
        param abnormal (False) : flag to signal if abnormal closure of request
        '''
        file_loc = writer.get_filepath()
        del writer
        if (self.serv_conn_status):
            if (abnormal): # connection ended abnormally
                if os.path.exists(file_loc): #remove file
                    logger.info(f"File deleted: {file_loc} due to server connection lost")
                    os.remove(file_loc)
                    return
            if (hash is None): #empty file, do nothing
                logger.info(f"Empty file detected: {file_loc}")
                return 
            if (verify_hash(hash, file_loc)):
                #send success to server 
                # TODO: send success message to server
                logger.info(f"File hash verified: {file_loc}")
                return
            else: #failed hash check
                
                if os.path.exists(file_loc): #remove file
                    logger.info(f"File deleted: {file_loc} due to failed hash check")
                    os.remove(file_loc)
                #TODO: send failure message to server
        else: #lost connection to server, delete file
            if os.path.exists(file_loc): #remove file
                    logger.info(f"File deleted: {file_loc} due to main server connection lost")
                    os.remove(file_loc)

    def _cleanup_abnormal(self, seq_no, hash, writer, client_sock):
        '''
        Function to handle abnormal cleanup. Send ACK for message run cleanup and finally delete socket object
        param seq_no : seq_no of last packet to send ACK for
        param hash : hash of the file requested
        param writer : writer object used to write to disk
        param client_sock: client socket object used to communicate with peer
        '''
        try:
            logger.error(f"Connection reset or closed by {client_sock.get_addr()}")
            client_sock.send_ack(seq_no, True)
            self.request_cleanup(hash, writer, True)
        finally:
            del client_sock


    def request_file(self, filename, addr, writer):
        '''
        Function to handle request file from a peer
        param filename : name/number of the file to request from peer
        param addr : address to find peer at
        param writer : writer object used to writer to disk
        '''
        client_sock = myUDPClient(addr)

        data = (0).to_bytes(1, 'big') + (DATA_PACKET).to_bytes(1, 'big') + int(filename).to_bytes(1, 'big')
        client_sock.send(data)
        client_buffer = []
        retries = CLIENT_MAX_RETRIES
        seq_nos = [0,1]
        connEnd = False
        second_end = False
        hash = None

        while retries>=0 and self.serv_conn_status and (not connEnd):
            try:
                data = client_sock.recv()
                if (data[0] in seq_nos):
                    if (data[0] == seq_nos[0]): #expected sequence and hash
                        if (data[1]== SERVER_FILE_NOT_FOUND): #file not on peer
                            logger.error(f"File not found on peer")
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False
                        if (data[1] == SERVER_END_PACKET): # file empty
                            connEnd = True
                            client_sock.send_ack(data[0])
                            break
                        if second_end: #connection ends with message in buffer
                            connEnd = True
                        if (data[1] == SERVER_END_ABNORMAL): #server shutdown abnormal
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False

                        hash = data[2:].decode(encoding = 'utf-8')
                        print(hash)
                        client_sock.send_ack(data[0])
                        self.move_window(seq_nos)
                        if len(client_buffer) > 0:
                            self.write_buffer(client_buffer, writer)
                            self.move_window(seq_nos)
                            client_buffer.clear()

                    elif (data[0] == seq_nos[1]): #buffer this, don't move the window forward
                        if (data[1] == SERVER_END_PACKET): #connection ended by server
                            second_end = True
                        if (data[1] == SERVER_END_ABNORMAL): #server shutdown abnormal
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False
                        client_buffer.append(data[2:])
                        client_sock.send_ack(data[0])
                        retries = CLIENT_MAX_RETRIES
                        raise ConnectionError # try to get hash again
                break
            except ConnectionError:
                retries -= 1
        if (not self.serv_conn_status):
            logger.error(f"Request file failed due to server connection lost")
            self.request_cleanup(hash, writer)
            del client_sock
            return False
        if connEnd:
            logger.info(f"Connection complete after receiving file from {addr}")
            self.request_cleanup(hash, writer)
            del client_sock
            return True
        if retries < 0:
            logger.error(f"Failed P2P connection to {addr}")
            print(f"Failed P2P connection to {addr}")
            del client_sock
            self.request_cleanup(hash, writer, True)
            return False
        print("done with init")
        retries = CLIENT_MAX_RETRIES
        while retries>=0 and self.serv_conn_status and (not connEnd):
            try:
                
                data = client_sock.recv()
                
                if (data[0] in seq_nos):
                    if (data[0] == seq_nos[0]): #expected sequence and hash
                        if (data[1] == SERVER_END_PACKET): #last packet by server
                            connEnd = True
                        if second_end: #connection ends with message in buffer
                            connEnd = True
                        if (data[1] == SERVER_END_ABNORMAL): #server shutdown abnormal
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return
                        
                        client_sock.send_ack(data[0])
                        writer.write(data[2:])
                        self.move_window(seq_nos)
                        
                        if len(client_buffer) > 0:
                            self.write_buffer(client_buffer, writer)
                            self.move_window(seq_nos)
                            client_buffer.clear()

                        retries = CLIENT_MAX_RETRIES
                    elif (data[0] == seq_nos[1]): #buffer this, don't move the window forward
                        if (data[1] == SERVER_END_PACKET): #last packet by server
                            second_end = True
                        if (data[1] == SERVER_END_ABNORMAL): #server shutdown abnormal
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False
                        client_buffer.append(data[2:])
                        client_sock.send_ack(data[0])
                        retries = CLIENT_MAX_RETRIES
                        raise ConnectionError # try to get sequence 1 again
                else: #maybe resent data or abnormal closure
                    if (data[1] == 3):
                        self._cleanup_abnormal(data[0], hash, writer, client_sock)
                        return False
                    print(data[0], seq_nos)
                    client_sock.send_ack(data[0])
                    retries = CLIENT_MAX_RETRIES
            except ConnectionError:
                retries -= 1
        if (not self.serv_conn_status):
            self.request_cleanup(hash, writer)
            del client_sock
            return False
        if connEnd:
            self.request_cleanup(hash, writer)
            del client_sock
            return True
        if retries < 0:
            logger.error(f"Failed P2P connection to {addr}")
            print(f"Failed P2P connection to {addr}")
            del client_sock
            self.request_cleanup(hash, writer, True)
            return False

    def user_input(self):
        while(True):
            file_name, port = input().split(' ')
            if (int(port) == -1):
                self.my_server.set_close()
                return
            retries = CLIENT_REQUEST_RETRIES
            while (retries > 0):
                if (not self.request_file(file_name, (socket.gethostbyname(socket.gethostname()), int(port)), self.client_file_mgr.newWrite(self.down_loca/(file_name+'.txt')))):
                    retries -= 1
                    logger.error(f"Request for {file_name} from {port} failed, retrying...")
                else:
                    logger.info(f"Request for {file_name} from {port} completed successfully.")
                    break
                retries -= 1


    def __del__(self):
        pass

class myUDPClient():
    def __init__(self, addr):
        self.clnt_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = addr

    def get_addr(self):
        return self.addr

    def send(self, message):
        self.clnt_socket.sendto(message, self.addr)
        logger.info(f"Sent data: {message} to {self.addr}")

    def send_ack(self, seq_no, end = False):
        logger.info(f"Sent ACK for seq: {seq_no}")
        data_type = DATA_ACK
        if (end):
            data_type = END_CONNECTION_ACK
        data = int(seq_no).to_bytes(1, "big") + int(data_type).to_bytes(1, "big")
        self.send(data)

    def recv(self):
        self.clnt_socket.settimeout(CLIENT_RECV_TIMEOUT)
        retries = CLIENT_MAX_RETRIES
        while(retries>=0):
            try:
                data, address = self.clnt_socket.recvfrom(CLIENT_BUFFER_SIZE)
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
        logger.info("Server listen set to close")
        self.init_close = True

    def listen(self):
        while True and (not self.init_close) or len(self.clients)>0:
            self.serv_socket.settimeout(SERVER_RECV_TIMEOUT)
            try:
                data, addr = self.serv_socket.recvfrom(SERVER_BUFFER_SIZE)
                with self.clients_lock:
                    if (data[0] == 0 and data[1] == 0): # new client
                        logger.info(f"New connection request from {addr} for file {data[2]}")
                        if (not self.file_mgr.checkFile(data[2])): # if client does not have file
                            logger.error(f"File {data[2]} not found locally")
                            self.clients[addr] = { 'requested_file' : data[2], 'reader' : None, 'status': 'not found', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr, 1)
                            continue
                        
                        if (self.init_close): # accept no more init requests
                            self.clients[addr] = { 'requested_file' : data[2], 'reader' : None, 'status': 'terminate', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr)
                            continue



                        reader = self.file_mgr.newRead(int(data[2]))
                        

                        self.clients[addr] = { 'requested_file' : data[2], 'reader' : reader, 'window' : {}, 'status': 'active', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}

                        self.load_window(addr, -1) #initialize
                        # print(self.clients[addr]['window'])
                        self.send_window(addr)
                        self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                        self.clients[addr]['timer'].start()
                        # print(self.clients[addr]['window'])

                    elif (data[1] == 1): # this is an ack
                        logger.info(f"Received ACK from {addr} for seq_no: {data[0]}")
                        # print(data[:2])

                        if (addr not in self.clients.keys()):
                            if addr not in self.clients.keys():
                                self.clients[addr] = { 'requested_file' : None, 'reader' : None, 'status': 'terminate', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(1.0, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr)
                            continue
                        with self.clients[addr]['lock']:
                            self.clients[addr]['retries'] = SERVER_MAX_RETRIES
                            self.clients[addr]['timer'].cancel()
                            # print(f"{addr} timer canceled")
                            if data[0] not in self.clients[addr]['window'].keys(): #if it is duplicate ack
                                if len(self.clients[addr]['window'].keys()) != 0:
                                    self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                                    self.clients[addr]['timer'].start()
                                continue
                            do_nothing = False
                            self.clients[addr]['window'][data[0]][2] = 1
                            if len(list(self.clients[addr]['window'].keys()))>1:
                                if data[0] == list(self.clients[addr]['window'].keys())[-2]: #move only
                                    do_nothing = True

                            self.send_window(addr, move_only= True)

                            if do_nothing:
                                self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                                self.clients[addr]['timer'].start()
                                continue

                            if (len(self.clients[addr]['window'])==0): #nothing more to send to this client and connection ended
                                # print(f'deleting {addr}')
                                del self.clients[addr]
                                continue

                            self.send_window(addr)

                            self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            # print(f"{addr} timer started ack")
                            # print(self.clients[addr]['window'])

                    elif (data[1] == END_CONNECTION_ACK): #user shutdown close ack
                        self.clients[addr]['timer'].cancel()
                        logger.info(f"Closed connection to {addr}")
                        del self.clients[addr]
                        continue
                    else:
                        print(data)
            except socket.timeout:
                continue

    def _send_close(self, addr, type = 0):
        payload = int(0).to_bytes(1, "big") + int(3).to_bytes(1, "big")
        if (type == 1):
            payload = int(0).to_bytes(1, "big") + int(SERVER_FILE_NOT_FOUND).to_bytes(1, "big") # file not found
        
        self.serv_socket.sendto(payload, addr)
        logger.info(f"Sent {payload} to {addr}")

    def _send_window(self, addr):
        # print(self.clients[addr]['window'])
        # print(self.clients[addr]['window'].keys())
        for i in self.clients[addr]['window'].keys():
            # print(self.clients[addr]['window'][i])
            if self.clients[addr]['window'][i][2] == 0:
                logger.info(f"Sent data with seq {i}")
                seq_no = int(i).to_bytes(1, "big")
                data_type = (self.clients[addr]['window'][i][1]).to_bytes(1, "big")
                data = self.clients[addr]['window'][i][0]
                # print(data)
                payload = seq_no + data_type + bytes(data)
                self.serv_socket.sendto(payload, addr)
                time.sleep(0.1)

    def send_window(self, addr, move_only = False):
        # print(self.clients[addr]['last_ack']-self.clients[addr]['top'])
        # if(self.clients[addr]['last_ack']-self.clients[addr]['top']==0): #dont add anything to the window, resend window
        #     self._send_window(addr)
        # else:
        delFlag = True
        endFlag = False
        if (len(self.clients[addr]['window'])==0):
            return
        seq_no = list(self.clients[addr]['window'].keys())[-1]
        for i in list(self.clients[addr]['window'].keys()):
            if self.clients[addr]['window'][i][1] == 2:
                endFlag = True
            if self.clients[addr]['window'][i][2] == 1 and delFlag:
                logger.info(f'deleting {i}')
                del self.clients[addr]['window'][i]
            else:
                delFlag = False
        if not endFlag:
            self.load_window(addr, seq_no)
        if not move_only:
            self._send_window(addr)

    def load_window(self, addr, seq_no):
        seq_no = (seq_no + 1)%MAX_SEQ_NO
        while len(self.clients[addr]['window']) < WINDOW_SIZE:
            try:
                # print()
                data = next(self.clients[addr]['reader'])
                # print(data)
                # input()
                self.clients[addr]['window'][seq_no] = [data[0], data[1], 0]
                # print(self.clients[addr]['window'])
                # self.clients[addr]['window'].append((next(self.clients[addr]['reader']),0,0))
            except StopIteration as e:
                # self.clients['window'].append((e,2,0))
                # print(e)
                # self.clients[addr]['window'][seq_no] = [e,2,0]
                break
            seq_no = (seq_no + 1)%MAX_SEQ_NO
        
    def _declare_dead(self, addr):
        with self.clients_lock:
            logger.warning(f"Client with address {addr} declared dead.")
            del self.clients[addr]

    def resend(self, *args):
        addr = (args[0],args[1])
        if addr not in self.clients.keys():
            return
        if self.clients[addr]['lock'].acquire(False): # if it is not able to acquire this lock immediately, then it must be locked by receiving thread
            # print('resend called'
            logger.warning(f"Resend called for {addr} as no ack received. Retry count: {self.clients[addr]['retries']}")
            lock = self.clients[addr]['lock']
            try:
                if (self.clients[addr]['status'] == 'not found'):
                    if self.clients[addr]['retries'] < 0:
                        logger.info(f"Retries expired for closing request or terminated client {addr}")
                        self._declare_dead(addr)
                        return
                    with self.clients_lock:
                        self.clients[addr]['retries'] -= 1
                        self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                        self.clients[addr]['timer'].start()
                        self._send_close(addr, 1)
                        return

                if len(self.clients[addr]['window'])==0:
                    logger.info(f"Nothing more to send to {addr}, declared dead.")
                    self._declare_dead(addr)
                    return

                if (self.clients[addr]['status'] == 'terminate'):
                    if self.clients[addr]['retries'] < 0:
                        logger.info(f"Retries expired for closing request or terminated client {addr}")
                        self._declare_dead(addr)
                        return
                    with self.clients_lock:
                        self._send_close(addr)
                        self.clients[addr]['retries'] -= 1
                        self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, (addr))
                        self.clients[addr]['timer'].start()
                    return

                if self.clients[addr]['retries'] < 0: #declare client dead
                    self._declare_dead(addr)
                    return
                else:
                    self.clients[addr]['retries'] -= 1
                    self.send_window(addr)
                    self.clients[addr]['timer'] = threading.Timer(1.0, self.resend, (addr))
                    self.clients[addr]['timer'].start()
                    return
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
    
    def checkFile(self, i):
        if i in self.filedict.keys():
            return True
        return False

    def newRead(self, i):
        return ReadObj(self.filedict[i]).read()

    def newWrite(self, loc):
        return WriteObj(loc)

class ReadObj():
    '''
    Class for a file read object. Keeps track of current position and reads in 4094 bytes at a time
    '''
    def __init__(self, file_location):
        if (Path(file_location).stat().st_size==0): #empty file
            self.file_hash = None
            return
        self.file_obj = open(file_location, 'rb')
        self.file_hash = bytes(file_hash(file_location), encoding='utf-8')
        self.file_loc = file_location
        # print(self.file_hash)
        # input()

    def get_filepath(self):
        return self.file_loc

    def read(self):
        # print(self.file_hash)
        if (self.file_hash is not None):
            # print(self.file_hash)
            yield (self.file_hash,0)
            while (block:=self.file_obj.read(DATA_PAYLOAD_SIZE)):
                if len(block) < DATA_PAYLOAD_SIZE:
                    yield (block, SERVER_END_PACKET)
                    break
                yield (block, DATA_PACKET)

        else:
            yield (b'', SERVER_END_PACKET)

    def __del__(self):
        if (self.file_hash is not None):
            self.file_obj.close()

class WriteObj():
    '''
    Class for a file write object. Keeps track of current position and writes in 4094 bytes at a time
    '''
    def __init__(self, file_location):
        self.file_obj = open(file_location, 'wb')
        self.file_loc = file_location

    def get_filepath(self):
        return self.file_loc

    def write(self, block):
        self.file_obj.write(block)

    def __del__(self):
        self.file_obj.close()

if __name__ == "__main__":
    # parser = argparse.ArgumentParser(description= "Client ")
    client_no = int(input())
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s", filename = f"./client/log_{client_no}.log" )
    client = Client(f'./configs/clients/{client_no}/{client_no}.yaml')
    # client.send_msg("Hello from Client 1", socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (socket.gethostname(),5000))