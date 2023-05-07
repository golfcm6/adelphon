import sys
import os
import socket
import subprocess, signal

from game import NUM_RELAYERS, NUM_RUNNERS
from common import SPAWN_PORT, IM_UP, DEFAULT_SEED

def main(seed=DEFAULT_SEED):
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

def wait_for_connection(sock, process_name):
    conn, _ = sock.accept()
    if not conn.recv(len(IM_UP)):
        raise ConnectionError(f"Invalid connection from {process_name}")
    conn.close()

if __name__ == '__main__':
    # seed is optional, has default
    if len(sys.argv) == 2:
        main(int(sys.argv[1]))
    else:
        main()