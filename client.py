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

CLIENT_MAIN_SERV_TIMEOUT = 5.0
CLIENT_MAIN_SERV_RETRIES = 10

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
        self.down_loca = (self.file_loca/'downloads') # set downloads path for client
        self.down_loca.mkdir(parents = True, exist_ok = True)
        self.client_file_mgr = ClientFile(self.file_vector, self.file_loca)
        logging.info("Done with config initialization")

        self.serv_conn_status = True
        self.client_shutdown = False

        # send init message to server 
        print("Do INIT")
        self.main_serv_init()
        print("INIT DONE")



        # then start listening on port
        # my_server = myUDPServer(self.my_port, self.client_file_mgr)
        # if (not my_server.check_success()):
            # return 
        # server = threading.Thread(target = self.my_server.listen)
        # server.start()

        # open user input
        input_thread = threading.Thread(target = self.user_input)
        input_thread.start()

        while (not self.client_shutdown):
            # do nothing
            pass
        print("Client shutting down...")
        input_thread.join()
        # server.join()
    def main_serv_init(self):
        self.main_serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.main_serv.connect((socket.gethostbyname(socket.gethostname()),self.serv_port))
            self.main_serv.sendall(bytes("INIT:"+str(self.client_id)+":"+str(self.file_vector)+":"+str(self.my_port), encoding ='utf-8'))
            retries = CLIENT_MAIN_SERV_RETRIES
            flag = False
            while(retries):
                try:
                    self.main_serv.settimeout(CLIENT_MAIN_SERV_TIMEOUT)
                    success = self.main_serv.recv(4096)
                    flag = True
                    if not success:
                        break
                    print(success.decode('utf-8'))
                    input()
                except socket.timeout:
                    retries -= 1
            print("Got success")

        except Exception as e:
            print("Socket connection failed ", e)
            self.main_serv.close()
            return False

    def main_serv_hold(self):
        pass

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
        seq_nos = [0,1] #starting sequence numbers that it should get from the server
        connEnd = False
        second_end = False # if buffer has the ending packet
        hash = None # hash of the incoming file

        while retries>=0 and self.serv_conn_status and (not connEnd):
            try:
                data = client_sock.recv() # try to get data from socket
                if (data[0] in seq_nos):
                    if (data[0] == seq_nos[0]): #expected sequence and hash
                        if (data[1]== SERVER_FILE_NOT_FOUND): #file not on peer
                            logger.error(f"File not found on peer")
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False
                        if (data[1] == SERVER_END_PACKET): # file empty
                            connEnd = True # connEnd is set to true
                            client_sock.send_ack(data[0])
                            break
                        if second_end: #connection ends with message in buffer
                            connEnd = True
                        if (data[1] == SERVER_END_ABNORMAL): #server shutdown abnormal
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False

                        hash = data[2:].decode(encoding = 'utf-8')

                        client_sock.send_ack(data[0])
                        self.move_window(seq_nos) #move widow forward

                        if len(client_buffer) > 0: #clear buffer and move window forward
                            self.write_buffer(client_buffer, writer)
                            self.move_window(seq_nos)
                            client_buffer.clear()

                    elif (data[0] == seq_nos[1]): #buffer this, don't move the window forward
                        if (data[1] == SERVER_END_PACKET): #connection ended by server with this packet
                            second_end = True
                        if (data[1] == SERVER_END_ABNORMAL): #server shutdown abnormal
                            self._cleanup_abnormal(data[0], hash, writer, client_sock)
                            return False
                        if len(client_buffer)==0: #append only if there isnt any data in buffer. discard packet if repeated
                            client_buffer.append(data[2:]) # add data to buffer
                        client_sock.send_ack(data[0]) # 
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
                        if len(client_buffer)==0: # add to buffer only if buffer empty, else possiblity of duplicates
                            client_buffer.append(data[2:])
                        client_sock.send_ack(data[0])
                        retries = CLIENT_MAX_RETRIES
                        raise ConnectionError # try to get sequence 1 again
                else: #maybe resent data or abnormal closure 
                    if (data[1] == 3):
                        self._cleanup_abnormal(data[0], hash, writer, client_sock)
                        return False
                    # print(data[0], seq_nos)
                    client_sock.send_ack(data[0])
                    retries = CLIENT_MAX_RETRIES
            except ConnectionError:
                retries -= 1

        if (not self.serv_conn_status): # connection to main server lost
            self.request_cleanup(hash, writer)
            del client_sock
            return False
        if connEnd: # connection ended
            self.request_cleanup(hash, writer)
            del client_sock
            return True
        if retries < 0: # retries exceeded
            logger.error(f"Failed P2P connection to {addr}")
            print(f"Failed P2P connection to {addr}")
            del client_sock
            self.request_cleanup(hash, writer, True)
            return False

    def user_input(self):
        '''
        Function to get user input
        '''
        while(not self.client_shutdown): # keep looping to get user input
            file_name, port = input().split(' ')
            if (int(port) == -1):
                self.my_server.set_close()
                self.client_shutdown = True
                return
            if (int(port)==self.my_port):
                print("Requesting from myself...")
                continue
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
    '''
    Class for UDP Client
    '''
    def __init__(self, addr):
        '''
        Constructor for UDP Client class
        param addr : address to send and receive messages from
        '''
        self.clnt_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = addr

    def get_addr(self):
        '''
        Function to get the address the UDP Client object is connected to
        '''
        return self.addr

    def send(self, message):
        '''
        Function to send data to the address that the UDPClient is connected to
        param message : message payload to send to the server
        '''
        self.clnt_socket.sendto(message, self.addr)
        logger.info(f"Sent data: {message} to {self.addr}")

    def send_ack(self, seq_no, end = False):
        '''
        Function to send acknowledgement message for a specific sequence packet and optionally the end communication packet
        param seq_no : sequence number of packet for which ack has to be sent
        param end : whether to send it as an END_CONNECTION_ACK
        '''
        logger.info(f"Sent ACK for seq: {seq_no}")
        data_type = DATA_ACK
        if (end):
            data_type = END_CONNECTION_ACK
        data = int(seq_no).to_bytes(1, "big") + int(data_type).to_bytes(1, "big")
        self.send(data)

    def recv(self):
        '''
        Function to receive data from another client with a set number of retries and a timeout for each receive
        '''
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
    '''
    Class for UDP Server
    '''
    def __init__(self, port, file_mgr):
        '''
        UDP Server Constructor to initialize the server
        param port : the port to run the server on
        param file_mgr : the file manager that the server uses for file operations
        '''
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
        '''
        Function to check whether server creation was a success
        '''
        return self.serv_success

    def set_close(self):
        '''
        Function to set server state to close (accept no more incoming connections)
        '''
        logger.info("Server listen set to close")
        self.init_close = True

    def listen(self):
        '''
        Function for the server to listen at port specified by initialization parameters
        '''
        while True and (not self.init_close) or len(self.clients)>0:
            self.serv_socket.settimeout(SERVER_RECV_TIMEOUT)
            try:
                data, addr = self.serv_socket.recvfrom(SERVER_BUFFER_SIZE)
                with self.clients_lock:
                    if (data[0] == 0 and data[1] == 0): # new client
                        logger.info(f"New connection request from {addr} for file {data[2]}")

                        # accept no more init requests
                        if (self.init_close): 
                            self.clients[addr] = { 'requested_file' : data[2], 'reader' : None, 'status': 'terminate', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr)
                            continue

                        # if client does not have file
                        if (not self.file_mgr.checkFile(data[2])): 
                            logger.error(f"File {data[2]} not found locally")
                            self.clients[addr] = { 'requested_file' : data[2], 'reader' : None, 'status': 'not found', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr) # start a timer for receive
                            self.clients[addr]['timer'].start()
                            self._send_close(addr, 1)
                            continue

                        # initialize the reader object
                        reader = self.file_mgr.newRead(int(data[2]))

                        # initialize bookkeeping for the client
                        self.clients[addr] = { 'requested_file' : data[2], 'reader' : reader, 'window' : {}, 'status': 'active', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}

                        # load window
                        self.load_window(addr, -1) #initialize

                        # send window to client
                        self.send_window(addr)

                        # initialize timer to resend packet in case lost
                        self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                        self.clients[addr]['timer'].start()
                        
                    #if packet is an ack packet
                    elif (data[1] == 1): # this is an ack
                        logger.info(f"Received ACK from {addr} for seq_no: {data[0]}")

                        # server does not know this client, maybe expired connection or it was shutdown
                        if (addr not in self.clients.keys()):
                            if addr not in self.clients.keys():
                                self.clients[addr] = { 'requested_file' : None, 'reader' : None, 'status': 'terminate', 'retries' : SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(1.0, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr)
                            continue

                        # try to get lock to modify shared dictionary
                        with self.clients[addr]['lock']:
                            
                            # reset retries
                            self.clients[addr]['retries'] = SERVER_MAX_RETRIES

                            # cancel timer thread
                            self.clients[addr]['timer'].cancel() 
                            if data[0] not in self.clients[addr]['window'].keys(): #if it is duplicate ack
                                if len(self.clients[addr]['window'].keys()) != 0:
                                    self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                                    self.clients[addr]['timer'].start()
                                continue
                            # flag to do nothing if window has not moved
                            do_nothing = False


                            self.clients[addr]['window'][data[0]][2] = DATA_ACK

                            # if there is more than one packet in window
                            if len(list(self.clients[addr]['window'].keys()))>1: 
                                if data[0] == list(self.clients[addr]['window'].keys())[-2]: #move only
                                    do_nothing = True

                            #move the window only
                            self.send_window(addr, move_only= True)

                            if do_nothing:
                                self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                                self.clients[addr]['timer'].start()
                                continue

                            if (len(self.clients[addr]['window'])==0): #nothing more to send to this client and connection ended
                                del self.clients[addr]
                                continue

                            #send window to client
                            self.send_window(addr)

                            #restart timer
                            self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()


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
        '''
        Function to send closing message to client
        param addr : address to send message to
        param type : type of closing message to send
        '''
        payload = int(0).to_bytes(1, "big") + int(3).to_bytes(1, "big")
        if (type == 1):
            payload = int(0).to_bytes(1, "big") + int(SERVER_FILE_NOT_FOUND).to_bytes(1, "big") # file not found
        self.serv_socket.sendto(payload, addr)
        logger.info(f"Sent {payload} to {addr}")

    def _send_window(self, addr):
        '''
        Low level function to send the current window contents (only packets that have not been acknowledged)
        param addr : address to send the window to
        '''
        # for all the keys in the window
        for i in self.clients[addr]['window'].keys():
            if self.clients[addr]['window'][i][2] == DATA_PACKET:
                seq_no = int(i).to_bytes(1, "big")
                data_type = (self.clients[addr]['window'][i][1]).to_bytes(1, "big")
                data = self.clients[addr]['window'][i][0]

                # prepare payload
                payload = seq_no + data_type + bytes(data)
                self.serv_socket.sendto(payload, addr)
                logger.info(f"Sent data with seq {i}")
                
                # wait some time before sending the next packet
                time.sleep(0.1)

    def send_window(self, addr, move_only = False):
        '''
        High level function to send current window contents and delete already acknowledged window contents
        param addr : address to send the window to
        param move_only : flag to do move only operations and not send operations
        '''
        # if there is a non acknowledged packet before
        delFlag = True
        # if the end packet is in the window
        endFlag = False

        if (len(self.clients[addr]['window'])==0):
            return
        seq_no = list(self.clients[addr]['window'].keys())[-1]
        for i in list(self.clients[addr]['window'].keys()):
            if self.clients[addr]['window'][i][1] == SERVER_END_PACKET:
                endFlag = True
            if self.clients[addr]['window'][i][2] == DATA_ACK and delFlag:
                logger.info(f'deleting {i}')
                del self.clients[addr]['window'][i]
            else:
                delFlag = False
        if not endFlag:
            self.load_window(addr, seq_no)
        if not move_only:
            self._send_window(addr)

    def load_window(self, addr, seq_no):
        '''
        Function to load contents into the window by using the reader assigned to request
        param addr : address of the client
        param seq_no : sequence number of last packet in the window
        '''
        # generate next sequence number
        seq_no = (seq_no + 1)%MAX_SEQ_NO

        while len(self.clients[addr]['window']) < WINDOW_SIZE:
            try:
                # get the next chunk from the reader
                data = next(self.clients[addr]['reader'])
                # add it to the window with the seq_no as key
                self.clients[addr]['window'][seq_no] = [data[0], data[1], DATA_PACKET]

            except StopIteration: # reached the end of the generator
                break
            seq_no = (seq_no + 1)%MAX_SEQ_NO
        
    def _declare_dead(self, addr):
        '''
        Function to declare a client as dead and remove it from the shared dictionary between threads
        param addr : address of the client to be deleted from shared dictionary
        '''
        with self.clients_lock:
            logger.warning(f"Client with address {addr} declared dead.")
            del self.clients[addr]

    def resend(self, *args):
        '''
        Timer function to resend contents of the window to a clients
        param hostname : hostname of the client
        param port : port to reach the client at
        '''
        addr = (args[0],args[1])
        if addr not in self.clients.keys(): # do nothing if client is not in the shared dictionary anymore
            return
        

        if self.clients[addr]['lock'].acquire(False): # if it is not able to acquire this lock immediately, then it must be locked by receiving thread
            logger.warning(f"Resend called for {addr} as no ack received. Retry count: {self.clients[addr]['retries']}")
            lock = self.clients[addr]['lock'] # since we need to release lock after we delete client
            try:
                if (self.clients[addr]['status'] == 'not found'): # file not found case
                    if self.clients[addr]['retries'] < 0: # retries expired
                        logger.info(f"Retries expired for closing request or terminated client {addr}")
                        self._declare_dead(addr)
                        return

                    self.clients[addr]['retries'] -= 1
                    self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                    self.clients[addr]['timer'].start() # restart timer
                    self._send_close(addr, 1)
                    return

                # nothing more to send to the client
                if len(self.clients[addr]['window'])==0:
                    logger.info(f"Nothing more to send to {addr}, declared dead.")
                    self._declare_dead(addr)
                    return

                # if client status is set to terminate
                if (self.clients[addr]['status'] == 'terminate'):
                    if self.clients[addr]['retries'] < 0: # retries expired
                        logger.info(f"Retries expired for closing request or terminated client {addr}")
                        self._declare_dead(addr)
                        return
                    #resend close message
                    self._send_close(addr)
                    self.clients[addr]['retries'] -= 1
                    self.clients[addr]['timer'] = threading.Timer(SERVER_TIMER_THREAD_TIMEOUT, self.resend, (addr))
                    self.clients[addr]['timer'].start() # restart timer
                    return

                # normal client status
                if self.clients[addr]['retries'] < 0: #retries expired
                    self._declare_dead(addr)
                    return
                else:
                    self.clients[addr]['retries'] -= 1
                    self.send_window(addr)
                    self.clients[addr]['timer'] = threading.Timer(1.0, self.resend, (addr))
                    self.clients[addr]['timer'].start() # restart timer
                    return
            finally:
                lock.release()
        else:
            logger.debug("Cancelled timer called.")
        # if the lock is being used by server receive thread then do nothing

    def __del__(self):
        '''
        Destructor for UDP Server class, closes socket if it exists.
        '''
        if self.serv_success:
            self.serv_socket.close()
class ClientFile():
    '''
    Class to handle files of the client
    '''
    def __init__(self, filevector, file_location):
        '''
        Initialize the file handler for the client
        param filevector : filevector to initialize file manager
        param file_location : location to find files of the client
        '''
        self.filedict = {}
        for i in range(len(filevector)):
            if filevector[i] == '1':
                file_i_location = file_location/(str(i)+'.txt')
                # print(file_i_location)
                if not Path(file_i_location).is_file():
                    raise FileNotFoundError
                self.filedict[i] = file_i_location
    
    def checkFile(self, i):
        '''
        Function to check if file exists for the file
        param i : file number in vector
        '''
        if i in self.filedict.keys():
            return True
        return False

    def newRead(self, i):
        '''
        Function to return new read object for a file
        param i : file number in vector
        '''
        return ReadObj(self.filedict[i]).read()

    def newWrite(self, loc):
        '''
        Function to return new write object for a file
        param loc : location to create a file and write to it
        '''
        return WriteObj(loc)

class ReadObj():
    '''
    Class for a file read object
    '''
    def __init__(self, file_location):
        '''
        Constructor for read object class
        param file_location : path of the file to read
        '''
        if (Path(file_location).stat().st_size==0): #empty file
            self.file_hash = None
            return
        self.file_obj = open(file_location, 'rb')
        self.file_hash = bytes(file_hash(file_location), encoding='utf-8') # get hash of the file
        self.file_loc = file_location


    def get_filepath(self):
        '''
        Function to get the file path
        '''
        return self.file_loc

    def read(self):
        '''
        Function to read from a file DATA_PAYLOAD_SIZE bytes at a time
        '''
        # if file is not empty
        if (self.file_hash is not None):
            yield (self.file_hash,DATA_PACKET) # yield file hash first
            while (block:=self.file_obj.read(DATA_PAYLOAD_SIZE)):
                if len(block) < DATA_PAYLOAD_SIZE:
                    yield (block, SERVER_END_PACKET)
                    break
                yield (block, DATA_PACKET)

        else: # yield an empty bytes object
            yield (b'', SERVER_END_PACKET)

    def __del__(self):
        '''
        Destructor for file read object, closes the file after done reading
        '''
        if (self.file_hash is not None):
            self.file_obj.close()

class WriteObj():
    '''
    Class for a file write object. Keeps track of current position
    '''
    def __init__(self, file_location):
        '''
        Constructor of file write object
        param file_location : location of file to write into
        '''
        self.file_obj = open(file_location, 'wb')
        self.file_loc = file_location

    def get_filepath(self):
        '''
        Function to get filepath of file being written
        '''
        return self.file_loc

    def write(self, block):
        '''
        Function to write a block of bytes into the file
        param block : block of bytes to write into the file
        '''
        self.file_obj.write(block)

    def __del__(self):
        '''
        Destructor of file write object, closes file after writing
        '''
        self.file_obj.close()

if __name__ == "__main__":
    # parser = argparse.ArgumentParser(description= "Client ")
    client_no = int(input())
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s", filename = f"./client_logs/log_{client_no}.log" )
    client = Client(f'./configs/clients/{client_no}/{client_no}.yaml')
    # client.send_msg("Hello from Client 1", socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (socket.gethostname(),5000))