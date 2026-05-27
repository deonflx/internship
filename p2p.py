import socket
import threading
import time
import json
import os
import hashlib

MULTICAST_GROUP = "224.1.1.1"
MULTICAST_PORT = 5007

BUFFER_SIZE = 4096

DISCOVERY_INTERVAL = 5
PEER_TIMEOUT = 10


class P2PNode:

    def __init__(self):

        self.host = socket.gethostbyname(socket.gethostname())

        self.port = self.get_port()

        self.peer_id = f"{self.host}:{self.port}"

        self.config_file = f"{self.port}.json"

        self.registered_nodes = []

        self.peers = {}

        self.running = True

        self.lock = threading.Lock()

        self.load_config()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind(("", MULTICAST_PORT))
        except:
            self.sock.bind((MULTICAST_GROUP, MULTICAST_PORT))

        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")

        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            mreq
        )

    def get_port(self):

        while True:

            try:

                port = int(input("Enter port: "))

                if 0 < port < 65535:
                    return port

                print("Invalid port")

            except:
                print("Enter numeric value")

    def generate_hash(self, value):

        return hashlib.sha256(value.encode()).hexdigest()

    def save_config(self):

        data = {
            "peer_id": self.peer_id,
            "host": self.host,
            "port": self.port,
            "registered_nodes": self.registered_nodes,
            "peers": self.peers
        }

        with open(self.config_file, "w") as f:

            json.dump(data, f, indent=4)

    def load_config(self):

        if os.path.exists(self.config_file):

            with open(self.config_file, "r") as f:

                data = json.load(f)

                self.registered_nodes = data.get("registered_nodes", [])

                self.peers = data.get("peers", {})

                print(f"\nLoaded config from {self.config_file}")

        else:

            self.save_config()

    def register_node(self):

        node_name = input("\nEnter node string: ").strip()

        if node_name == "":
            print("Invalid node")
            return

        with self.lock:

            if node_name not in self.registered_nodes:

                self.registered_nodes.append(node_name)

                self.peers[self.peer_id] = {
                    "host": self.host,
                    "port": self.port,
                    "nodes": self.registered_nodes,
                    "hash": self.generate_hash(self.peer_id),
                    "last_seen": time.time()
                }

                self.save_config()

                print(f"\nRegistered node: {node_name}")

            else:
                print("Node already exists")

    def send_discovery(self):

        while self.running:

            message = {
                "type": "DISCOVER",
                "peer_id": self.peer_id,
                "host": self.host,
                "port": self.port,
                "nodes": self.registered_nodes,
                "hash": self.generate_hash(self.peer_id)
            }

            self.sock.sendto(
                json.dumps(message).encode(),
                (MULTICAST_GROUP, MULTICAST_PORT)
            )

            time.sleep(DISCOVERY_INTERVAL)

    def listen(self):

        while self.running:

            try:

                data, addr = self.sock.recvfrom(BUFFER_SIZE)

                message = json.loads(data.decode())

                if message["peer_id"] == self.peer_id:
                    continue

                if message["type"] == "DISCOVER":

                    with self.lock:

                        self.peers[message["peer_id"]] = {
                            "host": message["host"],
                            "port": message["port"],
                            "nodes": message["nodes"],
                            "hash": message["hash"],
                            "last_seen": time.time()
                        }

                        self.save_config()

            except:
                pass

    def health_monitor(self):

        while self.running:

            current_time = time.time()

            remove_peers = []

            with self.lock:

                for peer_id, info in self.peers.items():

                    if peer_id == self.peer_id:
                        continue

                    if current_time - info["last_seen"] > PEER_TIMEOUT:

                        remove_peers.append(peer_id)

                for peer_id in remove_peers:

                    del self.peers[peer_id]

                    print(f"\nRemoved inactive peer: {peer_id}")

                self.save_config()

            time.sleep(2)

    def view_nodes(self):

        with self.lock:

            print("\n========== ALL REGISTERED NODES ==========")

            for peer_id, info in self.peers.items():

                print(f"\nPeer : {peer_id}")

                for node in info["nodes"]:

                    print(f"  - {node}")

            print("\n==========================================")

    def view_peers(self):

        with self.lock:

            print("\n=============== PEERS =================")

            for peer_id, info in self.peers.items():

                print(f"""
Peer ID : {peer_id}
IP      : {info['host']}
Port    : {info['port']}
Hash    : {info['hash'][:20]}...
""")

            print("=======================================")

    def command_loop(self):

        while self.running:

            command = input(f"\n[{self.port}] Enter command: ")

            if command.lower() == "register":

                self.register_node()

            elif command.lower() == "view nodes":

                self.view_nodes()

            elif command.lower() == "view peers":

                self.view_peers()

            elif command.lower() == "exit":

                self.running = False

                break

    def initialize_self_peer(self):

        with self.lock:

            self.peers[self.peer_id] = {
                "host": self.host,
                "port": self.port,
                "nodes": self.registered_nodes,
                "hash": self.generate_hash(self.peer_id),
                "last_seen": time.time()
            }

            self.save_config()

    def start(self):

        self.initialize_self_peer()

        print(f"\nPeer started on {self.peer_id}")

        threading.Thread(target=self.listen, daemon=True).start()

        threading.Thread(target=self.send_discovery, daemon=True).start()

        threading.Thread(target=self.health_monitor, daemon=True).start()

        self.command_loop()


node = P2PNode()

node.start()