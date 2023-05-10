import sys
import os, signal
import socket
import selectors
import types
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import matplotlib.lines as mlines
from matplotlib.patches import RegularPolygon
from collections import OrderedDict

from game import *
from common import alert_spawn_process

NON_TERRAIN_COLOR_MAP = OrderedDict([
    ('treasure', convert_color([121, 245, 110])),
    ('animal', convert_color([237, 24, 17])),
    ('runner', convert_color([140, 14, 130])),
    ('relayer', convert_color([17, 237, 230])),
])
BLANK_COLOR = convert_color([255, 255, 255])
BLANK_INDEX = -1
interval = (len(Terrain), len(Terrain) + len(NON_TERRAIN_COLOR_MAP.keys()))
TREASURE_INDEX, ANIMAL_INDEX, RUNNER_INDEX, RELAYER_INDEX = [i for i in range(*interval)]

color_map = ListedColormap([BLANK_COLOR, *TERRAIN_COLOR_MAP.values(), *NON_TERRAIN_COLOR_MAP.values()])

# helper function to create a 3x3 square with value val centered at loc
def blot(map, loc, val):
    i, j = loc
    map[max(i-1, 0): i+2, max(j-1, 0): j+2] = val
    return map

class Visualizer:
    def __init__(self, seed):
        print("Visualizer is up and visualizing")
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
        self.relayer_map = self.get_relayer_base_map()
        self.runner_locations = []
        self.runner_attendance = 0
        self.runner_count = NUM_RUNNERS
        self.relayer_attendance = 0
        self.won = False

        # setup plotting
        fig, self.axes = plt.subplots(ncols = 2, figsize = (12, 8))
        plt.suptitle("Adelphon", fontsize = 28, y = 0.9)
        self.axes[0].set_title("True Game Map")
        self.true_im = self.axes[0].imshow(self.base_map, cmap = color_map, vmin = -1, vmax = interval[1] - 1, 
                                           aspect = 'equal', interpolation = 'none')
        self.relayer_im = self.axes[1].imshow(self.relayer_map, cmap = color_map, vmin = -1, vmax = interval[1] - 1, 
                                              aspect = 'equal', interpolation = 'none')
        self.axes[1].set_title("Total Relayer Knowledge")

        # plot tinted circles to visualize varius radii
        # need to reverse xy coords to fit matplotlib convention
        comm_radius_circles = [plt.Circle(loc[::-1], COMM_RADIUS, facecolor = NON_TERRAIN_COLOR_MAP['relayer'],
                               alpha = 0.3) for loc in self.game_instance.relayer_locations]
        for circle in comm_radius_circles:
            self.axes[0].add_artist(circle)
        self.kill_radius_circles = [plt.Circle(loc[::-1], KILL_RADIUS, facecolor = NON_TERRAIN_COLOR_MAP['animal'],
                                    alpha = 0.3) for loc in self.game_instance.animal_locations]
        for circle in self.kill_radius_circles:
            self.axes[0].add_artist(circle)
        self.treasure_radius_circles = [plt.Circle(loc[::-1], TREASURE_RADIUS, facecolor = NON_TERRAIN_COLOR_MAP['runner'],
                                        alpha = 0.3) for loc in self.game_instance.runner_start_locations]
        for circle in self.treasure_radius_circles:
            self.axes[0].add_artist(circle)

        # treasure
        hexagon = RegularPolygon(self.game_instance.treasure[::-1], 6, radius = 3, 
                                     facecolor = NON_TERRAIN_COLOR_MAP['treasure'])
        self.axes[0].add_artist(hexagon)

        # legend
        treasure = mlines.Line2D([], [], color = '#79F56E', marker = 'h', markersize = 5, label = 'Treasure')
        animal = mlines.Line2D([], [], color = '#ED1811', marker = 's', markersize = 5, label = 'Animal')
        runner = mlines.Line2D([], [], color = '#8C0E82', marker = 's', markersize = 5, label = 'Runner')
        relayer = mlines.Line2D([], [], color = '#11EDE6', marker = 's', markersize = 5, label = 'Relayer')
        flat_ground = mlines.Line2D([], [], color = '#0E5714', marker = 's', markersize = 5, label = 'Flat Ground')
        rocks = mlines.Line2D([], [], color = '#292828', marker = 'D', markersize = 5, label = 'Rocks')
        mud = mlines.Line2D([], [], color = '#452706', marker = 'D', markersize = 5, label = 'Mud')
        quicksand = mlines.Line2D([], [], color = '#EDCC55', marker = 'D', markersize = 5, label = 'Quicksand')
        blank = mlines.Line2D([], [], color = '#FFFFFF', marker = 'D', markersize = 5, label = 'Blank')
        fig.legend(handles = [treasure, animal, runner, relayer, flat_ground, rocks, mud, quicksand, blank],
                   title = "Legend", loc = 'lower right', bbox_to_anchor = (0.5, 0.5, 0.5, 0.5), fontsize = "9", fancybox = True)
        plt.ion()

        # tell spawner that everything has been set up correctly
        alert_spawn_process()

    # helper function that constructs base map with fixed treasure and relayer locations
    def get_base_map(self):
        map = self.game_instance.terrain.copy()
        for loc in self.game_instance.relayer_locations:
            map = blot(map, loc, RELAYER_INDEX)
        return map
    
    def get_relayer_base_map(self):
        map = np.full(MAP_DIMENSIONS, BLANK_INDEX, dtype=np.int8)
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
            # only overwrite blank parts of the map because all game objects are more important than terrain
            if self.relayer_map[i,j] == BLANK_INDEX:
                self.relayer_map[i, j] = t

    # runs one step of the visualizer by updating plots and resetting state
    def one_step(self):
        assert len(self.runner_locations) == self.runner_count

        # need to query so that visualizer's game instance is on the same page as the other game instances
        # i.e. we just want the update side effects of querying
        self.game_instance.query((0, 0), is_runner = False)
        map = self.add_animals(self.base_map.copy())
        for loc in self.runner_locations:
            map = blot(map, loc, RUNNER_INDEX)

        # update plots
        self.true_im.set_data(map)
        self.relayer_im.set_data(self.relayer_map)
        # update kill radius circles to stay centered at animal locations
        for circle, loc in zip(self.kill_radius_circles, self.game_instance.animal_locations):
            circle.set(center = loc[::-1])
         # update treasure radius circles to stay centered at runner locations
        for circle, loc in zip(self.treasure_radius_circles, self.runner_locations):
            circle.set(center = loc[::-1])
        plt.pause(0.01)

        # reset attendance and locations
        self.relayer_map = self.get_relayer_base_map()
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
        assert self.runner_attendance <= self.runner_count
        sock = key.fileobj
        data = key.data
        recv_data = sock.recv(VISUALIZER_TRANSMISSION_SIZE_LIMIT)
        if not recv_data:
            if not self.won:
                raise ConnectionError(f"Lost connection to socket on port {data.port}")
            else:
                # all good if you've already won since sys exits won't be perfectly in sync
                self.sel.unregister(sock)
                sock.close()
                return
        recv_data = recv_data.decode("utf-8").split("|")
        is_dead_runner = False
        if recv_data[0] == RUNNER_CODE:
            # special case for runner either dying or winning
            if len(recv_data) == 3:
                msg = recv_data[2]
                if msg == IM_DEAD:
                    is_dead_runner = True
                    id = int(recv_data[1])
                    # remove a circle for dead runner
                    self.treasure_radius_circles[-1].remove()
                    self.treasure_radius_circles.pop()
                    self.runner_count -= 1
                    if self.runner_count == 0:
                        print("GAME OVER: All runners have died")
                        # kill the parent (spawning process) and the visualizer itself
                        os.kill(os.getppid(), signal.SIGTERM)
                        sys.exit() # GAME OVER
                elif msg == I_WON:
                    self.runner_attendance += 1
                    self.won = True # GAME OVER but wait to let all runners know before killing this process
                else:
                    raise ValueError(f"Invalid msg: {msg}")
            # standard runner case
            else:
                self.runner_attendance += 1
                self.runner_locations.append(eval(recv_data[1]))
        elif recv_data[0] == RELAYER_CODE:
            self.relayer_attendance += 1
            # add current relayer's info to the master relayer map for this time step
            _, id, treasure_location, animal_locations, terrains, known_runner_locations = recv_data
            self.add_terrain(eval(terrains))
            if eval(treasure_location):
                self.relayer_map = blot(self.relayer_map, eval(treasure_location), TREASURE_INDEX)
            for animal in eval(animal_locations):
                self.relayer_map = blot(self.relayer_map, animal, ANIMAL_INDEX)
            for runner in eval(known_runner_locations):
                self.relayer_map = blot(self.relayer_map, runner, RUNNER_INDEX)
        else:
            raise Exception(f"Invalid data: {recv_data}")

        # once it has heard back from everyone, the visualizer should one step
        if self.runner_attendance == self.runner_count and self.relayer_attendance == NUM_RELAYERS:
            self.one_step()
        # respond back to all relayers and runners
        sock.send(MESSAGE_RECEIVED.encode("utf-8"))
        # close socket for this runner
        if is_dead_runner:
            self.sel.unregister(sock)
            sock.close()
        # kill the parent (spawning process) and the visualizer itself
        # after you've heard from and responded to all runners
        if self.runner_attendance == self.runner_count and self.won:
            os.kill(os.getppid(), signal.SIGTERM)
            sys.exit()

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