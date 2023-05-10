import socket
import numpy as np

# starting port for relayer and runner facing sockets
PORT_START = 50000
# special ports for spawn process and visualizer process
VISUALIZER_PORT = PORT_START - 1
SPAWN_PORT = PORT_START - 2
RUNNER_TRANSMISSION_SIZE_LIMIT = 32
RELAYER_TRANSMISSION_SIZE_LIMIT = 128
VISUALIZER_TRANSMISSION_SIZE_LIMIT = 8092
IM_UP = '19'
MESSAGE_RECEIVED = '10'
TOO_FAR_AWAY = '20'
IM_DEAD = '7'
I_WON = '91'
WE_WON = '32'
RUNNER_CODE = '0'
RELAYER_CODE = '1'
LINF_SWEEP_MIN = 2
MAP_DIMENSIONS = (100, 100) # needs to be here to avoid circular import

assert len(MESSAGE_RECEIVED) == len(WE_WON), "these messages need to be the same length for code simplicity"

# helper function to find the distance between two points
def distance(c1, c2):
    return np.linalg.norm(np.array(c1) - np.array(c2))

# check if a potential location is within the bounds of the map
def is_valid_location(location):
    x, y = location
    x_lim, y_lim = MAP_DIMENSIONS
    return (x >= 0 and x < x_lim) and (y >= 0 and y < y_lim)

# clip location to be on the map
def clip_location(location):
    x, y = location
    x_lim, y_lim = MAP_DIMENSIONS
    # order of min, max is arbitrary
    return (min(max(0, x), x_lim - 1), min(max(0, y), y_lim - 1))

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

# connects to spawn process to let it know that you're good to go
# this prevents processes from getting ahead of each other and causing connection errors
def alert_spawn_process():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((socket.gethostbyname(socket.gethostname()), SPAWN_PORT))
    sock.send(IM_UP.encode('utf-8'))
    sock.close()
