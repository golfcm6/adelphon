import sys
import socket
import selectors
import types
import numpy as np

from game import *
from common import *
from visualizer import BLANK_INDEX

WAITING_FOR_RUNNERS = 'a'
WAITING_FOR_RELAYERS = 'b'

class Relayer:
    def __init__(self, seed, id):
        self.id = id
        self.game_instance = Game(seed)
        print(f"Relayer {self.id} is up and relaying")
        # setup data structures that represent this relayer's knowledge
        self.treasure_location = None
        self.animal_locations = set() # set of tuples (x,y)
        # local game map with this relayer's knowledge of terrain
        self.terrains = np.full(MAP_DIMENSIONS, BLANK_INDEX, dtype=np.int8)
        self.coords = generate_coord_grid()
        self.location = self.game_instance.relayer_locations[self.id]

        # setup sockets for communication
        self.address = socket.gethostbyname(socket.gethostname())
        self.runner_facing_port = PORT_START + id
        self.relayer_facing_port = PORT_START + NUM_RELAYERS + id
        self.sel = selectors.DefaultSelector()
        self.relayer_connections = []
        self.runner_connections = set()
        # socket for all runners to connect to
        self.runner_facing_socket = self.listening_socket(self.runner_facing_port)
        # socket for higher id relayers to connect to
        self.relayer_facing_socket = self.listening_socket(self.relayer_facing_port)

        # connect to lower id relayers
        self.lower_relayer_sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(id)]
        for i in range(id):
            self.lower_relayer_sockets[i].connect((self.address, PORT_START + NUM_RELAYERS + i))
            self.sel.register(self.lower_relayer_sockets[i], selectors.EVENT_READ, 
                              data = types.SimpleNamespace(port = PORT_START + NUM_RELAYERS + i))

        self.visualizer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.visualizer_socket.connect((self.address, VISUALIZER_PORT))

        # setup data structures that help implement relayer logic
        self.runner_attendance = 0
        self.runner_count = NUM_RUNNERS
        self.relayer_attendance = 0
        # these three dictionaries use sockets (from self.runner_connections) as keys
        # to make it easier to reply to runners
        self.runner_within_range = dict()
        self.runner_locations = dict()
        self.existing_targets = dict()
        # before relayers sync, this set only contains nearby runner locations
        # and after the sync, it contains all runners within range of any relayer
        self.current_runner_locations = set()
        # boolean array for whether a runner has gotten close enough to each grid position to check for treasure
        self.checked_for_treasure = np.full(MAP_DIMENSIONS, False)
        self.phase = WAITING_FOR_RUNNERS
        self.won = False

        # tell spawner that everything has been set up correctly
        alert_spawn_process()

    # helper function to create and register a listening socket at the given port
    def listening_socket(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.address, port))
        sock.listen()
        sock.setblocking(False)
        self.sel.register(sock, selectors.EVENT_READ, data = None)
        return sock

    # a wrapper function for accepting sockets w/ selector
    def accept_wrapper(self, sock):
        conn, (addr, port) = sock.accept()
        if sock == self.runner_facing_socket:
            self.runner_connections.add(conn)
        elif sock == self.relayer_facing_socket:
            self.relayer_connections.append(conn)
        else:
            raise Exception("unrecognized socket")
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
            else:
                recv_data = recv_data.split("|")
                # runner message
                if recv_data[0] == RUNNER_CODE:
                    # handle special case of the runner either dying or winning
                    if len(recv_data) == 3:
                        msg = recv_data[2]
                        if msg == IM_DEAD:
                            # close socket for this runner and remove them from active runner connections
                            self.runner_connections.remove(sock)
                            self.sel.unregister(sock)
                            sock.close()
                            self.runner_count -= 1
                            if self.runner_count == 0:
                                sys.exit() # GAME OVER because all runners have died
                        elif msg == I_WON:
                            self.runner_attendance += 1
                            self.won = True # GAME OVER but wait till relayer sync to exit gracefully
                        else:
                            raise ValueError(f"Invalid msg: {msg}")
                    # standard runner case
                    else:
                        self.runner_within_range[sock] = True
                        location = self.parse_info(recv_data)
                        self.runner_locations[sock] = location
                        self.current_runner_locations.add(location)
                        self.runner_attendance += 1
                # relayer message
                elif recv_data[0] == RELAYER_CODE:
                    self.parse_info(recv_data)
                    self.relayer_attendance += 1
                else:
                    raise Exception(f"Invalid data: {recv_data}")
        else:
            self.sel.unregister(sock)
            sock.close()
            self.runner_connections.discard(sock) # won't throw an error if the socket isn't a runner sock
            # this is fine if you've already won because the sys exits won't be perfectly in sync
            if not self.won:
                raise ConnectionError(f"Closing connection to {sock}")
        # sync with other relayers once you've heard back from all runners
        if self.runner_attendance == self.runner_count and self.phase == WAITING_FOR_RUNNERS:
            self.sync_with_relayers()
            self.phase = WAITING_FOR_RELAYERS
        # sync with runners once you've heard back from all other relayers
        if self.relayer_attendance == (NUM_RELAYERS - 1) and self.phase == WAITING_FOR_RELAYERS:
            self.sync_with_runners()
            self.phase = WAITING_FOR_RUNNERS

    # share info with other relayers
    def sync_with_relayers(self):
        if self.won:
            # tell all runners that the game has been won, then exit
            for sock in self.runner_connections:
                sock.send(WE_WON.encode("utf-8"))
            sys.exit()

        # query the map and update state
        game_state = self.game_instance.query(self.location, is_runner = False)
        # all other parts of game state are irrelevant for relayers
        (terrains, coords), animals, treasure = game_state.local_view
        if treasure:
            self.treasure_location = treasure
        self.animal_locations.update(animals)
        i, j = coords[:,:,0], coords[:,:,1]
        self.terrains[i, j] = terrains

        info = prepare_info(self.terrains, self.coords, self.animal_locations, self.treasure_location, 
                            RELAYER_CODE, self.id, self.current_runner_locations)
        # use self.relayer_connections to send info to higher id relayers
        # and self.lower_relayer_sockets to send info to lower id relayers
        for sock in (self.relayer_connections + self.lower_relayer_sockets):
            sock.send(info.encode("utf-8"))

    def sync_with_runners(self):
        # send all of this relayer's knowledge to the visualizer
        terra = self.encode_map()
        data = RELAYER_CODE, self.id, self.treasure_location, self.animal_locations, terra, self.current_runner_locations
        info = "|".join([str(d) for d in data])
        self.visualizer_socket.sendall(info.encode("utf-8"))
        # each relayer must wait for the visualizer to respond before actually letting the runners go ahead
        self.visualizer_socket.recv(len(MESSAGE_RECEIVED))

        # reset info
        self.relayer_attendance = 0
        self.runner_attendance = 0
        self.animal_locations = set()
        self.current_runner_locations = set()

        # respond to runners with relevant info
        for sock in self.runner_connections:
            if self.runner_within_range[sock]:
                info = self.compile_info_for_runner(sock)
                sock.send(info.encode("utf-8"))
            else:
                sock.send(TOO_FAR_AWAY.encode("utf-8"))

    # encode terrain map by creating tuples for map positions that aren't blank
    def encode_map(self):
        map, coords = self.terrains.flatten().tolist(), self.coords.reshape(-1, 2).tolist()
        return [(*coord, terrain) for terrain, coord in zip(map, coords) if terrain != BLANK_INDEX]

    # info sent by relayer to a runner
    # convention: id|treasure|target|animals|terrains
    def compile_info_for_runner(self, sock):
        target = self.find_target(sock)
        # use standard prepare_info function to help compile some info and then rearrange using new schema
        info = prepare_info(self.terrains, self.coords, self.animal_locations, self.treasure_location, 
                            RUNNER_CODE, self.id, [target])
        _, id, target, treasure, animals, terrain = info.split("|")
        return "|".join([id, treasure, target, animals, terrain])

    # find a target grid position that is close to the runner but hasn't yet been checked for treasure
    def find_target(self, sock):
        if self.treasure_location is not None:
            return self.treasure_location

        # keep the same target if it hasn't been explored yet
        if sock in self.existing_targets and (not self.checked_for_treasure[self.existing_targets[sock]]):
            return self.existing_targets[sock]

        i, j = self.runner_locations[sock]
        # the furthest you can go (in terms of LINF norm) is the max distance to an edge of the map 
        LINF_SWEEP_MAX = max(i, j, MAP_DIMENSIONS[0] - 1 - i, MAP_DIMENSIONS[1] - 1 - j)
        # L-infinity norm is the appropriate norm for this game since the runners can move in all 8 directions
        # iterate through grid positions near the runner by incrementing LINF norm
        for LINF in range(LINF_SWEEP_MIN, LINF_SWEEP_MAX):
            coords = []
            # construct LINF box by creating each edge (top, left, bottom, right)
            imin, imax = max(i - LINF, 0), min(i + LINF, MAP_DIMENSIONS[0] - 1)
            jmin, jmax = max(j - LINF, 0), min(j + LINF, MAP_DIMENSIONS[1] - 1)
            if i - LINF >= 0:
                coords.extend([(i - LINF, j_) for j_ in range(jmin, jmax + 1)]) # top
            if j - LINF >= 0:
                coords.extend([(i_, j - LINF) for i_ in range(imin, imax + 1)]) # left
            if i + LINF < MAP_DIMENSIONS[0]:
                coords.extend([(i + LINF, j_) for j_ in range(jmin, jmax + 1)]) # bottom
            if j + LINF < MAP_DIMENSIONS[1]:
                coords.extend([(i_, j + LINF) for i_ in range(imin, imax + 1)]) # right
            # see if any of the coords are unexplored
            for coord in coords:
                assert is_valid_location(coord), "this iteration should only include valid coordinates"
                if not self.checked_for_treasure[coord]:
                    self.existing_targets[sock] = coord
                    return coord
        raise Exception("Somehow every location on the map has been checked")

    # parse incoming information from both runners and other relayers
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
                self.terrains[i][j] = terrain_type
        # update checked_for_treasure grid based on runner location 
        # mark all tiles within TREASURE_RADIUS as True
        if location_info:
            locations = location_info.split('!')
            for location in locations:
                i, j = eval(location)
                self.current_runner_locations.add((i, j))
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
