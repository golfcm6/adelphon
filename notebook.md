# Engineering Notebook - CS 262 Final Project

We built a game, Adelphon, where a team of runners and navigators collectively communicate to navigate a foreign map to find a treasure, while avoiding deadly animals and dangerous terrain.

This is our engineering notebook outlining key design decisions made while building Adelphon. For a more in-depth understanding to the project, find a pdf of the full report attached to this repo.

## Design Decisions
We decided to put a spin on existing map exploration/civilization games by creating a system where all players worked towards the same goal. Traditionally, games like Polytopia with multiple explorers of a map do not communicate and are pitted against each other. By uniting all players of Adelphon onto one team, we obtained the first pillar of distributed systems, communication.

#### Separate Game Instances
We also decided to make the game in a way such that there is no master/central game instance that all players are querying/referring to. This is for two reasons: the first being to employ characteristics of distributed systems where there is no single point of failure and that each relayer can act like a separate server with the current game instance operating independently. The second is to make this game more realistic: in a real world where we had some form of communicative exploration of an unknown area, there would be no central instance runners could query. However, relayers in a real world scenario would all share an independent view of the same area.

#### Communication
Our design decisions on communication were rather straightforward. We programmatically generated sockets for each relayer to communicate with each other, as well as all runners to communicate with every relayer. The visualizer and spawn processes also all had sockets talking to every game player to receive updates on the status of the game.

We developed a few different standards for how different characters/processes communicated over the course of the game. Relayers and runners shared mostly the same standard as they were communicate variants of the same information (and in doing so, we were able to abstract a function to prepare info for the wire that was shared by both players).

To simulate another real life aspect of the game, we incorporated transmission limits for runners and relayers such that players didn't have unlimited ability to transmit all the information they saw. Our logic behind this decision was to make the game not too simple for relayers in terms of how quickly they could aggregate info, as well as testing the limits of communication across different systems.

#### Timesteps
One of the biggest design decisions we had to make was how to keep each machine in sync with the others as the game progressed. While we played around with letting each player operate on their own time, syncing runners with relayers and storing an internal timestamp + updating in bulk when behind, this proved extremely complicated for the game mechanics we had developed.
Our game naturally lended itself to synced timestamps, where all runners and relayers would follow a set of ordered instructions and wait for all players to be on the same page before completing that same set of instructions again. Over the course of 1 timestep, runners would make a move and communicate info to all relayers, relayers would sync and recommend ideal locations to all runners, and for runners to take the recommendation and determine the ideal placement for its next move.
We kept internal counters of communication across relayers for them to know when to change to different phases of the timestep. One interesting feature we added to make such synchronous syncs work was implementing "heartbeat" transmissions that runners would send to relayers not within range to let them know they've made their move but not relay any information. That way, relayers could truly know when all runners were in sync and they could converse with the rest of the relayers.


## Challenges

One challenge we encountered was getting the communication set up among relayers and runners. We struggled to determine how many sockets we’d need and how to handle a protocol for creating and connecting the sockets. We solved this by requiring that relayers are spun up in increasing id order before all runners (handled by spawn.py). Thus, we realized we only needed to generate n sockets for relayer ←→ runner connections (n being the number of relayers). All runners would connect to the runner facing socket of each relayer; when those requests came in, the relayer could grab that specific connection socket and store it in a data structure, indexed by id, holding all runner facing connections. For intra-relayer communication, every relayer would create new sockets for higher id relayers to connect to, and connect to sockets previously made by lower id relayers.

Another challenge was that spawn.py would occasionally move too fast when creating subprocesses (runner and relayer instances), such that before connections were established for one process, it would try to connect with the next, resulting in errors. Our solution was to have the spawner wait to receive a connection heartbeat from a process (done when it is initialized by calling alert_spawn_process() in common) before it moves onto initializing the next process.

Finally, we struggled to determine intelligent strategies for the relayers advise runners and for runners to make their next moves. While not related to the distributed systems aspect, this was core to our game running effectively. We ultimately devised a solution where relayers would feed runner positions into a helper function iterating the L-infinity norm to try and find the nearest coordinate of value that hasn't already been checked. On the runner end, they employ a basic intelligent strategy of finding the move that makes the most progress towards the coordinate suggested by the relayer, unless it sees animals/bad terrain, in which case it sweeps for the next closest moves.
