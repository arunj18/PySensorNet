import sys, os
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')


from pathlib import Path
from utils import file_size
from setup import file_generator, client_config_generator
from yaml import load, Loader

def test_file_generator():
    '''
    Function to test if files are created and are of valid size
    by default runs in ./files/
    '''
    folder = "./files/"
    file_generator(folder)
    
    folder_path = Path(folder)

    assert folder_path.is_dir() #check if it is a directory

    assert any(folder_path.iterdir()) # check if directory is empty

    file_list = range(50)
    hash_map = {}
    for i in file_list:
        hash_map[i] = False

    for i in folder_path.iterdir():
        if i.is_file() and i.name.endswith('.txt'):
            check = i.name[:-4]
            try:
                check = int(check)

                hash_map[check] = True #file is created

                if check in file_list:
                    assert file_size(i) > 0 #check if file is empty

            except ValueError: #not the file we're looking for
                pass
    for i in hash_map.keys():
        assert hash_map[i] # file i is missing

def test_client_config():
    '''
    Function to check if client configs created are valid and can be loaded in as yaml objects
    by default stored in ./configs/clients
    '''
    folder = "./configs/clients"
    client_config_generator('./files')
    
    folder_path = Path(folder)

    assert folder_path.is_dir() #check if it is a directory

    assert any(folder_path.iterdir()) # check if directory is empty

    file_list = range(1,51)
    hash_map = {}
    for i in file_list:
        hash_map[i] = False

    for i in folder_path.rglob('*'):
        if i.is_file() and i.name.endswith('.yaml'):
            check = i.name[:-5]
            try:
                check = int(check)

                 #file is created

                if check in file_list:
                    assert file_size(i) > 0 #check if file is empty
                with i.open('r') as f:
                    client_dict = load(f, Loader=Loader)
                    assert type(client_dict) == dict

                    assert client_dict.get('CLIENTID',None)
                    assert client_dict.get('SERVERPORT',None)
                    assert client_dict.get("MYPORT",None)
                    assert client_dict.get("FILE_VECTOR",None)

                    assert client_dict['FILE_VECTOR'] != "0"*50
                print(f"Check done {check}")
                hash_map[check] = True
            except ValueError: #not the file we're looking for
                pass
    for i in hash_map.keys():
        print(i)
        assert hash_map[i] # file i is missing

if __name__ == "__main__":
    test_file_generator()
    test_client_config()