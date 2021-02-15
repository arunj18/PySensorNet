import socket
import argparse
import json
from utils import file_hash

class Client(object):
    def __init__(self, config_file_path):
        # reach out to server to share config
        # self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.serv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.file_vector = '00000000000000000000000'
        self.config = {'FILE_VECTOR': self.file_vector, 'PORT': 4200}

        self._send_init_to_serv()

        # then start listening on port

        # open user input

    def _get_hash_of_files(self):
        pass


    def _send_init_to_serv(self):
        INIT_MSG = "INIT!"+json.dumps(self.config)
        file_hashes = self._get_hash_of_files()
        send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_msg(INIT_MSG, send_socket, (socket.gethostname(),5000))

    def send_msg(self, msg, sock, address):
        '''
        High level data sending
        '''
        msg = bytes(msg,'utf-8')
        if len(msg)<4094: #message is too long, determine number of splits
            while True:
                try:
                    self._send_msg(msg, sock, address, 0, 0)
                    sock.settimeout(10.0)
                    data_ack, address =  sock.recvfrom(4096)
                    # print(data_ack[0]==0, data_ack[1]==1)
                    if (data_ack[0]==0, data_ack[1]==1): #got ack for the message we sent
                        break
                except socket.timeout:
                    pass


    def _send_msg(self, msg, sock, address, sequence_no, type_msg):
        data = sequence_no.to_bytes(1, 'big') + type_msg.to_bytes(1, 'big') + msg
        sock.sendto(data,address)

    def get_msg(self, sock, bytes_recv = 4096):

        msg, address = sock.recvfrom(bytes_recv)
        return msg, address


if __name__ == "__main__":
    # parser = argparse.ArgumentParser(description= "Client ")
    client = Client(None)
    # client.send_msg("Hello from Client 1", socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (socket.gethostname(),5000))