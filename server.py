import socket
import logging
import threading
import os
import time
from pathlib import Path

from readerwriterlock import rwlock
from inputimeout import inputimeout, TimeoutOccurred

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
        self.init_success = False
        try:
            self.s.bind((socket.gethostname(), port))
            self.init_success = True
        except OSError as e:
            logger.error(e)
            pass
        self.IP = "192.1.1.1"
        self.init_close = False
        logger.debug("Created server socket at localhost with port:" + str(port))

        # List of the files within each client
        self.files = [[] for _ in range(50)]
        # The threads
        self.threads = []
        # Contains all the information about a client
        self.clients = {}
        # Set up the config file with the information
        self.server_config()
        # Set up the locks with reader priority
        self.lock = rwlock.RWLockWrite()
        self.thread_lock = threading.Lock()

    def listen(self, queue_size=5):
        """
        Function to listen on the socket for clients to add or requests to process
        :param self: The server instance
        :param queue_size: How long the queue will be
        :return: N/A
        """
        logger.debug("Server socket at port " + str(self.port) + " is now listening")
        self.s.listen()
        self.timed_thread_killer()
        while True:
            if self.init_close and len(self.clients) == 0:
                return
            self.s.settimeout(1.0)
            try:
                conn, address = self.s.accept()
                logger.info(f"Connected to {address}")
                x = threading.Thread(target=self.handle, args=(conn, address,))
                x.start()
                with self.thread_lock:
                    self.threads.append(x)
            except socket.timeout:
                logger.info("No connection received, continuing to listen")
                continue

    def is_init_success(self):
        """
        Returns if the initialization was successful or not
        :return: A boolean; true if the initialization was a success, false if not
        """
        return self.init_success

    def thread_killer(self):
        """
        Cleans up the threads
        :return: N/A
        """
        with self.thread_lock:
            to_del = []
            # print(self.threads)
            for i in range(len(self.threads)):
                self.threads[i].join(0.0)
                if not (self.threads[i].is_alive()):
                    to_del.append(i)
                # print(self.threads[i].is_alive())
            # print(to_del)
            if len(self.threads) > 0:
                for i in range(len(self.threads) - 1, -1, -1):
                    if i in to_del:
                        del self.threads[i]
                        logger.info(f"Thread {i} killed")
                        # print(f"Thread {i} killed")
        self.timed_thread_killer()

    def timed_thread_killer(self):
        """
        Timer for the thread killer function
        :return: N/A
        """
        if self.init_close:
            return
        self.timed_killer = threading.Timer(10.0, self.thread_killer)
        self.timed_killer.start()

    def handle(self, conn, address):
        """
        Handles the connection request
        :param conn: The connection
        :param address: The IP address of the client that is connecting
        :return: N/A
        """
        # If this is the first time getting data from a client, add it to the clients dict
        conn_estd = False
        retries = 10
        while retries:
            conn.settimeout(10)
            try:
                data = conn.recv(4096)  # 4096 is the size of the buffer
                # print('Server received', repr(data))
                logger.info(f"Received message from {address}")
                logger.info(repr(data))
                if self.init_close:  # user has initiated server close
                    conn.sendall(b"HB-")
                    conn.close()
                    return
                data = data.decode('utf-8')
                # Split the received data and place into an array
                data_array = data.split(':')
                # print(data_array)
                # Extra check to make sure the information is the correct size
                if len(data_array) == 4:
                    # Activate the writer lock
                    with self.lock.gen_wlock():
                        # print(data_array)
                        # print("Processed result: {}".format(data))
                        logger.info("Processed result: {}".format(data))
                        # conn.sendall("-".encode("utf8"))
                        # Remove single quotes from the second and fourth elements
                        data_array[1] = data_array[1].replace("'", "")
                        data_array[3] = data_array[3].replace("'", "")
                        # Single out the client ID
                        client_id = data_array[1]
                        client_info = {"id": data_array[1], "FILE_VECTOR": data_array[2], "PORT": data_array[3]}
                        file_vector = data_array[2]
                        if client_id in self.clients.keys(): # client id already exists, duplicate client
                            logger.error(f"Client {client_id} already exists, ask to delete new connection")
                            conn.sendall(b"HB-")
                            conn.close()
                            return
                        # Add the new client's information into the clients dictionary
                        self.clients.update({client_id: client_info})

                        # A queue for each file
                        for i in range(len(self.files)):
                            if data_array[2][i] == '1':
                                self.files[i].append(data_array[1])
                        # print(self.files)
                        logger.info(self.files)
                        conn.sendall(b"Success!")
                        conn_estd = True
                        break
                else:
                    logger.error(f"Malformed request received")
                    conn.sendall(b"ERR:MALFORM")
            except socket.timeout:
                retries -= 1
        if not conn_estd:
            # print(f"Connection to {address} failed")
            logger.info(f"Connection to {address} failed")
            conn.close() # close connection
            return

        # Go into a loop to listen for other requests
        retries = 10
        while retries >= 0:
            conn.settimeout(20.0)
            try:
                data = conn.recv(4096)  # 4096 is the size of the buffer
                logger.info(f"Received message from {address}")
                data = data.decode('utf-8')
                data_array = data.split(':')
                if "QUIT" in data or len(data) == 0:
                    print("Client is requesting to quit")
                    conn.close()
                    # print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                    logger.info("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                    with self.lock.gen_wlock():
                        del self.clients[client_id]
                        for i in range(len(self.files)):
                            # TODO fix this file_vector logic
                            if file_vector[i] == '1':
                                self.files[i].remove(client_id)
                        # print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                        logger.info("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                        return
                # Client is trying to find a file
                elif self.init_close:
                    conn.sendall(b"HB-")
                    conn.close()
                    with self.lock.gen_wlock():
                        del self.clients[client_id]
                        for i in range(len(self.files)):
                            # TODO fix this file_vector logic
                            if file_vector[i] == '1':
                                self.files[i].remove(client_id)
                        # print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                        logger.info("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                    return
                else:
                    # Make sure the second element is an integer
                    try:
                        # print(data_array)
                        if data_array[0] == "HB":
                            conn.sendall(b'HB+')
                            retries = 10
                            continue
                        elif data_array[0] == 'FILE':
                            with self.lock.gen_rlock():
                                i = int(data_array[1])
                                if i < 0 or i >= 50:
                                    conn.sendall(b"PORT:-1:-1")
                                    retries = 10
                                    continue
                                if len(self.files[i]) == 0:
                                    conn.sendall(b"PORT:-1:-1")
                                    retries = 10
                                    continue
                                else:
                                    port = self.clients[self.files[i][0]]["PORT"]
                                    conn.sendall(bytes(f"PORT:{port}:{self.files[i][0]}", encoding="utf-8"))
                                    retries = 10
                                    continue
                        elif data_array[0] == "LOG":
                            logger.info(f"Request success for file {data_array[1]} from client id {data_array[2]}")
                            conn.sendall(b'LOG:DONE')
                            retries = 10
                            continue
                        else:
                            logger.error(f"Malformed request received")
                            conn.sendall(b"ERR:MALFORM")
                            retries = 10
                            continue

                    except ValueError:
                        # print("Did not receive a correct request. Try again.")
                        pass
            except socket.timeout:
                # print('timedout')
                if self.init_close:  # user has initiated server close
                    conn.sendall(b"HB-")
                    conn.close()
                    with self.lock.gen_wlock():
                        if client_id in self.clients.keys():
                            del self.clients[client_id]
                        for i in range(len(self.files)):
                            # TODO fix this file_vector logic
                            if file_vector[i] == '1':
                                self.files[i].remove(client_id)
                        # print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                        logger.info("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
                    return
                retries -= 1
        logger.error("Retries expired for client {client_id}, shutting off client")
        conn.close()
        with self.lock.gen_wlock():
            del self.clients[client_id]
            for i in range(len(self.files)):
                # TODO fix this file_vector logic
                if file_vector[i] == '1':
                    self.files[i].remove(client_id)
        # print("Connection " + str(self.IP) + ":" + str(self.port) + " closed")
        logger.info("Connection " + str(self.IP) + ":" + str(self.port) + " closed")

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
        try:
            self.timed_killer.cancel()
        except:
            pass
        self.init_close = True
        self.thread_killer()

    def user_input(self):
        """
        Gets the user input; if the input is "-1", then the server shuts down
        :return: N/A
        """
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            try:
                num = inputimeout(prompt = f"Number of active clients: {len(self.clients)}\nEnter -1 to init server exit\n>>", timeout = 10.0).strip()
                try:
                    if (int(num) == -1):
                        self.init_close = True
                        logger.info("Server exiting due to user input")
                        print("Server shutting down")
                        break
                except Exception:
                    time.sleep(10.0)
                    print("Invalid input")
                    pass
            except TimeoutOccurred:
                continue


def main():
    Path('./logs/').mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s",
                        filename=f"./logs/server.log")
    server = Server(5000)

    if not server.is_init_success():
        print("Server could not be initialized, check logs for errors. Exiting...")
        logger.error("Server init failed..")
        del server
        return
    server_thread = threading.Thread(target=server.listen)
    print("Hello! The server is starting up...\n")
    server_thread.start()
    server.user_input()
    logger.info("User input thread joined")
    server_thread.join()
    logger.info("Server thread joined")
    del server


if __name__ == "__main__":
    main()
