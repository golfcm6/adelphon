# Adelphon

## Final Project for CS 262

## By Ashlan Ahmed, Christy Jestin, Charles Ma

## How To Run

-   Start the program by running `python spawn.py [seed]` where seed is an optional integer argument. If you do not supply a seed, one will automatically be chosen for you. Use the seed to rerun the same game scenario.

## Update
-   We made a few updates after the due date:
    - Fixed a major bug where the animal positions in each process diverged due to a variable number of extra np.random calls in the runner processes (the processes each run their own game instance, and they only agree on the state of the game because they all use the same seed and make the same calls in the same order: extra random calls broke this alignment)
    - Implemented Dijkstra's algorithm for pathfinding and added complementary logic to remove frequent changes to the runners' targets
- **Our original submission is at [this commit](https://github.com/golfcm6/adelphon/tree/f978baeba21f88e1cc34cda047416389e4610f09)**

## The Game

-   The players are split into two groups: runners and relayers
-   Runners explore the map and collaborate to find a treasure
-   Relayers compile information received from the runners and each other and transmit it back out to runners
-   Runners must also avoid dangerous animals which will kill them if they're close enough
-   Runners must be within a communication radius in order to communicate with relayers: the radius is indicated by the large blue tinted circles around each relayer
-   Treasure must fall within a small treasure radius in order for the runners to see it: the radius is indicated by the small purple tinted circles around each runner
-   The game ends when either all runners have been killed or the treasure has been found
-   Relayers cannot move, be killed, or get the treasure themselves, since they're perched up in trees to facilitate communication: they can however see nearby objects just like the runners can
