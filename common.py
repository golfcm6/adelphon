import numpy as np

PORT_START = 50000
VISUALIZER_PORT = PORT_START - 1
RUNNER_TRANSMISSION_SIZE_LIMIT = 32
RELAYER_TRANSMISSION_SIZE_LIMIT = 128
VISUALIZER_TRANSMISSION_SIZE_LIMIT = 8092
MESSAGE_RECEIVED = '1000'
TOO_FAR_AWAY = '20'
RUNNER_CODE = '0'
RELAYER_CODE = '1'
L1_SWEEP_MIN = 1
MAP_DIMENSIONS = (100, 100) # needs to be here to avoid circular import

# helper function to find the distance between two points
def distance(c1, c2):
    return np.linalg.norm(np.array(c1) - np.array(c2))

# check if a potential location is within the bounds of the map
def is_valid_location(location):
    x, y = location
    x_lim, y_lim = MAP_DIMENSIONS
    return (x >= 0 and x < x_lim) and (y >= 0 and y < y_lim)

# return new location after applying move
def apply_move(location, move):
    return location[0] + move[0], location[1] + move[1]

# generate a 3d grid where the ijth index contains [i, j]
def generate_coord_grid():
    i, j = np.meshgrid(np.arange(MAP_DIMENSIONS[0]), np.arange(MAP_DIMENSIONS[1]), indexing = 'ij')
    return np.dstack((i, j))

# divide rgb color value so that it falls in the range [0, 1]
def convert_color(rgb):
    return np.array(rgb) / 255

# helper function for sending information from runners to relayers or between relayers
# message convention: code|id|location|treasure|animal_coords|terrain_info
# treasure is empty string if not found, otherwise tuple of treasure coords
# animal_coords is a series of tuples (i, j) for animal locations, seperated by ! delimiter
# terrain_info is series of tuples (i, j, terrain_type), separated by ! delimiter
def prepare_info(terrains, coords, animals, treasure, sender_code, id, runner_locations):
    assert sender_code == RUNNER_CODE or sender_code == RELAYER_CODE
    limit = RUNNER_TRANSMISSION_SIZE_LIMIT if sender_code == RUNNER_CODE else RELAYER_TRANSMISSION_SIZE_LIMIT

    location_info = "!".join([str(location) for location in runner_locations])
    relevant_info = str(sender_code) + "|" + str(id) + "|" + location_info + "|"
    # treasure info logic
    if treasure: 
        relevant_info += str(treasure)
    relevant_info += "|"

    # animal info logic
    for animal in animals:
        # + 1 for the required pipe separator between animals and terrain
        if len(relevant_info) + len(str(animal)) + 1 > limit:
            break # relevant info string has gotten too long
        else:
            relevant_info += str(animal) + '!'
    # remove extra separator
    if relevant_info[-1] == '!':
        relevant_info = relevant_info[:-1]
    relevant_info += "|"

    # terrain info logic - encode tuple of x, y, terrain_type
    terrains, coords = terrains.flatten(), coords.reshape((-1, 2))
    coords = coords[np.argsort(terrains)[::-1]]
    terrains = np.sort(terrains)[::-1]
    for terrain, coord in zip(terrains, coords):
        info = (*coord, terrain)
        if len(relevant_info) + len(str(info)) > limit:
            break # relevant info string has gotten too long
        else:
            relevant_info += str(info) + '!'
    # remove extra separator
    if relevant_info[-1] == '!':
        relevant_info = relevant_info[:-1]

    return relevant_info