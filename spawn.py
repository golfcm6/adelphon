from game import NUM_RELAYERS, NUM_RUNNERS
import sys
import subprocess
import socket
from common import SPAWN_PORT, IM_UP

def main(seed):
    # wait for a connection from each process before spawning the next one
    # each connection will be at the end of the process's init function
    # this will prevent processes from getting ahead of each other and causing connection errors
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((socket.gethostbyname(socket.gethostname()), SPAWN_PORT))
    sock.listen()
    subprocess.Popen(["python", "visualizer.py", str(seed)])
    wait_for_connection(sock, "visualizer")
    for i in range(NUM_RELAYERS):
        subprocess.Popen(["python", "relayer.py", str(seed), str(i)])
        wait_for_connection(sock, f"relayer {i}")
    for i in range(NUM_RUNNERS):
        subprocess.Popen(["python", "runner.py", str(seed), str(i)])
        wait_for_connection(sock, f"runner {i}")
    sock.close()

def wait_for_connection(sock, process_name):
    conn, _ = sock.accept()
    if not conn.recv(len(IM_UP)):
        raise ConnectionError(f"Invalid connection from {process_name}")
    conn.close()

if __name__ == '__main__':
    assert len(sys.argv) == 2, "This program takes in one required argument seeds"
    main(int(sys.argv[1]))