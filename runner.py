import sys
import socket
import numpy as np

from game import *
from common import *

class Runner:
    def __init__(self, seed, id):
        self.id = id
        self.game_instance = Game(seed)
        self.alive = True
        self.won = False
        self.relayer_locations = []
        self.location = self.game_instance.runner_start_locations[self.id]
        self.wait_time = 0
        self.treasure_location = None
        self.terrains = np.full(MAP_DIMENSIONS, -1, dtype=np.int8)
        self.direction = (0, 0)

        # socket setup
        self.address = socket.gethostbyname(socket.gethostname())
        self.sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(NUM_RELAYERS)]
        for i in range(NUM_RELAYERS):
            self.sockets[i].connect((self.address, port_start + i))

    def one_step(self):
        if self.wait_time > 0:
            self.wait_time -= 1 # keep waiting to move
        else:
            self.location = apply_move(self.location, self.direction)

        # query the game map and update your own state
        game_state = self.game_instance.query(self.location)
        self.alive = game_state.alive
        self.won = game_state.won

        # game is over for this runner
        if not self.alive or self.won:
            return
        
        # only start waiting if you're not already waiting
        if self.wait_time == 0:
            self.wait_time = game_state.wait_time
        (terrains, coords), animals, treasure = self.local_view
        relevant_info = prepare_info(terrains, coords, animals, treasure, RUNNER_CODE, self.id, [self.location])

        # send info to nearby relayers and a placeholder message to all others
        for i in range(NUM_RELAYERS):
            if distance(self.game_instance.relayer_locations[i], self.location) <= COMM_RADIUS:
                self.sockets[i].send(relevant_info.encode('utf-8'))
            else:
                self.sockets[i].send(TOO_FAR_AWAY.encode('utf-8'))
    
        # logic for receiving relayer responses
        received_response = False
        for i in range(NUM_RELAYERS):
            recv_data = self.sockets[i].recv(RUNNER_TRANSMISSION_SIZE_LIMIT)
            if not recv_data:
                raise ConnectionError(f"Lost connection to relayer {i}")
            data = recv_data.decode("utf-8")
            
            # too far away message should only ever be echoed i.e. you shouldn't ever hear it from a relayer
            # that is close enough
            if data == TOO_FAR_AWAY:
                assert distance(self.game_instance.relayer_locations[i], self.location) > COMM_RADIUS
            
            # this is case of relayer in range but you've already listened to another relayer
            # would put the logic for check if multiple relayers have same content/are lying here
            elif received_response:
                pass

            # first relayer response with data
            else:
                received_response = True
                _, relayer_treasure, relayer_target, relayer_animals, relayer_terrain = data.split("|")
                # update internal understanding from relayer info

                # updated treasure_location, but also target_location will be treasure
                if relayer_treasure != "":
                    self.treasure_location = eval(relayer_treasure)

                # parse relayer_terrain and update internal terrain map (copy relayer map)
                if relayer_terrain:
                    relayer_terrain = relayer_terrain.split('!')
                    for terrain in relayer_terrain:
                        i, j, terrain_type = eval(terrain)
                        if self.terrains[i][j] == -1:
                            self.terrains[i][j] = terrain_type
                        else:
                            if self.terrains[i][j] != terrain_type:
                                # TODO: anomaly/liar
                                pass

                # MOVE STRATEGY V0 (simple)
                #TODO: logic to make use of relayer_id if detects lie from a relayer
                # find the adjacent square that is closest to being in line with the target
                x, y = self.location
                target_x, target_y = eval(relayer_target)
                theta = np.rint(np.arctan2(target_y - y, target_x - x) / (np.pi / 4)) * (np.pi / 4)
                move = np.rint([np.cos(theta), np.sin(theta)])
                proposed_loc = apply_move(self.location, move)

                # if quicksand or animal in move, try pi/4 counterclockwise - if all moves bad stay put                
                for _ in range(8):
                    min_dist = min(distance(animal_loc, proposed_loc) for animal_loc in relayer_animals)
                    if min_dist > KILL_RADIUS and relayer_terrain[proposed_loc] != Terrain.QUICKSAND:
                        break
                    theta += (np.pi / 4)
                    move = np.rint([np.cos(theta), np.sin(theta)])
                    proposed_loc = apply_move(self.location, move)
        
        # if not in range of any relayer, make a move based on your own view
        if not received_response:
            theta = np.random.randint(8) * (np.pi / 4)
            move = np.rint([np.cos(theta), np.sin(theta)])
        
        self.direction = move        

def main(seed, id):
    runner = Runner(seed, id)
    while True:
        runner.one_step()
        if not runner.alive:
            print("This runner has died")
            break
        if runner.won:
            print("This runner has won")
            break

if __name__ == '__main__':
    assert len(sys.argv) == 3, "The runner program takes 2 required arguments: seed and id"
    main(int(sys.argv[1]), int(sys.argv[2]))
