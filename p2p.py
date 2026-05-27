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
NODE_TIMEOUT = 10


class P2PNode:

    def __init__(self):

        self.host = socket.gethostbyname(socket.gethostname())

        self.port = self.get_free_port()

        self.config_file = f"{self.port}.json"

        self.peers = {}

        self.running = True

        self.lock = threading.Lock()

        self.node_name = None

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

    def get_free_port(self):

        temp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        temp.bind(("", 0))

        port = temp.getsockname()[1]

        temp.close()

        return port

    def generate_hash(self, value):

        return hashlib.sha256(value.encode()).hexdigest()

    def save_config(self):

        data = {
            "node_name": self.node_name,
            "host": self.host,
            "port": self.port,
            "peers": self.peers
        }

        with open(self.config_file, "w") as f:

            json.dump(data, f, indent=4)

    def load_config(self):

        if os.path.exists(self.config_file):

            with open(self.config_file, "r") as f:

                data = json.load(f)

                self.node_name = data.get("node_name")

                self.peers = data.get("peers", {})

                print(f"\nLoaded config from {self.config_file}")

        else:

            self.save_config()

    def register_node(self):

        while True:

            name = input("\nEnter node name: ").strip()

            if name == "":
                print("Invalid node name")
            else:
                break

        self.node_name = name

        node_hash = self.generate_hash(
            f"{self.node_name}{self.host}{self.port}"
        )

        with self.lock:

            self.peers[self.node_name] = {
                "host": self.host,
                "port": self.port,
                "hash": node_hash,
                "last_seen": time.time()
            }

            self.save_config()

        print(f"\nRegistered node: {self.node_name}")

    def send_discovery(self):

        while self.running:

            if self.node_name:

                message = {
                    "type": "DISCOVER",
                    "node_name": self.node_name,
                    "host": self.host,
                    "port": self.port,
                    "hash": self.generate_hash(
                        f"{self.node_name}{self.host}{self.port}"
                    )
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

                if message["node_name"] == self.node_name:
                    continue

                if message["type"] == "DISCOVER":

                    with self.lock:

                        self.peers[message["node_name"]] = {
                            "host": message["host"],
                            "port": message["port"],
                            "hash": message["hash"],
                            "last_seen": time.time()
                        }

                        self.save_config()

            except:
                pass

    def health_monitor(self):

        while self.running:

            current_time = time.time()

            remove_nodes = []

            with self.lock:

                for peer, info in self.peers.items():

                    if peer == self.node_name:
                        continue

                    if current_time - info["last_seen"] > NODE_TIMEOUT:

                        remove_nodes.append(peer)

                for peer in remove_nodes:

                    del self.peers[peer]

                    print(f"\nRemoved inactive node: {peer}")

                self.save_config()

            time.sleep(2)

    def view_nodes(self):

        with self.lock:

            print("\n========== REGISTERED NODES ==========")

            if not self.peers:
                print("No nodes available")

            for peer, info in self.peers.items():

                print(f"""
Name : {peer}
IP   : {info['host']}
Port : {info['port']}
Hash : {info['hash'][:20]}...
""")

            print("======================================")

    def command_loop(self):

        while self.running:

            command = input(f"\n[{self.port}] Enter command: ")

            if command.lower() == "register":

                self.register_node()

            elif command.lower() == "view":

                self.view_nodes()

            elif command.lower() == "exit":

                self.running = False

                print("\nNode stopped")

                break

    def start(self):

        print(f"\nTerminal started on port {self.port}")

        threading.Thread(target=self.listen, daemon=True).start()

        threading.Thread(target=self.send_discovery, daemon=True).start()

        threading.Thread(target=self.health_monitor, daemon=True).start()

        self.command_loop()


node = P2PNode()

node.start()