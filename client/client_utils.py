import socket
import logging
import constants
from utils.utils import file_hash
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ClientFile():
    '''
    Class to handle files of the client
    '''
    def __init__(self, filevector, file_location):
        '''
        Initialize the file handler for the client
        param filevector : filevector to initialize file manager
        param file_location : location to find files of the client
        '''
        self.filedict = {}
        for i in range(len(filevector)):
            if filevector[i] == '1':
                file_i_location = file_location/(str(i)+'.txt')
                # print(file_i_location)
                if not Path(file_i_location).is_file():
                    raise FileNotFoundError
                self.filedict[i] = file_i_location
    def checkFile(self, i):
        '''
        Function to check if file exists for the file
        param i : file number in vector
        '''
        if i in self.filedict.keys():
            return True
        return False

    def newRead(self, i):
        '''
        Function to return new read object for a file
        param i : file number in vector
        '''
        return ReadObj(self.filedict[i]).read()

    def newWrite(self, loc):
        '''
        Function to return new write object for a file
        param loc : location to create a file and write to it
        '''
        return WriteObj(loc)

class ReadObj():
    '''
    Class for a file read object
    '''
    def __init__(self, file_location):
        '''
        Constructor for read object class
        param file_location : path of the file to read
        '''
        if (Path(file_location).stat().st_size==0): #empty file
            self.file_hash = None
            return
        self.file_obj = open(file_location, 'rb')
        self.file_hash = bytes(file_hash(file_location), encoding='utf-8') # get hash of the file
        self.file_loc = file_location


    def get_filepath(self):
        '''
        Function to get the file path
        '''
        return self.file_loc

    def read(self):
        '''
        Function to read from a file DATA_PAYLOAD_SIZE bytes at a time
        '''
        # if file is not empty
        if (self.file_hash is not None):
            yield (self.file_hash, constants.DATA_PACKET) # yield file hash first
            while (block:=self.file_obj.read(constants.DATA_PAYLOAD_SIZE)):
                if len(block) < constants.DATA_PAYLOAD_SIZE:
                    yield (block, constants.SERVER_END_PACKET)
                    break
                yield (block, constants.DATA_PACKET)

        else: # yield an empty bytes object
            yield (b'', constants.SERVER_END_PACKET)

    def __del__(self):
        '''
        Destructor for file read object, closes the file after done reading
        '''
        if (self.file_hash is not None):
            self.file_obj.close()

class WriteObj():
    '''
    Class for a file write object. Keeps track of current position
    '''
    def __init__(self, file_location):
        '''
        Constructor of file write object
        param file_location : location of file to write into
        '''
        self.file_obj = open(file_location, 'wb', 0)
        self.file_loc = file_location

    def get_filepath(self):
        '''
        Function to get filepath of file being written
        '''
        return self.file_loc

    def write(self, block):
        '''
        Function to write a block of bytes into the file
        param block : block of bytes to write into the file
        '''
        self.file_obj.write(block)

    def __del__(self):
        '''
        Destructor of file write object, closes file after writing
        '''
        self.file_obj.close()
