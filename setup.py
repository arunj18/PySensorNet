import random
import string
from pathlib import Path
import logging
import yaml
from shutil import copy


from utils import file_size

# Get or creates a logger
logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

def create_dirs(path_hier):
    '''
    Function to create path given as string
    path_hier : path to create
    '''
    parent = Path(path_hier)
    parent.mkdir(parents = True, exist_ok = True)
    logger.info("Created directories if they didn't exist at {0}".format(path_hier))
    return parent

def client_config_generator(files_location):
    '''
    Function to generate client configs
    '''
    parent = create_dirs("./configs/clients/")

    for file_idx in range(100): #create 100 client configs
        name = str(file_idx + 1)
        fn = name + ".yaml"
        # new_file = parent / fn
        new_parent = create_dirs(str(parent / name))
        new_file = new_parent / fn
        # print(new_file)
        client_dict = {}

        client_dict['CLIENTID'] = str(name) 

        client_dict['SERVERPORT'] = 5000
        client_dict['MYPORT'] = random.choice([n for n in range(1024,49151) if n!= 5000])
        client_dict['FILE_VECTOR'] = ''.join([str(random.choice([0,1])) for x in range(50)])

        if client_dict['FILE_VECTOR'] == "0"*50:
            logger.debug(f"FILE_VECTOR for name was all 0s,")
            client_dict['FILE_VECTOR'] = list(client_dict['FILE_VECTOR'])
            client_dict['FILE_VECTOR'][random.choice(range(50))] = '1'
            client_dict['FILE_VECTOR'] = ''.join(client_dict['FILE_VECTOR'])

        file_folder_path = Path(files_location)

        for idx in range(len(client_dict['FILE_VECTOR'])):
            if client_dict['FILE_VECTOR'][idx] == '1':
                filename = str(idx) + '.txt'
                file_1 = file_folder_path / filename
                # print(file_1, new_parent/filename)
                copy(file_1, new_parent/filename)


        with new_file.open('w') as f:
            yaml.dump(client_dict,f)
    
            logger.info(f"Client created with CLIENTID: {client_dict['CLIENTID']}")
            logger.info(f"Client SERVERPORT: {client_dict['SERVERPORT']}")
            logger.info(f"Client MYPORT: {client_dict['MYPORT']}")
            logger.info(f"Client FILE_VECTOR: {client_dict['FILE_VECTOR']}")
            logger.info("Dumped client config as yaml data")
        

def file_generator(folder):
    '''
    Function to generate 50 random text files in a folder
    folder : string path of folder
    '''
    parent = create_dirs(folder)
    letters = string.ascii_letters + string.digits

    for file_idx in range(50):
        fn = str(file_idx) + ".txt"
        new_file = parent / fn
        bytes_written = 0
        with new_file.open('w') as f:
            for j in range(40):
                random_string = ''.join(random.choice(letters) for i in range(1000))
                f.write(random_string)
                bytes_written += len(random_string)
        logger.info(f"Finished writing to file {new_file}")
        logger.debug(f"Wrote file of size bytes = {bytes_written}")

if __name__ == '__main__':
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s :: %(pathname)s:%(lineno)d :: %(levelname)s :: %(message)s", filename = "./logs/utils.log" )
    file_generator("./files/")
    client_config_generator("./files")
