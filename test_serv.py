from base import Server
import logging

if __name__== "__main__":
    serv = Server(1234)
    serv.listen()