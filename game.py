from collections import namedtuple, OrderedDict
from enum import Enum
import numpy as np

from common import *


NUM_ANIMALS = 5
ANIMAL_RADIUS = 10
KILL_RADIUS = 5
TERRAIN_RANGE = 8 # side length of terrain block
TREASURE_RADIUS = 3
COMM_RADIUS = 20
ANIMAL_RANGE = 1
ANIMAL_DIRECTION_CHANGE_PROB = 0.15
ANIMAL_STAGNATE_PROB = 0.2
NUM_RELAYERS = 5
NUM_RUNNERS = 8
# we want to place relayers within some smaller square concentric to each grid block
# this value determines how small that smaller square is relative to the grid block
RELAYER_GRID_CENTER_RATIO = 0.5
assert RELAYER_GRID_CENTER_RATIO > 0 and RELAYER_GRID_CENTER_RATIO <= 1

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

WAIT_TIME_MAP_INVERSE = {v:k for k,v in WAIT_TIME_MAP.items()}

TERRAIN_COLOR_MAP = OrderedDict([
    (Terrain.FLAT_GROUND, convert_color([14, 87, 20])),
    (Terrain.ROCKS, convert_color([41, 40, 40])),
    (Terrain.MUD, convert_color([69, 39, 6])),
    (Terrain.QUICKSAND, convert_color([237, 204, 85]))
])

TERRAIN_PROBABILITIES = [0.5, 0.25, 0.2, 0.05]
assert len(Terrain) == len(TERRAIN_PROBABILITIES)
assert abs(sum(TERRAIN_PROBABILITIES) - 1) < 1e-8, "probabilities must sum to 1"
assert set(WAIT_TIME_MAP.keys()) == set(Terrain) and set(TERRAIN_COLOR_MAP.keys()) == set(Terrain)

MAINTAIN_TERRAIN_TYPE_PROB = 0.7

GameState = namedtuple('GameState', ['alive', 'won', 'wait_time', 'local_view'])
LocalView = namedtuple("LocalView", ['terrain', 'animals', 'treasure'])

class Game:
    def __init__(self, seed):
        np.random.seed(seed)
        self.relayer_locations = self.relayer_init()
        self.runner_start_locations = [self.random_coord_helper() for _ in range(NUM_RUNNERS)]
        self.animal_locations = tuple(self.random_coord_helper() for _ in range(NUM_ANIMALS))
        self.animal_movements = tuple(self.random_movement_helper() for _ in range(NUM_ANIMALS))
        self.treasure = self.random_coord_helper()
        self.terrain = self.generate_terrain_grid()
        self.coords = generate_coord_grid()
        runner_start_terrains = [Terrain(self.terrain[loc]) for loc in self.runner_start_locations]
        self.runner_start_wait_times = [WAIT_TIME_MAP[terrain] for terrain in runner_start_terrains]

    def query(self, location, is_relayer):
        # only runners can find treasure or get killed by animals
        if not is_relayer:
            if location == self.treasure:
                return GameState(alive = True, won = True, wait_time = 0, local_view = None)  # treasure found and game won

            for animal_location in self.animal_locations:
                # death (killed by an animal)
                if distance(location, animal_location) <= KILL_RADIUS:
                    return GameState(alive = False, won = False, wait_time = 0, local_view = None)

        # update animals on every timestep
        self.update_animals()

        # any other outcome means you are still alive and get local_view
        # convention: animal_radius > terrain_radius >> treasure_radius
        # decision: radius for treasure and animals, surrounding blocks (box) for terrain

        # give local terrain BOX with side length TERRAIN_RANGE
        i, j = location
        half = TERRAIN_RANGE // 2
        local_terrain = self.terrain[max(0, i - half) : i + half + 1, max(0, j - half) : j + half + 1]
        local_coords = self.coords[max(0, i - half) : i + half + 1, max(0, j - half) : j + half + 1]
        local_animals = [animal for animal in self.animal_locations if distance(animal, location) <= ANIMAL_RADIUS]
        local_treasure = self.treasure if (distance(location, self.treasure) <= TREASURE_RADIUS) else None

        local_view = LocalView(terrain = (local_terrain, local_coords), animals = local_animals, treasure = local_treasure)
        current_terrain = Terrain(self.terrain[i, j])
        return GameState(alive = True, won = False, wait_time = WAIT_TIME_MAP[current_terrain], local_view = local_view)

    # update one animal's location and movement pattern
    def update_single_animal(self, animal_loc, animal_movement):
        # randomly stay in the same location with some probability
        if np.random.rand() < ANIMAL_STAGNATE_PROB:
            return animal_loc, animal_movement
        # randomly change direction with some probability for the next move
        new_dir = animal_movement
        if np.random.rand() < ANIMAL_DIRECTION_CHANGE_PROB:
            while new_dir == animal_movement:
                new_dir = self.random_movement_helper()

        # apply the movement based off current move tuple
        new_loc = apply_move(animal_loc, new_dir)
        # if not a valid move, update the movement pattern randomly and try again
        while not is_valid_location(new_loc):
            new_dir = tuple(-val for val in new_dir) # bounce off the edges of the map
            new_loc = apply_move(animal_loc, new_dir)

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
        return np.random.randint(-ANIMAL_RANGE, ANIMAL_RANGE + 1), np.random.randint(-ANIMAL_RANGE, ANIMAL_RANGE + 1)

    def generate_terrain_grid(self):
        ilim, jlim = MAP_DIMENSIONS
        terra = np.ones(MAP_DIMENSIONS, dtype = np.int8)
        # go up each diagonal
        for d in range(1, ilim + jlim):
            for i in reversed(range(min(ilim, d))):
                j = d - 1 - i
                # stop before you go past the right end of the map
                if j >= jlim:
                    break
                # the adjacent squares on previous diagonal and previous square on current 
                # diagonal are this square's neighbors
                potential_neighbors = [(i+1, j-1), (i, j-1), (i-1, j)]
                neighboring_terrain = [terra[loc] for loc in potential_neighbors if is_valid_location(loc)]
                # keep the same type of terrain with some probability
                if neighboring_terrain and np.random.rand() < MAINTAIN_TERRAIN_TYPE_PROB:
                    terra[i, j] = np.random.choice(neighboring_terrain)
                else:
                    terra[i, j] = np.random.choice(len(Terrain), p = TERRAIN_PROBABILITIES)
        return terra

    def relayer_init(self):
        ratio = MAP_DIMENSIONS[0] / MAP_DIMENSIONS[1]
        assert ratio >= 0.8 and ratio <= 1.2, \
            "The ratio of the side lengths should be somewhat close to 1 for this init method to be reasonable"
        relayer_locations = []
        n = int(np.sqrt(NUM_RELAYERS)) # we're imposing an n x n grid over map
        s1, s2 = MAP_DIMENSIONS[0] / n, MAP_DIMENSIONS[1] / n
        d = (1 - RELAYER_GRID_CENTER_RATIO) / 2 # offset to create a smaller square between [d, 1-d] instead of [0, 1]
        for i in range(n):
            for j in range(n):
                # randomly generate the relayer inside corresponding grid cell
                x = np.random.randint(int(s1 * (i + d)), int(s1 * (i + 1 - d)))
                y = np.random.randint(int(s2 * (j + d)), int(s2 * (j + 1 - d)))
                relayer_locations.append((x, y))
        # randomly choose coordinates for extra positions
        relayer_locations.extend([self.random_coord_helper() for _ in range(NUM_RELAYERS - n ** 2)])
        return relayer_locations