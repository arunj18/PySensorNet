
import socket
import time
import threading
import logging

import constants

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class MainServerConn():
    def __init__(self, config, server_port = 5000):
        self.serv_port = server_port
        self.main_serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_conn_status(False)
        self.conn_estd = False
        retries = 10
        while(retries):
            try:
                self.main_serv.connect((socket.gethostbyname(socket.gethostname()),self.serv_port))
                self.conn_estd = True
                break
            except ConnectionRefusedError:
                print('retry')
                retries -= 1
                time.sleep(1)
        if not self.conn_estd:
            return
        self.send_init_to_serv(config)
        self.HB_timer = threading.Timer(10.0, self.send_HB)
        self.HB_timer.start()
        self.wait_HB = threading.Lock() # waiting for HB packet response?


    def send_init_to_serv(self, config):
        self.main_serv.sendall(bytes("INIT:"+str(config['CLIENTID'])+":"+str(config['FILE_VECTOR'])+":"+str(config['MYPORT']), encoding ='utf-8'))
        retries = constants.CLIENT_MAIN_SERV_RETRIES
        conn_estd = False
        chunks = []
        while(retries):
            try:
                self.main_serv.settimeout(constants.CLIENT_MAIN_SERV_TIMEOUT)
                success = self.main_serv.recv(4096)
                chunks.append(success)
                print(success.decode('utf-8'))
                if success.decode('utf-8') == "Success!":
                    self.set_conn_status(True)
                    conn_estd = True
                    break 
            except socket.timeout as e:
                print(e)
                retries-=1
        if (conn_estd):
            self.set_conn_status(True)
            print("Got success")
            return

    def request_file(self, file_no):
        with self.wait_HB: #make sure we are not waiting for a HB reply
            if (not self.get_conn_status()): #connection is dead
                return 0, 0
            self.HB_timer.cancel() #cancel HB timer
            self.main_serv.sendall(bytes(f"FILE:{file_no}", encoding = "utf-8"))
            retries = 10
            while retries:
                try:
                    self.main_serv.settimeout(constants.CLIENT_MAIN_SERV_TIMEOUT)
                    resp = self.main_serv.recv(4096)
                    resp = resp.decode('utf-8')
                    try:
                        _, port = resp.split(':')
                        self.HB_timer = threading.Timer(10.0, self.send_HB)
                        self.HB_timer.start()
                        return port
                    except ValueError:
                        print(resp)
                except socket.timeout:
                    retries -= 1
            self.set_close()
            self.set_conn_status(False)
            return -2



    def send_HB(self):
        with self.wait_HB:
            self.main_serv.sendall(bytes("HB", encoding = 'utf-8'))
            logger.info("Sent HB packet")
            self.recv_HB()

    def recv_HB(self):
        retries = 2
        while retries:
            try:
                self.main_serv.settimeout(constants.CLIENT_MAIN_SERV_TIMEOUT)
                HB_resp = self.main_serv.recv(4096)
                if HB_resp.decode('utf-8') == 'HB+':
                    logger.info("received reply to HB")
                    self.HB_timer = threading.Timer(10.0, self.send_HB)
                    self.HB_timer.start()
                    return
            except socket.timeout:
                logger.info("Timed out")
                retries -= 1
        logger.error("No replies to HB message, connection dead to main server")
        self.set_conn_status(False)



    def get_conn_status(self):
        return self.conn_status

    def set_conn_status(self, status):
        self.conn_status = status

    def set_close(self):
        self.main_serv.sendall(b'QUIT')
        self.set_conn_status(False)
        self.HB_timer.cancel()

    def __del__(self):
        # print (self.main_serv)
        if (self.conn_estd):
            self.main_serv.shutdown(1)
            self.main_serv.close()

