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

(NROWS, NCOLS) = (2, 3)
# plus one for the true game map
assert NROWS * NCOLS == 1 + NUM_RELAYERS, "the plot dimensions must line up with the number of relayers"

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
        self.base_map = self.get_base_map()
        self.runner_locations = []
        self.runner_attendance = 0
        self.relayer_attendance = 0

        fig, self.axes = plt.subplots(nrows = NROWS, ncols = NCOLS, squeeze = False, figsize = (6 * NROWS, 6 * NCOLS))
        self.axes[0, 0].set_title("True Game Map")
        self.true_im = self.axes[0, 0].imshow(self.base_map, cmap = color_map, vmin = 0, vmax = interval[1] - 1, aspect = 'equal')
        self.relayer_ims = []
        # off by one to account for the true game map
        for i in range(1, NUM_RELAYERS + 1):
            im = self.axes[i // NCOLS, i % NCOLS].imshow(np.full(MAP_DIMENSIONS, BLANK_INDEX), cmap = color_map, 
                                                           vmin = 0, vmax = interval[1] - 1, aspect = 'equal')
            self.relayer_ims.append(im)
            self.axes[i // NCOLS, i % NCOLS].set_title(f"Relayer {i-1}'s Map")
        plt.ion()
        self.relayer_maps = [None] * NUM_RELAYERS

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
    def decode_map(self, terra):
        map = np.full(MAP_DIMENSIONS, BLANK_INDEX, dtype = np.int8)
        for (i, j, t) in terra:
            map[i, j] = t
        return map

    # runs one step of the visualizer by updating plots and resetting state
    def one_step(self):
        assert len(self.runner_locations) == NUM_RUNNERS

        # make call to update animals directly since the visualizer isn't querying the map like the runners
        self.game_instance.update_animals()
        map = self.add_animals(self.base_map.copy())
        for loc in self.runner_locations:
            map = blot(map, loc, RUNNER_INDEX)

        self.true_im.set_data(map)
        for i in range(NUM_RELAYERS):
            self.relayer_ims[i].set_data(self.relayer_maps[i])
        plt.pause(0.01)

        # reset attendance and locations
        self.runner_attendance = 0
        self.relayer_attendance = 0
        self.runner_locations = []

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
            # reconstruct relayer map with passed info
            _, id, treasure_location, animal_locations, terrains, known_runner_locations = recv_data
            map = self.decode_map(eval(terrains))
            if eval(treasure_location):
                map = blot(map, treasure_location, TREASURE_INDEX)
            for animal in eval(animal_locations):
                map = blot(map, animal, ANIMAL_INDEX)
            for runner in eval(known_runner_locations):
                map = blot(map, runner, RUNNER_INDEX)
            self.relayer_maps[int(id)] = map
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
        sys.exit()

if __name__ == '__main__':
    assert len(sys.argv) == 2, "This program only takes the required argument seed"
    main(int(sys.argv[1]))