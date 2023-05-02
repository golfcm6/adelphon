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
        self.coords = generate_coord_grid()
        self.runner_attendance = 0
        self.relayer_attendance = 0

        self.runner_facing_port = port_start + id
        self.relayer_facing_port = port_start + NUM_RELAYERS + id
        self.sel = selectors.DefaultSelector()
        self.relayer_connections = []
        self.runner_connections = []
        # both of these dictionaries use sockets (from self.runner_connections) as keys to make replying
        # to runners easier
        self.runner_within_range = dict()
        self.runner_locations = dict()
        self.current_runner_locations = set() # set of locations for the runners that are within range
        # boolean array for whether a runner has gotten close enough to each grid position to check for treasure
        self.checked_for_treasure = np.full(MAP_DIMENSIONS, False)
        self.runner_was_here = np.full(MAP_DIMENSIONS, False)

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
            recv_data = recv_data.decode("utf-8")
            # runners that are too far away will still send a heartbeat so we can make sure
            # all runners and relayers are synced up in the game
            if recv_data == TOO_FAR_AWAY:
                self.runner_within_range[sock] = False
                self.runner_attendance += 1
                # when we've heard from all runners, we can sync all of the relayers by sharing info
                if self.runner_attendance == NUM_RUNNERS:
                    self.sync_relayers()
            else:
                recv_data = recv_data.split("|")
                # runner message
                if recv_data[0] == RUNNER_CODE:
                    self.runner_within_range[sock] = True
                    location = self.parse_info(recv_data)
                    self.runner_locations[sock] = location
                    self.current_runner_locations.add(location)
                    self.runner_attendance += 1
                    if self.runner_attendance == NUM_RUNNERS:
                        self.sync_relayers()
                # relayer message
                elif recv_data[0] == RELAYER_CODE:
                    self.parse_info(recv_data)
                    self.relayer_attendance += 1
                    # similarly once we've heard from all relayers, we can dispatch info back to
                    # nearby runners
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
        useful_runner_locations = list(filter(lambda x: not self.runner_was_here[x], self.current_runner_locations))
        info = prepare_info(self.terrains, self.coords, self.animal_locations, self.treasure_location, 
                            RELAYER_CODE, self.id, useful_runner_locations)
        # reset runner related info after syncing
        self.runner_attendance = 0
        self.current_runner_locations = set()
        # use self.connections to send info to higher id relayers
        for sock in self.relayer_connections:
            sock.send(info.encode("utf-8"))
        # use self.lower_relayer_sockets to send info to lower id relayers
        for i in range(len(self.lower_relayer_sockets)):
            self.lower_relayer_sockets[i].send(info.encode("utf-8"))

    def sync_runners(self):
        for sock in self.runner_connections:
            if self.runner_within_range[sock]:
                info = self.compile_info_for_runner(self.runner_locations[sock])
                sock.send(info.encode("utf-8"))
            else:
                sock.send(TOO_FAR_AWAY.encode("utf-8"))

    # info sent by relayer to a runner
    # convention: id|treasure|target|animals|terrains
    def compile_info_for_runner(self, runner_location):
        target = self.find_target(runner_location)
        # use standard prepare_info function to help compile some info and then rearrange using new schema
        info = prepare_info(self.terrains, self.coords, self.animal_locations, self.treasure_location, 
                            RUNNER_CODE, self.id, [target])
        _, id, target, treasure, animals, terrain = info.split("|")
        return "|".join([id, treasure, target, animals, terrain])

    # find a target grid position that is close to the runner but hasn't yet been checked for treasure
    def find_target(self, runner_location):
        if self.treasure_location is not None:
            return self.treasure_location
        
        i, j = runner_location
        # iterate through grid positions near the runner by incrementing L1 norm
        # ideally we're using L2 norm, but this makes the iteration tractable
        for L1 in range(L1_SWEEP_MIN, MAP_DIMENSIONS[0] + MAP_DIMENSIONS[1] - 1):
            for di in range(L1 + 1):
                dj = L1 - di # the difference in i and j must add up to the L1 norm
                coords = {(i + di, j + dj), (i - di, j + dj), (i + di, j - dj), (i - di, j - dj)}
                for coord in coords:
                    if is_valid_location(coord) and not self.checked_for_treasure[coord]:
                        return coord
        raise Exception("Somehow every location on the map has been checked")


    def parse_info(self, data):
        code, id, location_info, treasure, animals, terrains = data
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
                    self.terrains[i][j] = terrain_type
                else:
                    if self.terrains[i][j] != terrain_type:
                        # TODO: anomaly/liar
                        pass
                    
        # update checked_for_treasure grid based on runner location 
        # mark all tiles within TREASURE_RADIUS as True
        locations = location_info.split('!')
        for location in locations:
            i, j = eval(location)
            self.runner_was_here[i, j] = True
            for i2 in range(i - TREASURE_RADIUS, i + TREASURE_RADIUS + 1):
                for j2 in range(j - TREASURE_RADIUS, j + TREASURE_RADIUS + 1):
                    if is_valid_location((i2, j2)) and distance((i, j), (i2, j2)) <= TREASURE_RADIUS:
                        self.checked_for_treasure[i2, j2] = True

        if code == RUNNER_CODE:
            return eval(location_info)

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
