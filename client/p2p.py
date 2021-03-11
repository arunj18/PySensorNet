import socket
import logging
import threading
import time


import constants




logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)





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
        data_type = constants.DATA_ACK
        if (end):
            data_type = constants.END_CONNECTION_ACK
        data = int(seq_no).to_bytes(1, "big") + int(data_type).to_bytes(1, "big")
        self.send(data)

    def recv(self):
        '''
        Function to receive data from another client with a set number of retries and a timeout for each receive
        '''
        self.clnt_socket.settimeout(constants.CLIENT_RECV_TIMEOUT)
        retries = constants.CLIENT_MAX_RETRIES
        while(retries>=0):
            try:
                data, address = self.clnt_socket.recvfrom(constants.CLIENT_BUFFER_SIZE)
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
            self.serv_socket.settimeout(constants.SERVER_RECV_TIMEOUT)
            try:
                data, addr = self.serv_socket.recvfrom(constants.SERVER_BUFFER_SIZE)
                with self.clients_lock:
                    if (data[0] == 0 and data[1] == 0): # new client
                        logger.info(f"New connection request from {addr} for file {data[2]}")

                        # accept no more init requests
                        if (self.init_close): 
                            self.clients[addr] = { 'requested_file' : data[2], 'reader' : None, 'status': 'terminate', 'retries' : constants.SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr)
                            continue

                        # if client does not have file
                        if (not self.file_mgr.checkFile(data[2])): 
                            logger.error(f"File {data[2]} not found locally")
                            self.clients[addr] = { 'requested_file' : data[2], 'reader' : None, 'status': 'not found', 'retries' : constants.SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr) # start a timer for receive
                            self.clients[addr]['timer'].start()
                            self._send_close(addr, 1)
                            continue

                        # initialize the reader object
                        reader = self.file_mgr.newRead(int(data[2]))

                        # initialize bookkeeping for the client
                        self.clients[addr] = { 'requested_file' : data[2], 'reader' : reader, 'window' : {}, 'status': 'active', 'retries' : constants.SERVER_MAX_RETRIES, 'lock': threading.Lock()}

                        # load window
                        self.load_window(addr, -1) #initialize

                        # send window to client
                        self.send_window(addr)

                        # initialize timer to resend packet in case lost
                        self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                        self.clients[addr]['timer'].start()
                        
                    #if packet is an ack packet
                    elif (data[1] == 1): # this is an ack
                        logger.info(f"Received ACK from {addr} for seq_no: {data[0]}")

                        # server does not know this client, maybe expired connection or it was shutdown
                        if (addr not in self.clients.keys()):
                            if addr not in self.clients.keys():
                                self.clients[addr] = { 'requested_file' : None, 'reader' : None, 'status': 'terminate', 'retries' : constants.SERVER_MAX_RETRIES, 'lock': threading.Lock()}
                            self.clients[addr]['timer'] = threading.Timer(1.0, self.resend, addr)
                            self.clients[addr]['timer'].start()
                            self._send_close(addr)
                            continue

                        # try to get lock to modify shared dictionary
                        with self.clients[addr]['lock']:
                            
                            # reset retries
                            self.clients[addr]['retries'] = constants.SERVER_MAX_RETRIES

                            # cancel timer thread
                            self.clients[addr]['timer'].cancel() 
                            if data[0] not in self.clients[addr]['window'].keys(): #if it is duplicate ack
                                if len(self.clients[addr]['window'].keys()) != 0:
                                    self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                                    self.clients[addr]['timer'].start()
                                continue
                            # flag to do nothing if window has not moved
                            do_nothing = False


                            self.clients[addr]['window'][data[0]][2] = constants.DATA_ACK

                            # if there is more than one packet in window
                            if len(list(self.clients[addr]['window'].keys()))>1: 
                                if data[0] == list(self.clients[addr]['window'].keys())[-2]: #move only
                                    do_nothing = True

                            #move the window only
                            self.send_window(addr, move_only= True)

                            if do_nothing:
                                self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                                self.clients[addr]['timer'].start()
                                continue

                            if (len(self.clients[addr]['window'])==0): #nothing more to send to this client and connection ended
                                del self.clients[addr]
                                continue

                            #send window to client
                            self.send_window(addr)

                            #restart timer
                            self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
                            self.clients[addr]['timer'].start()


                    elif (data[1] == constants.END_CONNECTION_ACK): #user shutdown close ack
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
        payload = int(0).to_bytes(1, "big") + int(constants.SERVER_END_ABNORMAL).to_bytes(1, "big")
        if (type == 1):
            payload = int(0).to_bytes(1, "big") + int(constants.SERVER_FILE_NOT_FOUND).to_bytes(1, "big") # file not found
        self.serv_socket.sendto(payload, addr)
        logger.info(f"Sent {payload} to {addr}")

    def _send_window(self, addr):
        '''
        Low level function to send the current window contents (only packets that have not been acknowledged)
        param addr : address to send the window to
        '''
        # for all the keys in the window
        for i in self.clients[addr]['window'].keys():
            if self.clients[addr]['window'][i][2] == constants.DATA_PACKET:
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
            if self.clients[addr]['window'][i][1] == constants.SERVER_END_PACKET:
                endFlag = True
            if self.clients[addr]['window'][i][2] == constants.DATA_ACK and delFlag:
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
        seq_no = (seq_no + 1)%(constants.MAX_SEQ_NO)

        while len(self.clients[addr]['window']) < constants.WINDOW_SIZE:
            try:
                # get the next chunk from the reader
                data = next(self.clients[addr]['reader'])
                # add it to the window with the seq_no as key
                self.clients[addr]['window'][seq_no] = [data[0], data[1], constants.DATA_PACKET]

            except StopIteration: # reached the end of the generator
                break
            seq_no = (seq_no + 1)%(constants.MAX_SEQ_NO)
        
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
                    self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, addr)
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
                    self.clients[addr]['timer'] = threading.Timer(constants.SERVER_TIMER_THREAD_TIMEOUT, self.resend, (addr))
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