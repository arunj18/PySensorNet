import socket
import logging

log = logging.getLogger(__name__)
class Server:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.port = port
        self.s.bind((socket.gethostname(), port))
        log.debug("Createed server socket at localhost with port:" + str(port))

    def listen(self,queue_size=5):
        log.debug("Server socket at port " + str(self.port) + " is now listening")
        while(True):
            data, address = self.s.recvfrom(4096)
            
            seq_no, type_data = data[:2]
            # print(seq_no, type_data)

            data = data[2:].decode('utf-8')

            log.info(f"Received message from {address} with sequence no {seq_no} and type {type_data}")

            print(seq_no, type_data, data)
            data_ack = bytes([seq_no,1])
            self.s.sendto(data_ack,address)
            
    def __del__(self):
        # log.debug(f"Client socket closed to {self.clientaddress}")
        self.s.close()

if __name__ == "__main__":
    server = Server(5000)
    server.listen()