import subprocess

def start_client_in_list(clients):
    for i in clients:
        subprocess.call(['xterm', '-e', f'python bb.py {int(i)}'])

if __name__ == "__main__":
    start_client_in_list(input().split(' '))