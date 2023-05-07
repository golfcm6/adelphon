import sys
import socket
import selectors
import types
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from collections import OrderedDict

from game import *

NON_TERRAIN_COLOR_MAP = OrderedDict([
    ('treasure', convert_color([121, 245, 110])),
    ('animal', convert_color([237, 24, 17])),
    ('runner', convert_color([140, 14, 130])),
    ('relayer', convert_color([17, 237, 230])),
    ('blank', convert_color([255, 255, 255]))
])

interval = (len(Terrain), len(Terrain) + len(NON_TERRAIN_COLOR_MAP.keys()))
TREASURE_INDEX, ANIMAL_INDEX, RUNNER_INDEX, RELAYER_INDEX, BLANK_INDEX = [i for i in range(*interval)]

color_map = ListedColormap(list(TERRAIN_COLOR_MAP.values()) + list(NON_TERRAIN_COLOR_MAP.values()), N = interval[1])

# helper function to create a 3x3 square with value val centered at loc
def blot(map, loc, val):
    i, j = loc
    map[max(i-1, 0): i+2, max(j-1, 0): j+2] = val
    return map

class Visualizer:
    def __init__(self, seed):
        # setup sockets
        self.address = socket.gethostbyname(socket.gethostname())
        self.sel = selectors.DefaultSelector()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.address, VISUALIZER_PORT))
        self.sock.listen()
        self.sock.setblocking(False)
        self.sel.register(self.sock, selectors.EVENT_READ, data=None)

        # setup game instance and related data structures
        self.game_instance = Game(seed)
        self.base_map = self.get_base_map()
        self.relayer_map = np.full(MAP_DIMENSIONS, BLANK_INDEX)
        self.runner_locations = []
        self.runner_attendance = 0
        self.relayer_attendance = 0

        # setup plotting
        fig, self.axes = plt.subplots(ncols = 2, figsize = (12, 6))
        self.axes[0].set_title("True Game Map")
        self.true_im = self.axes[0].imshow(self.base_map, cmap = color_map, vmin = 0, vmax = interval[1] - 1, aspect = 'equal')
        self.relayer_im = self.axes[1].imshow(np.full(MAP_DIMENSIONS, BLANK_INDEX), cmap = color_map, 
                                                           vmin = 0, vmax = interval[1] - 1, aspect = 'equal')
        self.axes[1].set_title("Total Relayer Knowledge")
        plt.ion()

    # helper function that constructs base map with fixed treasure and relayer locations
    def get_base_map(self):
        map = self.game_instance.terrain.copy()
        map = blot(map, self.game_instance.treasure, TREASURE_INDEX)
        for loc in self.game_instance.relayer_locations:
            map = blot(map, loc, RELAYER_INDEX)
        return map

    # helper function that adds blots for animals to the map after getting animal info from the game
    def add_animals(self, map):
        for loc in self.game_instance.animal_locations:
            map = blot(map, loc, ANIMAL_INDEX)
        return map

    # helper function that decodes list of terrain info and adds them to a blank map
    def add_terrain(self, terra):
        for (i, j, t) in terra:
            self.relayer_map[i, j] = t

    # runs one step of the visualizer by updating plots and resetting state
    def one_step(self):
        assert len(self.runner_locations) == NUM_RUNNERS

        # make call to update animals directly since the visualizer isn't querying the map like the runners
        self.game_instance.update_animals()
        map = self.add_animals(self.base_map.copy())
        for loc in self.runner_locations:
            map = blot(map, loc, RUNNER_INDEX)

        # update plots
        self.true_im.set_data(map)
        self.relayer_im.set_data(self.relayer_map)
        plt.pause(0.01)

        # reset attendance and locations
        self.relayer_map = np.full(MAP_DIMENSIONS, BLANK_INDEX)
        self.runner_attendance = 0
        self.relayer_attendance = 0
        self.runner_locations = []

    # a wrapper function for accepting sockets w/ selector
    def accept_wrapper(self, sock):
        conn, (addr, port) = sock.accept()
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
            # add current relayer's info to the master relayer map for this time step
            _, id, treasure_location, animal_locations, terrains, known_runner_locations = recv_data
            self.add_terrain(eval(terrains))
            if eval(treasure_location):
                self.relayer_map = blot(self.relayer_map, treasure_location, TREASURE_INDEX)
            for animal in eval(animal_locations):
                self.relayer_map = blot(self.relayer_map, animal, ANIMAL_INDEX)
            for runner in eval(known_runner_locations):
                self.relayer_map = blot(self.relayer_map, runner, RUNNER_INDEX)
        else:
            raise Exception(f"Invalid data: {recv_data}")

        # once it has heard back from everyone, the visualizer should one step
        if self.runner_attendance == NUM_RUNNERS and self.relayer_attendance == NUM_RELAYERS:
            self.one_step()
        sock.send(MESSAGE_RECEIVED.encode("utf-8"))


def main(seed):
    visualizer = Visualizer(seed)
    try:
        while True:
            events = visualizer.sel.select(timeout=None)
            for key, _ in events:
                if key.data is None:
                    visualizer.accept_wrapper(key.fileobj)
                else:
                    visualizer.service_connection(key)
    except KeyboardInterrupt:
        plt.ioff()
        sys.exit()

if __name__ == '__main__':
    assert len(sys.argv) == 2, "This program only takes the required argument seed"
    main(int(sys.argv[1]))