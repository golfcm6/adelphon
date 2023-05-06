import sys
import socket
import selectors
import types
import numpy as np

from game import *
from common import *
from visualizer import BLANK_INDEX


class Relayer:
    def __init__(self, seed, id):
        self.id = id
        self.address = socket.gethostbyname(socket.gethostname())

        self.treasure_location = None
        # set of tuples (x,y)
        self.animal_locations = set()
        # local game map with this relayer's knowledge of terrain
        self.terrains = np.full(MAP_DIMENSIONS, BLANK_INDEX, dtype=np.int8)
        self.coords = generate_coord_grid()
        self.runner_attendance = 0
        self.relayer_attendance = 0

        self.runner_facing_port = PORT_START + id
        self.relayer_facing_port = PORT_START + NUM_RELAYERS + id
        self.sel = selectors.DefaultSelector()
        self.relayer_connections = []
        self.runner_connections = []
        # both of these dictionaries use sockets (from self.runner_connections) as keys to make replying
        # to runners easier
        self.runner_within_range = dict()
        self.runner_locations = dict()
        # before relayers sync, this set only contains nearby runner locations
        # and after the sync, it contains all runners within range of any relayer
        self.current_runner_locations = set()
        # boolean array for whether a runner has gotten close enough to each grid position to check for treasure
        self.checked_for_treasure = np.full(MAP_DIMENSIONS, False)
        self.runner_was_here = np.full(MAP_DIMENSIONS, False)

        # socket for all runners to connect to
        self.runner_facing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.runner_facing_socket.bind((self.address, self.runner_facing_port))
        self.runner_facing_socket.listen()
        self.runner_facing_socket.setblocking(False)
        self.sel.register(self.runner_facing_socket, selectors.EVENT_READ, data = None)

        # socket for higher id relayers to connect to
        self.relayer_facing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.relayer_facing_socket.bind((self.address, self.relayer_facing_port))
        self.relayer_facing_socket.listen()
        self.relayer_facing_socket.setblocking(False)
        self.sel.register(self.relayer_facing_socket, selectors.EVENT_READ, data = None)

        # connect to lower id relayers
        self.lower_relayer_sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(id)]
        for i in range(id):
            self.lower_relayer_sockets[i].connect((self.address, PORT_START + NUM_RELAYERS + i))
            self.sel.register(self.lower_relayer_sockets[i], selectors.EVENT_READ, 
                              data = types.SimpleNamespace(port = PORT_START + NUM_RELAYERS + i))

        self.visualizer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.visualizer_socket.connect((self.address, VISUALIZER_PORT))

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
        events = selectors.EVENT_READ
        self.sel.register(conn, events, data = types.SimpleNamespace(port = port))

    # process incoming data from a connection
    def service_connection(self, key):
        sock = key.fileobj
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
                    # similarly once we've heard from all other relayers, we can dispatch info back to
                    # nearby runners
                    if self.relayer_attendance == NUM_RELAYERS - 1:
                        self.sync_runners()
                else:
                    raise Exception(f"Invalid data: {recv_data}")
        else:
            print(f"Closing connection to {sock}")
            self.sel.unregister(sock)
            sock.close()
            raise ConnectionError

    # share info with other relayers
    def sync_relayers(self):
        info = prepare_info(self.terrains, self.coords, self.animal_locations, self.treasure_location, 
                            RELAYER_CODE, self.id, self.current_runner_locations)
        # use self.connections to send info to higher id relayers
        for sock in self.relayer_connections:
            sock.send(info.encode("utf-8"))
        # use self.lower_relayer_sockets to send info to lower id relayers
        for i in range(len(self.lower_relayer_sockets)):
            self.lower_relayer_sockets[i].send(info.encode("utf-8"))

    def sync_runners(self):
        self.relayer_attendance = 0
        self.runner_attendance = 0
        # send all of this relayer's knowledge to the visualizer
        terra = self.encode_map()
        data = RELAYER_CODE, self.id, self.treasure_location, self.animal_locations, terra, self.current_runner_locations
        info = "|".join([str(d) for d in data])
        self.visualizer_socket.sendall(info.encode("utf-8"))
        self.visualizer_socket.recv(len(MESSAGE_RECEIVED))

        for sock in self.runner_connections:
            if self.runner_within_range[sock]:
                info = self.compile_info_for_runner(self.runner_locations[sock])
                sock.send(info.encode("utf-8"))
            else:
                sock.send(TOO_FAR_AWAY.encode("utf-8"))

        # reset info after syncing
        self.animal_locations = set()
        self.current_runner_locations = set()

    def encode_map(self):
        map, coords = self.terrains.flatten().tolist(), self.coords.reshape(-1, 2).tolist()
        return [(*coord, terrain) for terrain, coord in zip(map, coords) if terrain != BLANK_INDEX]

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
                if self.terrains[i][j] == BLANK_INDEX:
                    self.terrains[i][j] = terrain_type
                else:
                    if self.terrains[i][j] != terrain_type:
                        # TODO: anomaly/liar
                        pass
                    
        # update checked_for_treasure grid based on runner location 
        # mark all tiles within TREASURE_RADIUS as True
        if location_info:
            locations = location_info.split('!')
            for location in locations:
                i, j = eval(location)
                self.current_runner_locations.add((i, j))
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
    try:
        while True:
            events = relayer.sel.select(timeout=None)
            for key, _ in events:
                if key.data is None:
                    relayer.accept_wrapper(key.fileobj)
                else:
                    relayer.service_connection(key)
    except KeyboardInterrupt:
        sys.exit()

if __name__ == '__main__':
    assert len(sys.argv) == 3, "This program takes 2 required arguments: seed and id"
    main(int(sys.argv[1]), int(sys.argv[2]))
