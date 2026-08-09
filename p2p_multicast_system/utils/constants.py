# Network constants for the P2P multicast system

MULTICAST_GROUP = "224.1.1.1"
MULTICAST_PORT = 5007
GOSSIP_PORT = 5008          # Dedicated unicast port for gossip + data messages

BUFFER_SIZE = 65535         # Increased from 4096 for gossip payloads with peer lists

DISCOVERY_INTERVAL = 5
PEER_TIMEOUT = 10

GOSSIP_FANOUT = 3           # Number of random peers to gossip with each round
ANNOUNCE_REPEATS = 3        # Send ANNOUNCE this many times on startup for reliability
