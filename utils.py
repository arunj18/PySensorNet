from pathlib import Path
from filehash import FileHash
import logging

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

def file_size(path):
    '''
    Function to get size of file given as path
    path : string or Path object of the path of the file
    '''
    logger.info(f"Get file size of {path}")
    size = None
    if (type(path) == type(Path('./'))):
        size = path.stat().st_size
    elif(type(path) == str):
        size = Path(path).stat().st_size
    else:
        logger.error(f"Unknown type of path = {path}")
    
    logger.debug("Size of file {path} = {size}")
    return size

def file_hash(path):
    '''
    Function to return sha1 hash of a file
    path: string or Path object of the path of the file
    '''
    logger.info(f"Get hash of {path}")
    hash = ''
    sha1hasher = FileHash('sha1')
    hash = sha1hasher.hash_file(path)
    return hash

def verify_hash(hash, path):
    '''
    Function to verify hash of the file
    path: string or Path object of the path of the file
    '''
    logger.info(f"Verify hash of file {path}")
    print(hash==file_hash(path))
    print(hash)
    print(file_hash(path))
    # input()
    if (hash==file_hash(path)):
        return True
    return False
