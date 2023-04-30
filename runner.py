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

        # socket setup
        self.address = socket.gethostbyname(socket.gethostname())
        self.sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(NUM_RELAYERS)]
        for i in range(NUM_RELAYERS):
            self.sockets[i].connect((self.address, port_start + i))

    def one_step(self):
        # TODO: logic for deciding where to move
        if self.wait_time > 0:
            self.wait_time -= 1 # keep waiting to move
        else:
            self.location = None

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
        relevant_info = self.prepare_info(game_state.local_view)

        # send info to nearby relayers and a placeholder message to all others
        for i in range(NUM_RELAYERS):
            if distance(self.game_instance.relayer_locations[i], self.location) <= COMM_RADIUS:
                self.sockets[i].send(relevant_info.encode('utf-8'))
            else:
                self.sockets[i].send(TOO_FAR_AWAY.encode('utf-8'))

        # logic for receiving relayer responses
        for i in range(NUM_RELAYERS):
            if distance(self.game_instance.relayer_locations[i], self.location) <= COMM_RADIUS:
                # logic for sending relevant info to nearby
                data = self.sockets[i].recv(RUNNER_TRANSMISSION_SIZE_LIMIT)
                data = data.decode('utf-8')
                # TODO: process data

    # prepare info to transmit to nearby relayers
    # convention: runner_code|id|treasure|animals|terrain (we prioritize information in this same order)
    def prepare_info(self, local_view):
        (terrains, coords), animals, treasure = local_view
        relevant_info = RUNNER_CODE + "|" + self.id + "|"
        # treasure info logic
        if treasure: 
            relevant_info += str(treasure)
        relevant_info += "|"

        # animal info logic
        for animal in animals:
            # + 1 for the required pipe separator between animals and terrain
            if len(relevant_info) + len(str(animal)) + 1 > RUNNER_TRANSMISSION_SIZE_LIMIT:
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
            if len(relevant_info) + len(str(info)) > RUNNER_TRANSMISSION_SIZE_LIMIT:
                break # relevant info string has gotten too long
            else:
                relevant_info += str(terrain) + '!'
        # remove extra separator
        if relevant_info[-1] == '!':
            relevant_info = relevant_info[:-1]

        return relevant_info

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
