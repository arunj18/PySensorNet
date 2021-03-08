import socket
import logging
import threading
from readerwriterlock import rwlock

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
        self.port = port
        self.hostname = "Server"
        self.s.bind((socket.gethostname(), port))
        self.IP = "192.1.1.1"
        log.debug("Created server socket at localhost with port:" + str(port))
        self.threads = []
        self.clients = {}
        # Set up the config file with the information
        self.server_config()
        # Set up the locks with reader priority
        a = rwlock.RWLockRead()
        self.reader_lock = a.gen_rlock()
        self.writer_lock = a.gen_wlock()

    def listen(self, queue_size=5):
        """
        Function to listen on the socket for clients to add or requests to process
        :param self: The server instance
        :param queue_size: How long the queue will be
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

    def handle(self, conn, address):
        """
        Handles the connection request
        :param conn: The connection
        :param address: The IP address of the client that is connecting
        :return: N/A
        """

        # If this is the first time getting data from a client, add it to the clients dict
        conn.settimeout(60)
        data = conn.recv(4096)  # 4096 is the size of the buffer
        print('Server received', repr(data))
        log.info(f"Received message from {address}")

        data = data.decode('utf-8')
        # Split the received data and place into an array
        data_array = data.split()

        # Extra check to make sure the information is the correct size
        if len(data_array) == 8:
            # Activate the writer lock
            with self.writer_lock:
                print("Processed result: {}".format(data))
                conn.sendall("-".encode("utf8"))
                # Remove single quotes from the second and fourth elements
                data_array[2].replace("'", "")
                data_array[4].replace("'", "")
                # Single out the client ID
                client_id = data_array[2]
                # Add the new client's information into the clients dictionary
                self.clients.update({client_id: data_array})

        # Go into a loop to listen for other requests
        while True:
            conn.settimeout(60)
            data = conn.recv(4096)  # 4096 is the size of the buffer
            print('Server received', repr(data))
            log.info(f"Received message from {address}")

            data = data.decode('utf-8')
            # Split the received data and place into an array
            data_array = data.split()

            if "QUIT" in data:
                print("Client is requesting to quit")
                conn.close()
                print("Connection " + self.IP + ":" + self.port + " closed")
            # Client is trying to find a file
            else:
                # Make sure the second element is an integer
                try:
                    i = int(data_array[2])
                    # Activate the reader lock
                    with self.reader_lock:
                        for client in self.clients:
                            file_vector = self.clients[client][4]
                            list(map(int, file_vector))

                except ValueError:
                    print("Did not receive a correct request. Try again.")


    def server_config(self):
        """
        Sets up the server config file
        :return: N/A
        """
        s_config_file = open("configs/server.txt", "w+")
        s_config_file.write("Hostname: " + self.hostname + "\n")
        s_config_file.write("IP: " + self.IP + "\n")
        s_config_file.write("Port_number: " + str(self.port) + "\n")
        s_config_file.close()

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
    server = Server(6400)
    server.listen()
