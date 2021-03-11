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

        self.files = [[] for _ in range(50)]  # TODO #1 keep client ids by time of insertion into list # CHANGE

        self.threads = []
        self.clients = {}
        # Set up the config file with the information
        self.server_config()
        # Set up the locks with reader priority
        self.lock = rwlock.RWLockWrite()  # CHANGE
        self.thread_lock = threading.Lock()

    def listen(self, queue_size=5):
        """
        Function to listen on the socket for clients to add or requests to process
        :param self: The server instance
        :param queue_size: How long the queue will be
        :return: N/A
        """
        log.debug("Server socket at port " + str(self.port) + " is now listening")
        self.s.listen()
        self.timed_thread_killer()
        while True:
            conn, address = self.s.accept()
            log.info(f"Connected to {address}")
            print(f"Server connected to {address}")
            x = threading.Thread(target=self.handle, args=(conn, address,))
            x.start()
            with self.thread_lock:
                self.threads.append(x)

    def thread_killer(self):
        with self.thread_lock:
            to_del = []
            print(self.threads)
            for i in range(len(self.threads)):
                self.threads[i].join(0.0)
                if not (self.threads[i].is_alive()):
                    to_del.append(i)
                print(self.threads[i].is_alive())
            print(to_del)
            if len(self.threads) > 0:
                for i in range(len(self.threads) - 1, -1, -1):
                    if i in to_del:
                        del self.threads[i]
                        print(f"Thread {i} killed")
        self.timed_thread_killer()

    def timed_thread_killer(self):
        self.timed_killer = threading.Timer(10.0, self.thread_killer)
        self.timed_killer.start()

    def handle(self, conn, address):
        """
        Handles the connection request
        :param conn: The connection
        :param address: The IP address of the client that is connecting
        :return: N/A
        """
        # with self.lock.gen_wlock(): # get a write lock  # CHANGE
        # If this is the first time getting data from a client, add it to the clients dict
        # !!! CHANGES MADE HERE !!!
        conn_estd = False
        retries = 10
        while retries:
            conn.settimeout(10)
            try:
                data = conn.recv(4096)  # 4096 is the size of the buffer
                print('Server received', repr(data))
                log.info(f"Received message from {address}")

                data = data.decode('utf-8')
                # Split the received data and place into an array
                data_array = data.split(':')
                print(data_array)
                # Extra check to make sure the information is the correct size
                if len(data_array) == 4:
                    # Activate the writer lock
                    with self.lock.gen_wlock():
                        print(data_array)
                        # input()
                        print("Processed result: {}".format(data))
                        # conn.sendall("-".encode("utf8"))
                        # Remove single quotes frteom the second and fourth elements
                        data_array[1] = data_array[1].replace("'", "")
                        data_array[3] = data_array[3].replace("'", "")
                        # Single out the client ID
                        client_id = data_array[1]
                        client_info = {"id": data_array[1], "FILE_VECTOR": data_array[2], "PORT": data_array[3]}
                        file_vector = data_array[2]
                        # Add the new client's information into the clients dictionary
                        self.clients.update({client_id: client_info})

                        # TODO some sort of queue for each file 
                        for i in range(len(self.files)):
                            if data_array[2][i] == '1':
                                self.files[i].append(data_array[1])
                        print(self.files)
                        conn.sendall(b"Success!")
                        conn_estd = True
                        # input()
                        break
            except socket.timeout:
                retries -= 1
        if not conn_estd:
            print(f"Connection to {address} failed")
            return

        # !!! CHANGES MADE HERE!!!
        # Go into a loop to listen for other requests
        while True:
            conn.settimeout(10)
            try:
                data = conn.recv(4096)  # 4096 is the size of the buffer
                # print('Server received', repr(data))
                log.info(f"Received message from {address}")

                data = data.decode('utf-8')
                if not data:
                    print(data)
                # input()
                # Split the received data and place into an array
                data_array = data.split()
                # input()
                if "QUIT" in data:
                    print("Client is requesting to quit")
                    conn.close()
                    print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                    with self.lock.gen_wlock():
                        for i in range(len(self.files)):
                            # TODO fix this file_vector logic
                            if file_vector[i] == '1':
                                self.files[i].remove(client_id)
                        print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                        return
                # Client is trying to find a file
                else:
                    # Make sure the second element is an integer
                    try:
                        i = int(data_array[1])
                        clients_with_file = []
                        # Check if there are any clients with the number the client is looking for
                        for client in self.clients:
                            file_vector = self.clients[client][3]
                            if str(file_vector[i]) == str(1):
                                my_client_id = self.clients[client][1]
                                clients_with_file.append(my_client_id)
                        # Make sure there are clients with the file
                        if len(clients_with_file) != 0:
                            # Activate the reader lock
                            with self.lock.gen_rlock():
                                my_client = bytes([clients_with_file[0]])
                                # Not sure if this is how you should send it...
                                # Send the number of the client that has
                                s = socket.socket()  # Create a socket object
                                s.connect((conn, address))  # connect with the server
                                s.send(my_client)  # communicate with the server

                            # Listen for the confirmation that the transfer is complete
                            complete = False
                            while not complete:
                                conn.settimeout(60)
                                data = conn.recv(4096)  # 4096 is the size of the buffer
                                print('Server received', repr(data))
                                log.info(f"Received message from {address}")
                        # Send that there are no clients with the file
                        else:
                            s = socket.socket()  # Create a socket object
                            s.connect((conn, address))  # connect with the server
                            s.send(b'0')  # communicate with the server
                    except ValueError:
                        print("Did not receive a correct request. Try again.")
                # time.sleep(2)
            except socket.timeout:
                print('timedout')

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
        self.timed_killer.cancel()
        for thread in self.threads:
            thread.join()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s",
                        filename="./logs/server.log")
    server = Server(5000)
    server.listen()

    print("Hello! The server is starting up...\n")
