from game import NUM_RELAYERS, NUM_RUNNERS
import sys
import subprocess
import time

PAUSE = 0.05 # need to wait a little between process starts to allow init calls to run

def main(seed):
    subprocess.Popen(["python", "visualizer.py", str(seed)])
    time.sleep(PAUSE)
    for i in range(NUM_RELAYERS):
        subprocess.Popen(["python", "relayer.py", str(seed), str(i)])
        time.sleep(PAUSE)
    for i in range(NUM_RUNNERS):
        subprocess.Popen(["python", "runner.py", str(seed), str(i)])
        time.sleep(PAUSE)

if __name__ == '__main__':
    assert len(sys.argv) == 2, "This program takes in one required argument seeds"
    main(int(sys.argv[1]))