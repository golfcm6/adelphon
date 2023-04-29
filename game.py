from collections import namedtuple
from enum import Enum
import numpy as np

MAP_DIMENSIONS = (100, 100)
NUM_ANIMALS = 5
ANIMAL_RADIUS = 10
TERRAIN_RANGE = 8 # side length of terrain block
TREASURE_RADIUS = 2
ANIMAL_RANGE = 1
ANIMAL_DIRECTION_CHANGE_PROB = 0.15
NUM_RELAYERS = 2
NUM_RUNNERS = 4

class Terrain(Enum):
    FLAT_GROUND = 0
    ROCKS = 1
    MUD = 2
    QUICKSAND = 3

WAIT_TIME_MAP = {
    Terrain.FLAT_GROUND: 0, 
    Terrain.ROCKS: 1, 
    Terrain.MUD: 3, 
    Terrain.QUICKSAND: 10
}

TERRAIN_PROBABILITIES = [0.55, 0.25, 0.15, 0.05]
assert len(Terrain) == len(TERRAIN_PROBABILITIES)
assert abs(sum(TERRAIN_PROBABILITIES) - 1) < 1e-8, "probabilities must sum to 1"

GameState = namedtuple('GameState', ['alive', 'won', 'wait_time', 'local_view'])
LocalView = namedtuple("LocalView", ['terrain', 'animals', 'treasure'])

# helper function to find the distance between two points
def distance(c1, c2):
    return np.linalg.norm(np.array(c1) - np.array(c2))

class Game:
    def __init__(self, seed):
        np.random.seed(seed)
        self.animal_locations = tuple(self.random_coord_helper() for _ in range(NUM_ANIMALS))
        self.animal_movements = tuple(self.random_movement_helper() for _ in range(NUM_ANIMALS))
        self.treasure = self.random_coord_helper()
        self.terrain = np.random.choice(len(Terrain), MAP_DIMENSIONS, p = TERRAIN_PROBABILITIES).astype(np.int8)

    def query(self, location):
        if location == self.treasure:
            return GameState(alive = True, won = True, wait_time = 0, local_view = None)  # treasure found and game won

        if location in self.animal_locations:
            return GameState(alive = False, won = False, wait_time = 0, local_view = None) # death (killed by an animal)

        # any other outcome means you are still alive and get local_view
        # convention: animal_radius > terrain_radius >> treasure_radius
        # decision: radius for treasure and animals, surrounding blocks (box) for terrain

        # give local terrain BOX with side length TERRAIN_RANGE
        x, y = location
        half = TERRAIN_RANGE // 2
        local_terrain = self.terrain[max(0, y - half) : y + half + 1, max(0, x - half) : x + half + 1]
        local_animals = [animal for animal in self.animal_locations if distance(animal, location) <= ANIMAL_RADIUS]
        local_treasure = self.treasure if (distance(location, self.treasure) <= TREASURE_RADIUS) else None

        local_view = LocalView(terrain = local_terrain, animals = local_animals, treasure = local_treasure)
        current_terrain = Terrain(self.terrain[x, y])
        return GameState(alive = True, won = False, wait_time = WAIT_TIME_MAP[current_terrain], local_view = local_view)

    # update one animal's location and movement pattern
    def update_single_animal(self, animal_loc, animal_movement):
        # randomly change direction with some probability for the next move
        new_dir = animal_movement
        if (np.random.rand() < ANIMAL_DIRECTION_CHANGE_PROB):
            while new_dir == animal_movement:
                new_dir = self.random_movement_helper()

        # apply the movement based off current move tuple
        new_loc = self.apply_move(animal_loc, new_dir)
        # if not a valid move, update the movement pattern randomly and try again
        while not self.check_location_valid(new_loc):
            new_dir = self.random_movement_helper()
            new_loc = self.apply_move(animal_loc, new_dir)

        return new_loc, new_dir

    # apply updates to all animal's location and movement patterns
    def update_animals(self):
        new_pairs = [self.update_single_animal(*pair) for pair in zip(self.animal_locations, self.animal_movements)]
        self.animal_locations, self.animal_movements = list(zip(*new_pairs))

    # randomly chooses a location on the map
    def random_coord_helper(self):
        return np.random.randint(MAP_DIMENSIONS[0]), np.random.randint(MAP_DIMENSIONS[1])

    # randomly chooses magnitude of animal movement based on ANIMAL_RANGE
    def random_movement_helper(self):
        return np.random.randint(-ANIMAL_RANGE, ANIMAL_RANGE), np.random.randint(-ANIMAL_RANGE, ANIMAL_RANGE)

    # return new location after applying move
    def apply_move(self, location, move):
        return location[0] + move[0], location[1] + move[1]

    # check if a potential location is within the bounds of the map
    def check_location_valid(self, location):
        x, y = location
        x_lim, y_lim = MAP_DIMENSIONS
        return (x >= 0 and x < x_lim) and (y >= 0 and y < y_lim)