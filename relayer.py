import sys
import socket
import selectors
import types

from game import *
from common import port_start, TRANSMISSION_SIZE_LIMIT


class Relayer:
    def __init__(self, seed, id):
        self.id = id
        self.address = socket.gethostbyname(socket.gethostname())
        self.runner_facing_port = port_start + id
        self.relayer_facing_port = port_start + NUM_RELAYERS + id
        self.sel = selectors.DefaultSelector()
        self.relayer_connections = []
        self.runner_connections = []

        # socket for all runners to connect to
        self.runner_facing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.runner_facing_socket.bind((self.address, self.runner_facing_port))
        self.runner_facing_socket.listen()
        self.runner_facing_socket.setblocking(False)
        self.sel.register(self.runner_facing_socket, selectors.EVENT_READ, data=None)

        # socket for higher id relayers to connect to
        self.relayer_facing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.relayer_facing_socket.bind((self.address, self.relayer_facing_port))
        self.relayer_facing_socket.listen()
        self.relayer_facing_socket.setblocking(False)
        self.sel.register(self.relayer_facing_socket, selectors.EVENT_READ, data=None)

        # connect to lower id relayers
        self.lower_relayer_sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(id)]
        for i in range(id):
            self.lower_relayer_sockets[i].connect((self.address, port_start + NUM_RELAYERS + i))

        for i in range(id):
            self.lower_relayer_sockets[i].send(str(id).encode('utf-8'))

        self.game_instance = Game(seed)

    # a wrapper function for accepting sockets w/ selector
    def accept_wrapper(self, sock):
        conn, (addr, port) = sock.accept()
        if sock == self.runner_facing_socket:
            self.runner_connections.append(conn)
        elif sock == self.relayer_facing_socket:
            self.relayer_connections.append(conn)
        else:
            raise Exception("unrecognized socket")
        print(f"Accepted connection from {addr, port}")
        conn.setblocking(False)
        data = types.SimpleNamespace(port = port, inb = b"", outb = b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.sel.register(conn, events, data=data)

    # service a socket that is connected: handle inbound and outbound data
    # while running any necessary chat server methods
    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(TRANSMISSION_SIZE_LIMIT)
            if recv_data:
                # message convention: {0, 1}|{id}|
                # first arg: first bit is 0 if runner, 1 if relayer sending msg,
                # second arg: id of the runner/relayer
                # third arg: payload
                # runner payload convention: TODO
                recv_data = recv_data.decode("utf-8")
                print(recv_data)
            else:
                print(f"Closing connection to {data.port}")
                self.sel.unregister(sock)
                sock.close()
        if mask & selectors.EVENT_WRITE and data.outb:
            # handle outbound data
            sock.sendall(data.outb)
            data.outb = b''

def main(seed, id):
    assert id < NUM_RELAYERS, "invalid id"
    relayer = Relayer(seed, id)
    while True:
        events = relayer.sel.select(timeout=None)
        for key, mask in events:
            if key.data is None:
                relayer.accept_wrapper(key.fileobj)
            else:
                relayer.service_connection(key, mask)

if __name__ == '__main__':
    assert len(sys.argv) == 3, "This program takes 2 required arguments: seed and id"
    main(int(sys.argv[1]), int(sys.argv[2]))
