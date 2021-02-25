import socket
import logging
import threading

log = logging.getLogger(__name__)
class Server:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = port
        self.s.bind((socket.gethostname(), port))
        log.debug("Createed server socket at localhost with port:" + str(port))
        self.threads = []

    def listen(self,queue_size=5):
        log.debug("Server socket at port " + str(self.port) + " is now listening")
        self.s.listen()
        while True:
            conn, address = self.s.accept()
            log.info(f"Connected to {address}")
            x = threading.Thread(target= self.handle, args = (conn,address,))
            x.start()
            self.threads.append(x)
        
            
    def handle(self,conn,address):
        while True:
                    conn.settimeout(60)
                    data = conn.recv(4096)
                    data = data.decode('utf-8')
                    print(data)
                    if not data:
                        break
                    log.info(f"Received message from {address}")

    def __del__(self):
        # log.debug(f"Client socket closed to {self.clientaddress}")
        # self.s.shutdown(1)
        self.s.close()
        for thread in self.threads:
            thread.join()

if __name__ == "__main__":
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s", filename = "./logs/server.log" )
    server = Server(5000)
    server.listen()