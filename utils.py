import random
import string
from pathlib import Path

def file_generator(folder):
    parent = Path(folder)
    parent.mkdir(parents = True, exist_ok= True)
    letters = string.ascii_letters + string.digits + string.punctuation

    for file_idx in range(50):
        fn = str(file_idx) +".txt"
        new_file = parent / fn
        with new_file.open('w') as f:
            for j in range(1000):
                random_string = ''.join(random.choice(letters) for i in range(1000))
                f.write(random_string)

if __name__ == '__main__':
    file_generator('./files/')
