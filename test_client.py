from base import Client

if __name__ == "__main__":
    client = Client()
    client.connect(1234)
    print(client.get_msg())