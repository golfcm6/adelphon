import sys
import socket
import selectors
import types
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from game import *

NON_TERRAIN_COLOR_MAP = {
    'treasure': convert_color([60, 255, 0]),
    'animal': convert_color([237, 24, 17]),
    'runner': convert_color([140, 14, 130]),
    'relayer': convert_color([17, 237, 230]),
    'blank': convert_color([255, 255, 255])
}

BASE_INDEX = len(Terrain)
TREASURE_INDEX = BASE_INDEX
ANIMAL_INDEX = BASE_INDEX + 1
RUNNER_INDEX = BASE_INDEX + 2
RELAYER_INDEX = BASE_INDEX + 3
BLANK_INDEX = BASE_INDEX + 4

color_map = ListedColormap(list(TERRAIN_COLOR_MAP.values()) + list(NON_TERRAIN_COLOR_MAP.values()))

# helper function to create a 3x3 square with value val centered at loc
def blot(map, loc, val):
    i, j = loc
    map[max(i-1, 0):i+2, max(j-1, 0): j+2] = val
    return map

class Visualizer:
    def __init__(self, seed):
        # setup socket
        self.address = socket.gethostbyname(socket.gethostname())
        self.sel = selectors.DefaultSelector()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.address, VISUALIZER_PORT))
        self.sock.listen()
        self.sock.setblocking(False)
        self.sel.register(self.sock, selectors.EVENT_READ, data=None)

        self.game_instance = Game(seed)
        self.base_index = len(Terrain)
        self.base_map = self.get_base_map()
        self.runner_locations = []
        self.runner_attendance = 0
        self.relayer_attendance = 0

        # self.im = plt.imshow(self.base_map.copy(), cmap = color_map)
        # plt.show(block = False)

        # used for cycling the displayed relayer map
        self.curr_relayer_id = 0
        self.curr_relayer_map = None

    # construct base map with treasure and relayers which don't move
    def get_base_map(self):
        map = self.game_instance.terrain.copy()
        map = blot(map, self.game_instance.treasure, TREASURE_INDEX)
        for loc in self.game_instance.relayer_locations:
            map = blot(map, loc, RELAYER_INDEX)
        return map

    def add_animals(self, map):
        for loc in self.game_instance.animal_locations:
            map = blot(map, loc, ANIMAL_INDEX)
        return map

    def one_step(self):
        assert len(self.runner_locations) == NUM_RUNNERS

        # make call to update animals directly since the visualizer isn't querying the map like the runners
        self.game_instance.update_animals()
        map = self.add_animals(self.base_map.copy())
        for loc in self.runner_locations:
            map = blot(map, loc, RUNNER_INDEX)

        # self.im = plt.imshow(map, cmap = color_map)
        # plt.ion()
        # plt.show()
        # self.im.set_data(map)
        # plt.draw()
        # plt.pause(1)

        # reset attendance and locations
        self.runner_attendance = 0
        self.relayer_attendance = 0
        self.runner_locations = []
        self.curr_relayer_id = (self.curr_relayer_id + 1) % NUM_RELAYERS

    # a wrapper function for accepting sockets w/ selector
    def accept_wrapper(self, sock):
        conn, (addr, port) = sock.accept()
        print(f"Accepted connection from {addr, port}")
        conn.setblocking(False)
        events = selectors.EVENT_READ
        self.sel.register(conn, events, data = types.SimpleNamespace(port = port))

    # process incoming data from a connection
    def service_connection(self, key):
        assert self.relayer_attendance <= NUM_RELAYERS
        assert self.runner_attendance <= NUM_RUNNERS
        sock = key.fileobj
        data = key.data
        recv_data = sock.recv(VISUALIZER_TRANSMISSION_SIZE_LIMIT)
        if not recv_data:
            raise ConnectionError(f"Lost connection to socket on port {data.port}")
        recv_data = recv_data.decode("utf-8").split("|")
        if recv_data[0] == RUNNER_CODE:
            self.runner_attendance += 1
            self.runner_locations.append(eval(recv_data[1]))
        elif recv_data[0] == RELAYER_CODE:
            self.relayer_attendance += 1
            # update our relayer data structures with passed info if relayer_id matches the current one we plot
            _, id, treasure_location, animal_locations, terrains, known_runner_locations = recv_data
            if id == self.curr_relayer_id:
                map = self.decode_map(eval(terrains))
                if eval(treasure_location):
                    map = blot(map, treasure_location, TREASURE_INDEX)
                for animal in eval(animal_locations):
                    map = blot(map, animal, ANIMAL_INDEX)
                for runner in eval(known_runner_locations):
                    map = blot(map, runner, RUNNER_INDEX)
                self.curr_relayer_map = map
        else:
            raise Exception(f"Invalid data: {recv_data}")

        # once it has heard back from everyone, the visualizer should one step
        if self.runner_attendance == NUM_RUNNERS and self.relayer_attendance == NUM_RELAYERS:
                self.one_step()
        sock.send(MESSAGE_RECEIVED.encode("utf-8"))

    def decode_map(self, terra):
        map = np.full(MAP_DIMENSIONS, BLANK_INDEX, dtype = np.int8)
        for (i, j, t) in terra:
            map[i, j] = t
        return map

def main(seed):
    visualizer = Visualizer(seed)
    while True:
        events = visualizer.sel.select(timeout=None)
        for key, _ in events:
            if key.data is None:
                visualizer.accept_wrapper(key.fileobj)
            else:
                visualizer.service_connection(key)


if __name__ == '__main__':
    assert len(sys.argv) == 2, "This program only takes the required argument seed"
    main(int(sys.argv[1]))