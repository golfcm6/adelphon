import numpy as np
import sys
import socket
import subprocess, signal
import time

from game import NUM_RELAYERS, NUM_RUNNERS
from common import SPAWN_PORT, IM_UP

def main(seed):
    # wait for a connection from each process before spawning the next one
    # each connection will be at the end of the process's init function
    # this will prevent processes from getting ahead of each other and causing connection errors
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((socket.gethostbyname(socket.gethostname()), SPAWN_PORT))
    sock.listen()
    child_processes = []
    child_processes.append(subprocess.Popen(["python", "visualizer.py", str(seed)]))
    wait_for_connection(sock, "visualizer")
    for i in range(NUM_RELAYERS):
        child_processes.append(subprocess.Popen(["python", "relayer.py", str(seed), str(i)]))
        wait_for_connection(sock, f"relayer {i}")
    for i in range(NUM_RUNNERS):
        child_processes.append(subprocess.Popen(["python", "runner.py", str(seed), str(i)]))
        wait_for_connection(sock, f"runner {i}")
    sock.close()

    # cycle so that you can accept KeyboardInterrupts and pass them down to child processes
    while True:
        pass

# helper function to wait for a single connection to the given socket
def wait_for_connection(sock, process_name):
    conn, _ = sock.accept()
    if not conn.recv(len(IM_UP)):
        raise ConnectionError(f"Invalid connection from {process_name}")
    conn.close()

if __name__ == '__main__':
    assert len(sys.argv) <= 2, \
        "This program only takes in one optional argument: seed (a seed will be chosen randomly if not provided)"
    if len(sys.argv) == 2:
        main(int(sys.argv[1]))
    else:
        max_int = np.iinfo(np.int32).max
        seed = np.random.randint(max_int)
        print(f"This run uses the seed {seed}")
        main(seed)