import socket
import sys
import traceback
import logging
import threading

log = logging.getLogger(__name__)


class Server:
    """
    The server class
    Some socket code comes from https://www.tutorialspoint.com/socket-programming-with-multi-threading-in-python
    """

    def __init__(self, port):
        """
        Constructor for the server class
        :param self: The server instance
        :param port: The port number
        :return: N/A
        """
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.s.bind((self.s.gethostname(), port))
        except:
            print("Bind failed. Error : " + str(sys.exc_info()))
            log.debug("Bind failed. Error : " + str(sys.exc_info()))
            sys.exit()

        log.debug("Created server socket at localhost with port:" + str(port))
        self.port = port
        self.hostname = socket.gethostname()
        self.IP = socket.gethostbyname(self.hostname)
        self.threads = []
        self.clients = {}
        # Set up the config file with the information
        self.server_config()

    def listen(self):
        """
        Function to listen on the socket for clients to add or requests to process
        :param self: The server instance
        :return: N/A
        """
        log.debug("Server socket at port " + str(self.port) + " is now listening")
        self.s.listen()
        while True:
            conn, address = self.s.accept()
            log.info(f"Connected to {address}")
            x = threading.Thread(target=self.handle, args=(conn, address,))
            x.start()
            self.threads.append(x)
            # TODO: need to get the name and config location from (x?) Should I use x.getName()?

    def handle(self, conn, address):
        """
        Handles the connection request
        :param conn: The connection
        :param address: The IP address of the client that is connecting
        :return: N/A
        """
        while True:
            conn.settimeout(60)
            data = conn.recv(4096)
            data = data.decode('utf-8')
            print(data)
            if not data:
                break
            log.info(f"Received message from {address}")

            client_input = self.receive_input(conn)
            if "--QUIT--" in client_input:
                print("Client is requesting to quit")
                conn.close()
                print("Connection " + self.IP + ":" + self.port + " closed")
                is_active = False
            else:
                print("Processed result: {}".format(client_input))
                conn.sendall("-".encode("utf8"))

    def receive_input(self, conn, max_buffer_size=4096):
        client_input = conn.recv(max_buffer_size)
        client_input_size = sys.getsizeof(client_input)
        if client_input_size > max_buffer_size:
            print("The input size is greater than expected {}".format(client_input_size))
        decoded_input = client_input.decode("utf8").rstrip()
        result = self.process_input(decoded_input)
        return result

    def process_input(self, connection, address, input_str):
        print(f"Processing the input received from {address}")

    def server_config(self):
        """
        Sets up the server config file
        :return: N/A
        """
        server_config = open("../configs/server.txt", "w+")
        server_config.write("Hostname: " + self.hostname + "\n")
        server_config.write("IP: " + self.IP + "\n")
        server_config.write("Port_number: " + self.port + "\n")
        server_config.close()

    def __del__(self):
        """
        Closes the connection and threads for the server instance
        :return: N/A
        """
        # log.debug(f"Client socket closed to {self.clientaddress}")
        # self.s.shutdown(1)
        self.s.close()
        for thread in self.threads:
            thread.join()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s",
                        filename="./logs/server.log")
    server = Server(5000)
    server.listen()
