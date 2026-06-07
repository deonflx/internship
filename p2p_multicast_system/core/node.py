import socket
import threading
import time
from utils.constants import MULTICAST_GROUP, MULTICAST_PORT
from utils.hashing import generate_hash
from core.config_manager import ConfigManager
from core.discovery import start_discovery_sender, start_discovery_listener
from core.health_monitor import start_health_monitor

class P2PNode:
    """
    Orchestrator class for the Peer-to-Peer Multicast node.
    Manages socket initialization, command-line interface, configuration state,
    and runs discovery and health monitoring services.
    """
    def __init__(self):
        self.host = socket.gethostbyname(socket.gethostname())
        self.port = self.get_port()
        self.peer_id = f"{self.host}:{self.port}"

        self.config_manager = ConfigManager(self.port)
        self.registered_nodes = []
        self.peers = {}
        self.running = True
        self.lock = threading.Lock()
        self.time = 0

        self.load_config()

        # Create UDP Multicast socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind(("", MULTICAST_PORT))
        except Exception:
            self.sock.bind((MULTICAST_GROUP, MULTICAST_PORT))

        # Join the Multicast Group
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            mreq
        )

    def get_port(self) -> int:
        """Prompts the user for a valid TCP/UDP port number."""
        while True:
            try:
                port = int(input("Enter port: "))
                if 0 < port < 65535:
                    return port
                print("Invalid port")
            except Exception:
                print("Enter numeric value")

    def save_config(self):
        """Saves node's current status and peers to disk."""
        self.config_manager.save_config(
            self.peer_id,
            self.host,
            self.registered_nodes,
            self.peers
        )

    def load_config(self):
        """Loads node configuration from disk if available."""
        config = self.config_manager.load_config()
        if config:
            self.registered_nodes = config.get("registered_nodes", [])
            self.peers = config.get("peers", {})
            print(f"\nLoaded config from {self.config_manager.config_file}")
        else:
            self.save_config()

    def register_node(self):
        """Interactive helper to register a new user-defined node/channel."""
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
                    "hash": generate_hash(self.peer_id),
                    "time": self.time
                }
                self.save_config()
                print(f"\nRegistered node: {node_name}")
            else:
                print("Node already exists")

    def view_nodes(self):
        """Prints all registered nodes across all discovered peers."""
        with self.lock:
            print("\n========== ALL REGISTERED NODES ==========")
            for peer_id, info in self.peers.items():
                print(f"\nPeer : {peer_id}")
                for node in info["nodes"]:
                    print(f"  - {node}")
            print("\n==========================================")

    def view_peers(self):
        """Prints information about all currently active peers."""
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
        """Loop that runs in the main thread accepting user commands."""
        while self.running:
            try:
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
            except (KeyboardInterrupt, EOFError):
                self.running = False
                break

    def initialize_self_peer(self):
        """Ensures the node registers itself in its own peer map."""
        with self.lock:
            self.peers[self.peer_id] = {
                "host": self.host,
                "port": self.port,
                "nodes": self.registered_nodes,
                "hash": generate_hash(self.peer_id),
                "time": self.time
            }
            self.save_config()

    def start(self):
        """Starts all daemon service threads and enters command shell loop."""
        self.initialize_self_peer()
        print(f"\nPeer started on {self.peer_id}")

        start_discovery_listener(self)
        start_discovery_sender(self)
        start_health_monitor(self)

        self.command_loop()
