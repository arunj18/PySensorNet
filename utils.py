from pathlib import Path
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