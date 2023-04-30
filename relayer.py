import sys
import socket
import selectors
import types
import numpy as np

from game import *
from common import *


class Relayer:
    def __init__(self, seed, id):
        self.id = id
        self.address = socket.gethostbyname(socket.gethostname())

        self.treasure_location = None
        # set of tuples (x,y)
        self.animal_locations = set()
        # local game map with this relayers knowledge of terrain
        self.terrains = np.full(MAP_DIMENSIONS, -1, dtype=np.int8)
        self.coords = generate_coord_grid(MAP_DIMENSIONS)
        self.runner_attendance = 0
        self.relayer_attendance = 0

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
        self.location = self.game_instance.relayer_locations

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
        data = types.SimpleNamespace(port = port)
        events = selectors.EVENT_READ
        self.sel.register(conn, events, data=data)

    # process incoming data from a connection
    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        recv_data = sock.recv(RELAYER_TRANSMISSION_SIZE_LIMIT)
        if recv_data:
            # message convention: {0, 1}|{id}|
            # first arg: first bit is 0 if runner, 1 if relayer sending msg,
            # second arg: id of the runner/relayer
            # third arg: payload
            # runner payload convention: 0|id|treasure|animals|terrain
            # relayer payload convention: XXX
            # TODO: update comments

            recv_data = recv_data.decode("utf-8")
            if recv_data == TOO_FAR_AWAY:
                self.runner_attendance += 1
                # check if this is the last runner to hear from in this "epoch"
                if self.runner_attendance == NUM_RUNNERS:
                    self.sync_relayers()
            else:
                recv_data = recv_data.split("|")
                # runner message
                if recv_data[0] == RUNNER_CODE:
                    self.parse_info(recv_data)
                    self.runner_attendance += 1
                    if self.runner_attendance == NUM_RUNNERS:
                        self.sync_relayers()
                elif recv_data[0] == RELAYER_CODE:
                    self.parse_info(recv_data)
                    self.relayer_attendance += 1
                    if self.relayer_attendance == NUM_RELAYERS:
                        self.sync_runners()
                else:
                    raise Exception(f"Invalid data: {recv_data}")
        else:
            print(f"Closing connection to {data.port}")
            self.sel.unregister(sock)
            sock.close()

    # share info with other relayers
    def sync_relayers(self):
        info = self.prepare_info_for_relayer()
        self.runner_attendance = 0
        # use self.connections to send info to higher id relayers
        for sock in self.relayer_connections:
            sock.send(info.encode("utf-8"))
        # use self.lower_relayer_sockets to send info to lower id relayers
        for i in range(len(self.lower_relayer_sockets)):
            self.lower_relayer_sockets[i].send(info.encode("utf-8"))

    def sync_runners(self):
        for sock in self.runner_connections:
            pass

    def parse_info(self, data):
        code, id, treasure, animals, terrains = data
        if treasure:
            self.treasure_location = eval(treasure)

        # update relayer animal mapping
        if animals:
            animals = animals.split('!')
            for animal in animals:
                self.animal_locations.add(eval(animal))

        # update relayer terrain mapping
        if terrains:
            terrains = terrains.split('!')
            for terrain in terrains:
                i, j, terrain_type = eval(terrain)
                if self.terrains[i][j] == -1:
                    self.t[i][j] = terrain_type
                else:
                    if self.terrains[i][j] != terrain_type:
                        # TODO: anomaly/liar
                        pass

    # prepare info to transmit to other relayers once all runners are accounted for
    # convention: relayer_code|id|treasure|animals|terrain (we prioritize information in this same order)
    def prepare_info_for_relayer(self):
        relevant_info = RELAYER_CODE + "|" + self.id + "|"
        # treasure info logic
        if self.treasure_location: 
            relevant_info += str(self.treasure_location)
        relevant_info += "|"

        # animal info logic
        for animal in self.animal_locations:
            # + 1 for the required pipe separator between animals and terrain
            if len(relevant_info) + len(str(animal)) + 1 > RELAYER_TRANSMISSION_SIZE_LIMIT:
                break # relevant info string has gotten too long
            else:
                relevant_info += str(animal) + '!'
        # remove extra separator
        if relevant_info[-1] == '!':
            relevant_info = relevant_info[:-1]
        relevant_info += "|"

        # terrain info logic
        terrains, coords = np.flatten(terrains), coords.reshape((-1, 2))
        coords = coords[np.argsort(terrains)[::-1]]
        terrains = np.sort(terrains)[::-1]
        for terrain, coord in zip(terrains, coords):
            info = (*coord, terrain)
            if len(relevant_info) + len(str(info)) > RELAYER_TRANSMISSION_SIZE_LIMIT:
                break # relevant info string has gotten too long
            else:
                relevant_info += str(terrain) + '!'
        # remove extra separator
        if relevant_info[-1] == '!':
            relevant_info = relevant_info[:-1]

        return relevant_info

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
