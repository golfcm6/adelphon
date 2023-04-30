import numpy as np

port_start = 50000
RUNNER_TRANSMISSION_SIZE_LIMIT = 2048
RELAYER_TRANSMISSION_SIZE_LIMIT = 8192
TOO_FAR_AWAY = "69"
RUNNER_CODE = "0"
RELAYER_CODE = "1"

# helper function to find the distance between two points
def distance(c1, c2):
    return np.linalg.norm(np.array(c1) - np.array(c2))

def generate_coord_grid(map_dimensions):
    i, j = np.meshgrid(np.arange(map_dimensions[0]), np.arange(map_dimensions[1]), indexing = 'ij')
    return np.dstack((i, j))