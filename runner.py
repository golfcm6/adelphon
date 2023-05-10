import sys
import socket
import numpy as np
from queue import PriorityQueue

from game import *
from common import *
from visualizer import BLANK_INDEX

NEW_TARGET_RANGE = 8

class Runner:
    def __init__(self, seed, id):
        self.id = id
        self.game_instance = Game(seed)
        print(f"Runner {self.id} is up and running")
        self.alive = True
        self.won = False
        self.relayer_locations = []
        self.location = self.game_instance.runner_start_locations[self.id]
        self.wait_time = self.game_instance.runner_start_wait_times[self.id]
        self.treasure_location = None
        self.terrains = np.full(MAP_DIMENSIONS, BLANK_INDEX, dtype=np.int8)
        self.next_location = self.location # initialized this way because of how runner logic sequence works
        self.target_location = None
        self.animal_locations = set()
        self.been_here = np.full(MAP_DIMENSIONS, False)

        # socket setup
        self.address = socket.gethostbyname(socket.gethostname())
        self.sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(NUM_RELAYERS)]
        for i in range(NUM_RELAYERS):
            self.sockets[i].connect((self.address, PORT_START + i))
        # socket for visualizer
        self.visualizer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.visualizer_socket.connect((self.address, VISUALIZER_PORT))

        # tell spawner that everything has been set up correctly
        alert_spawn_process()

    # helper function to get the weight for an edge (v, u)
    # in this case it's just the wait time of v
    def get_weight(self, v):
        # add one because you always need one timestep to just get there
        return (WAIT_TIME_MAP[Terrain(self.terrains[v])] if self.terrains[v] != BLANK_INDEX else 0) + 1

    # helper function to find the valid neighbors of a vertex
    def neighbors(self, vertex):
        i, j = vertex
        potential = [(i + di, j + dj) for di in range(-1, 2) for dj in range(-1, 2)]
        return [pair for pair in potential if is_valid_location(pair) and pair != vertex]

    # given edge weights and a target location, run Dijkstra's algorithm with current location as the source
    def dijkstra(self):
        assert self.location != self.target_location, f"{self.id}"
        # init data structures
        dists = dict()
        dists[self.target_location] = 0
        next = dict()
        visited = set()
        # note that we won't be deleting elements or overwriting priority
        # instead we'll be skipping elements with stale priorities
        # e.g. if (1, u) was added to the queue after (2, u), then we'll skip the second occurrence
        # this is tracked via the set visited
        queue = PriorityQueue()
        queue.put((0, self.target_location))

        while True:
            u = queue.get()[1]
            # skip stale entries
            if u in visited:
                continue
            visited.add(u)
            # we've constructed a path from our current location to the target location so we're done
            if u == self.location:
                assert next[self.location] in self.neighbors(self.location)
                return next[self.location]
            for v in self.neighbors(u):
                if v not in visited:
                    alt_dist = self.get_weight(v) + dists[u]
                    if (v not in dists) or (alt_dist < dists[v]):
                        dists[v] = alt_dist
                        next[v] = u
                        queue.put((alt_dist, v))

    def one_step(self):
        self.animal_locations = set() # reset set before getting new animal locations
        if self.wait_time == 0:
            self.location = self.next_location

        self.been_here[self.location] = True
        # query the game map and update your own state
        game_state = self.game_instance.query(self.location, is_runner = True)
        self.alive = game_state.alive
        self.won = game_state.won

        # game is over for this runner, tell all relayers and visualizer you've died/have won
        if (not self.alive) or self.won:
            if not self.alive:
                print("Runner " + str(self.id) + " has died")
            if self.won:
                print("Runner " + str(self.id) + " has won")
            msg = '|'.join([RUNNER_CODE, str(self.id), (I_WON if self.won else IM_DEAD)])
            for i in range(NUM_RELAYERS):
                self.sockets[i].send(msg.encode('utf-8'))
            self.visualizer_socket.send(msg.encode('utf-8'))
            self.visualizer_socket.recv(len(MESSAGE_RECEIVED))
            return

        # potentially start waiting if you're not already waiting
        if self.wait_time == 0:
            self.wait_time = game_state.wait_time
        # can decrement counter now if you're already waiting
        else:
            self.wait_time -= 1
        (terrains, coords), animals, treasure = game_state.local_view
        self.animal_locations.update(animals)
        if treasure:
            self.treasure_location = treasure
        i, j = coords[:,:,0], coords[:,:,1]
        self.terrains[i, j] = terrains
        relevant_info = prepare_info(terrains, coords, animals, treasure, RUNNER_CODE, self.id, [self.location])

        # send info to nearby relayers and a placeholder message to all others
        for i in range(NUM_RELAYERS):
            if distance(self.game_instance.relayer_locations[i], self.location) <= COMM_RADIUS:
                self.sockets[i].send(relevant_info.encode('utf-8'))
            else:
                self.sockets[i].send(TOO_FAR_AWAY.encode('utf-8'))
        self.visualizer_socket.sendall((RUNNER_CODE + "|" + str(self.location)).encode("utf-8"))
        self.visualizer_socket.recv(len(MESSAGE_RECEIVED))
    
        # logic for receiving relayer responses
        already_received_response = False
        for i in range(NUM_RELAYERS):
            recv_data = self.sockets[i].recv(RUNNER_TRANSMISSION_SIZE_LIMIT)
            if not recv_data:
                raise ConnectionError(f"Lost connection to relayer {i}")
            data = recv_data.decode("utf-8")

            # exit once you've heard that you've won from a relayer
            if data == WE_WON:
                sys.exit()
            # too far away message should only ever be echoed i.e. you shouldn't ever hear
            #  it from a relayer that is close enough
            elif data == TOO_FAR_AWAY:
                assert distance(self.game_instance.relayer_locations[i], self.location) > COMM_RADIUS
            elif not already_received_response:
                already_received_response = True
                _, treasure, target, animals, terrain = data.split("|")
                # parse info from relayer
                assert target, "relayer should always send a valid target"
                target = eval(target)
                # reject target locations you've already been to
                if not self.been_here[target]:
                    self.target_location = target
                if animals:
                    self.animal_locations.update([eval(a) for a in animals.split('!')])
                if treasure:
                    self.treasure_location = eval(treasure)
                if terrain:
                    for terra in terrain.split('!'):
                        i, j, terrain_type = eval(terra)
                        self.terrains[i][j] = terrain_type

        # only set a new target if you don't have one or if you're already there
        if (not self.target_location) or (self.target_location == self.location):
            i, j = self.location
            new_target = self.location
            # randomly go towards edges of map; retry in case you go off the map
            while new_target == self.location:
                options = [NEW_TARGET_RANGE, -NEW_TARGET_RANGE]
                # random movement that's biased towards center if you're on edges and fair coin toss in middle
                di = np.random.choice(options, p = np.array([MAP_DIMENSIONS[0] - 1 - i, i]) / (MAP_DIMENSIONS[0] - 1))
                dj = np.random.choice(options, p = np.array([MAP_DIMENSIONS[1] - 1 - j, j]) / (MAP_DIMENSIONS[1] - 1))
                new_target = clip_location((i + di, j + dj))
            self.target_location = new_target
        # target should always be treasure if you know where it is
        if self.treasure_location:
            self.target_location = self.treasure_location
        self.next_location = self.dijkstra()

def main(seed, id):
    runner = Runner(seed, id)
    try:
        while True:
            runner.one_step()
            if (not runner.alive) or runner.won:
                break
    except KeyboardInterrupt:
        sys.exit()

if __name__ == '__main__':
    assert len(sys.argv) == 3, "The runner program takes 2 required arguments: seed and id"
    main(int(sys.argv[1]), int(sys.argv[2]))
