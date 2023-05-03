import matplotlib.pyplot as plt
import numpy as np
from game import TERRAIN_COLOR_MAP
from matplotlib.colors import ListedColormap

fig, ax = plt.subplots()
im = plt.imshow(np.ones((10, 30)), cmap = ListedColormap(list(TERRAIN_COLOR_MAP.values())))

plt.ion()
for _ in range(10):
    im.set_array(np.random.randint(4, size = (10,30)))
    plt.pause(0.01)
plt.ioff()
plt.show()