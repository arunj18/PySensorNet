
import socket
import time
import threading
import logging

import constants

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MainServerConn():
    def __init__(self, config, server_port=5000):
        '''
        Constructor for main server connection class
        This class handles connection to the main server
        '''
        self.serv_port = server_port
        self.main_serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_conn_status(False)
        self.conn_estd = False
        retries = 10
        while(retries):
            try:
                self.main_serv.connect(
                    (socket.gethostbyname(socket.gethostname()),
                        self.serv_port))
                self.conn_estd = True
                break
            except ConnectionRefusedError:
                print('retry')
                retries -= 1
                time.sleep(1)
        if not self.conn_estd:
            return

        # send init to server
        self.send_init_to_serv(config)

        # a timer to send heartbeat packets
        self.HB_timer = threading.Timer(10.0, self.send_HB)

        # waiting for HB packet response?
        self.wait_HB = threading.Lock()
        self.HB_timer.start()

    def send_init_to_serv(self, config):
        '''
        Function to send init and handle init to server
        param config : config dictionary with information about client.
                       Keys are CLIENTID, FILE_VECTOR, MYPORT
        '''
        self.main_serv.sendall(bytes("INIT:"+str(config['CLIENTID'])
                                     + ":" + str(config['FILE_VECTOR'])
                                     + ":" + str(config['MYPORT']),
                                     encoding='utf-8'))  # send info to server
        # how many retries to receive back success message
        retries = constants.CLIENT_MAIN_SERV_RETRIES
        conn_estd = False
        while retries >= 0:
            try:
                self.main_serv.settimeout(constants.CLIENT_MAIN_SERV_TIMEOUT)
                success = self.main_serv.recv(4096)
                # client init was a success
                if success.decode('utf-8') == "Success!":
                    conn_estd = True
                    break
                # server asked to close connection, duplicate client
                elif success.decode('utf-8') == 'HB-':
                    conn_estd = False
                    logger.error("Received server close from main server,"
                                 " init fail. (Duplicate client)")
                    break
                # malformed request received by server
                elif success.decode('utf-8') == "ERR:MALFORM":
                    conn_estd = False
                    logger.error("Server received malformed request."
                                 " init fail.")
                    break
                else:  # got an unknown message from server
                    msg = success.decode("utf-8")
                    logger.error(f"Unknown message received {msg}")
                    if len(msg) == 0:
                        conn_estd = False
                        logger.error("Connection closed")
                        break

            except socket.timeout:  # socket time out
                retries -= 1
        if (conn_estd):
            self.set_conn_status(True)
            print("Got success")
            return

    def request_file(self, file_no):
        '''
        Function to request a file from the main server
        param file_no : number of the file to retrieve
        '''
        # make sure we are not waiting for a HB reply
        with self.wait_HB:
            if (not self.get_conn_status()):  # connection is dead
                return 0, -1
            self.HB_timer.cancel()  # cancel HB timer
            # send request to server
            self.main_serv.sendall(bytes(f"FILE:{file_no}",
                                         encoding="utf-8"))
            retries = constants.CLIENT_MAIN_SERV_RETRIES
            while retries >= 0:
                try:
                    self.main_serv.settimeout(
                        constants.CLIENT_MAIN_SERV_TIMEOUT)

                    resp = self.main_serv.recv(4096)
                    resp = resp.decode('utf-8')
                    try:
                        _, port, client_id = resp.split(':')
                        self.HB_timer = threading.Timer(10.0, self.send_HB)
                        self.HB_timer.start()
                        return port, client_id
                    except ValueError:
                        if resp == 'HB-' or len(resp) == 0:
                            logger.info("server shutting down, client shutdown"
                                        " initiated")
                            self.set_conn_status(False)
                            return -2, -1
                        else:
                            logger.error("Unknown response received.")
                            return -1, -1
                except socket.timeout:
                    retries -= 1
            logger.info("server connection broken, client shutdown initiated")
            self.set_close()
            self.set_conn_status(False)
            return -2, -1

    def send_success(self, file_no, client_id):
        '''
        Function to send success log message to main server
        param file_no : file number of the successful request
        param client_id : client id of the successful request
        '''
        with self.wait_HB:
            if (not self.get_conn_status()):  # connection is dead
                return -1
            self.HB_timer.cancel()  # cancel HB timer
            self.main_serv.sendall(bytes(f"LOG:{file_no}:{client_id}",
                                         encoding="utf-8"))
            retries = constants.CLIENT_MAIN_SERV_RETRIES
            while retries >= 0:
                try:
                    self.main_serv.settimeout(
                        constants.CLIENT_MAIN_SERV_TIMEOUT)
                    resp = self.main_serv.recv(4096)
                    resp = resp.decode('utf-8')
                    try:
                        _, success = resp.split(':')
                        if success == 'DONE':
                            logger.info("Success message acknowledged by main"
                                        " server")
                            self.HB_timer = threading.Timer(10.0, self.send_HB)
                            self.HB_timer.start()
                            return 0
                        else:
                            logger.error("Unknown message received from main"
                                         " server")
                            print("Unknown message received from main server")
                            self.HB_timer = threading.Timer(10.0, self.send_HB)
                            self.HB_timer.start()
                            return 0

                    except ValueError:
                        if resp == 'HB-' or len(resp) == 0:
                            logger.info("server shutting down, client shutdown"
                                        " initiated")
                            self.set_conn_status(False)
                            return -2

                except socket.timeout:
                    retries -= 1

            logger.info("server connection broken, client shutdown initiated")
            self.set_close()
            self.set_conn_status(False)
            return -1

    def send_HB(self):
        '''
        Function to send HeartBeat packets to the main server
        '''
        with self.wait_HB:
            self.main_serv.sendall(bytes("HB",
                                         encoding='utf-8'))
            logger.info("Sent HB packet")
            self.recv_HB()

    def recv_HB(self):
        '''
        Function to receive HeartBeat packets from main server
        '''
        retries = constants.CLIENT_MAIN_SERV_HB_RETRIES
        while retries >= 0:
            try:
                self.main_serv.settimeout(constants.CLIENT_MAIN_SERV_TIMEOUT)
                HB_resp = self.main_serv.recv(4096)
                if HB_resp.decode('utf-8') == 'HB+':
                    logger.info("received reply to HB")
                    self.HB_timer = threading.Timer(10.0, self.send_HB)
                    self.HB_timer.start()
                    return
                elif HB_resp.decode('utf-8') == 'HB-':
                    logger.info("server shutting down, client shutdown"
                                " initiated")
                    self.set_conn_status(False)
                    return
                if len(HB_resp) == 0:
                    logger.error("Empty reply from server, connection closed.")
                    self.set_conn_status(False)
                    return
                else:
                    logger.error("Unknown message received from server."
                                 " Exiting")
                    self.set_conn_status(False)
                    return
            except socket.timeout:
                logger.info("Timed out")
                retries = retries - 1

        logger.error("No replies to HB message, "
                     "connection dead to main server")
        self.set_conn_status(False)

    def get_conn_status(self):
        '''
        Function to get current connection status
        '''
        return self.conn_status

    def set_conn_status(self, status):
        '''
        Function to set connection status
        param status: boolean status to set
        '''
        self.conn_status = status

    def set_close(self):
        '''
        Function to close server connection
        '''
        self.main_serv.sendall(b'QUIT')
        self.set_conn_status(False)
        self.HB_timer.cancel()

    def __del__(self):
        '''
        Desctructor of main server class
        '''

        if (self.conn_estd):
            try:
                self.main_serv.shutdown(1)
                self.main_serv.close()
            except Exception:
                pass
