import random
import string
from pathlib import Path

def file_generator(folder):
    '''
    Function to generate 50 random text files in a folder
    folder : string path of folder
    '''
    parent = Path(folder)
    parent.mkdir(parents = True, exist_ok= True)
    letters = string.ascii_letters + string.digits + string.punctuation

    for file_idx in range(50):
        fn = str(file_idx) +".txt"
        new_file = parent / fn
        with new_file.open('w') as f:
            for j in range(40):
                random_string = ''.join(random.choice(letters) for i in range(1000))
                f.write(random_string)

def file_size(path):
    if (type(path) == type(Path('./'))):
        return path.stat().st_size
    if(type(path) == str):
        return Path(path).stat().st_size

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

if __name__ == '__main__':
    test_file_generator()
