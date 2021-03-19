import subprocess
import time


def start_client_in_list(clients):
    for i in clients:
        try:
            subprocess.Popen(['xterm', '-e',
                              f'python ./client/client.py {int(i)}'],
                             shell=False, stdin=None, stdout=None, stderr=None,
                             close_fds=True)
            time.sleep(2)
        except ValueError:
            print(f"Input {i} was invalid")


if __name__ == "__main__":
    start_client_in_list(input().split(' '))
