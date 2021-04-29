# PyTorrent

[![Python application](https://github.com/arunj18/PyTorrent/actions/workflows/python-app_fix.yml/badge.svg?branch=main&event=push)](https://github.com/arunj18/PyTorrent/actions/workflows/python-app_fix.yml)

---

## Installation

This project uses **Pipenv** for dependency and virtual environment management, more about **Pipenv** can be found [here](https://pipenv.pypa.io/en/latest/).

**Python : 3.8**  
**Tested OS: Ubuntu 20.04 LTS**
**GNU Make: 4.2.1**

1. Make sure **Python** and **pip** are already installed. Then run the following through **pip** in the terminal:  
    `pip install --user pipenv`
    Make sure pipenv is available on PATH if using the --user option.
    
    Alternatively, you can use pipx to create an isolated environment to use pipenv. 
    `pip install --user pipx`
    `python3 -m pipx ensurepath` to ensure pipx is on path.
    `pipx install pipenv`

2. After **Pipenv** has been installed run the following command in terminal to install the dependencies for this project:  
    `make install`

3. (Optional) Install Xterm to use the multi client launcher. Xterm can be installed using the following commands:  
    `sudo apt-get update -y`  
    `sudo apt-get install -y xterm`

4. Before running the project, the files and client configs have to be generated. This can be done through by running  
    `make build`
This checks if all the configs and files have been generated correctly.  

---

## Usage

### Server usage

- To start the main server, run the following command:  
`make server`

- After the server init is complete, it will accept new connection requests.

### Client usage

- **(Xterm required) Multiple clients**: Multiple clients can be started by running the following command  
    `make clients`  
Then the client numbers to be started should be entered with a space in between. This will open a new xterm window for each client.  
- **Single Client**: A single client can be started in the same terminal window by isnig the following command  
    `make client`  
    This will by default start up client 1. To specify the client number to start up, the client number can be specified in the following way  
    `make client client_no=3`  

---

### Clean repo

To clean the temporary files in the repository like logs, configs etc., use the following command  
    `make clean`
