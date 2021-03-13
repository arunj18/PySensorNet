client_no = 1

install: 
	pipenv install --ignore-pipfile

clean:
	rm -rf ./configs/* ./files/* ./logs/* ./client_logs/*

build: setup.py
	pipenv run pytest

clients: client/client.py client/constants.py client/main_serv.py client/p2p.py client/client_utils.py utils.py client_launcher.py
	pipenv run python3 client_launcher.py

client: client/client.py client/constants.py client/main_serv.py client/p2p.py client/client_utils.py utils.py
ifeq ($(client_no),1)
	pipenv run python3 client/client.py 1
else
	pipenv run python3 client/client.py $(client_no)
endif
server: server.py 
	pipenv run python3 server.py