import socket

class Server:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind((socket.gethostname(), port))
    
    def listen(self,queue_size=5):
        self.s.listen(queue_size)
        while(True):
            clientsocket, address = self.s.accept()
            print(f"Connection established from {address}!")
            clientsocket.send(bytes("Connected to server!",'utf-8'))
            clientsocket.close()

class Client:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

    def connect(self,port):
        self.s.connect((socket.gethostname(),port))

    def get_msg(self,bytes_recv = 1024):
        msg = self.s.recv(bytes_recv)
        msg.decode("utf-8")
        return msg