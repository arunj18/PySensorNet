import socket
import logging

log = logging.getLogger(__name__)
class Server:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = port
        self.s.bind((socket.gethostname(), port))
        log.debug("Createed server socket at localhost with port:" + str(port))
    def listen(self,queue_size=5):
        self.s.listen(queue_size)
        self.queue_size = queue_size
        log.debug("Server socket at port " + str(self.port) + " is now listening with queue size: " + str(self.queue_size))
        while(True):
            clientsocket, address = self.s.accept()
            self.clientsocket = clientsocket
            self.clientaddress = address

            log.info(f"Connection established from {address}.")

            sent = clientsocket.send(bytes("Connected to server!",'utf-8'))
            log.info(f"{sent} bytes of data to {address} through port: {self.port}")
    def __del__(self):
        self.clientsocket.close()
        log.debug(f"Client socket closed to {self.clientaddress}")
class Client:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

    def connect(self,port):
        self.s.connect((socket.gethostname(),port))

    def get_msg(self,bytes_recv = 1024):
        msg = self.s.recv(bytes_recv)
        msg.decode("utf-8")
        return msg