from game import NUM_RELAYERS, NUM_RUNNERS
import sys
import subprocess


def main(seed):
    subprocess.Popen(["python", "visualizer.py", str(seed)])
    for i in range(NUM_RELAYERS):
        subprocess.Popen(["python", "relayer.py", str(seed), str(i)])
    for i in range(NUM_RUNNERS):
        subprocess.Popen(["python", "runner.py", str(seed), str(i)])

if __name__ == '__main__':
    assert len(sys.argv) == 2, "This program takes in one required argument seeds"
    main(int(sys.argv[1]))