import socket
import threading
import time
from utils.constants import MULTICAST_GROUP, MULTICAST_PORT, GOSSIP_PORT
from utils.hashing import generate_hash
from core.config_manager import ConfigManager, start_config_saver
from core.discovery import (
    send_announce, start_gossip_sender,
    start_discovery_listener, start_gossip_listener,
    send_leave, send_data_to_peer
)
from core.health_monitor import start_health_monitor

def get_local_ip():
    """Auto-detect the local LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

lip = get_local_ip()

class P2PNode:
    """
    Orchestrator class for the Peer-to-Peer Multicast node.
    Manages socket initialization, command-line interface, configuration state,
    and runs discovery, gossip, and health monitoring services.

    Discovery Protocol (Hybrid Gossip + Multicast):
      1. JOIN:   Multicast ANNOUNCE on 224.1.1.1:5007 → peers reply with WELCOME
      2. STEADY: Unicast GOSSIP to K random peers every interval via port 5008
      3. DATA:   Unicast DATA directly to destination peer via port 5008
      4. LEAVE:  Multicast LEAVE on 224.1.1.1:5007 for graceful shutdown
    """
    def __init__(self):
        self.host = lip
        self.port = self.get_port()
        self.peer_id = f"{self.host}:{self.port}"

        self.config_manager = ConfigManager(self.port)
        self.registered_nodes = []
        self.peers = {}
        self.running = True
        self.lock = threading.Lock()
        self.sent = []
        self.recieve = []

        self.load_config()

        # --- Multicast socket (ANNOUNCE / LEAVE / WELCOME) ---
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.sock.bind(("", MULTICAST_PORT))
        except Exception:
            self.sock.bind((MULTICAST_GROUP, MULTICAST_PORT))

        # Join the Multicast Group on the WiFi interface
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton(lip)
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            mreq
        )
        # Send multicast packets out on the WiFi interface
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton(lip)
        )

        # --- Gossip / Data unicast socket ---
        self.gossip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.gossip_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.gossip_sock.bind(("", GOSSIP_PORT))

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
            self.peers,
            self.sent,
            self.recieve
        )

    def load_config(self):
        """Loads node configuration from disk if available."""
        config = self.config_manager.load_config()
        if config:
            self.registered_nodes = config.get("registered_nodes", [])
            self.peers = config.get("peers", {})
            self.sent = config.get("sent", [])
            self.recieve = config.get("recieve", [])
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
                    "last_seen": time.time()
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
                for node in info.get("nodes", []):
                    print(f"  - {node}")
            print("\n==========================================")

    def view_peers(self):
        """Prints information about all currently active peers."""
        with self.lock:
            print("\n=============== PEERS =================")
            for peer_id, info in self.peers.items():
                last_seen = info.get('last_seen', 0)
                age = time.time() - last_seen if last_seen else 0
                print(f"""
Peer ID   : {peer_id}
IP        : {info['host']}
Port      : {info['port']}
Hash      : {info.get('hash', 'N/A')[:20]}...
Last Seen : {age:.1f}s ago
""")
            print("=======================================")

    def send(self):
        """Prompts for a destination peer ID and a message, then sends it
        directly to the destination via unicast DATA message."""
        dest_peer_id = input("\nEnter destination peer ID (host:port): ").strip()
        if dest_peer_id == "":
            print("Invalid destination peer ID")
            return

        data = input("Enter message to send: ").strip()
        if data == "":
            print("Message cannot be empty")
            return

        # Record in sent history
        with self.lock:
            self.sent.append([data, self.peer_id, dest_peer_id])
            self.config_manager.mark_dirty()

        # Send directly via unicast
        success = send_data_to_peer(self, dest_peer_id, data)
        if success:
            print(f"\nSent message to {dest_peer_id}: {data}")
        else:
            print(f"\nMessage queued for {dest_peer_id} (will be delivered when peer is discovered)")

    def view_data(self):
        """Displays all received messages [data, source_peer_id, dest_peer_id] from self.recieve."""
        with self.lock:
            print("\n========== RECEIVED DATA ==========")
            if not self.recieve:
                print("  No data received yet.")
            else:
                for i, entry in enumerate(self.recieve, 1):
                    print(f"  [{i}] Data: {entry[0]}  |  From: {entry[1]}  |  To: {entry[2]}")
            print("====================================")

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
                elif command.lower() == "send":
                    self.send()
                elif command.lower() == "view data":
                    self.view_data()
                elif command.lower() == "exit":
                    self.shutdown()
                    break
            except (KeyboardInterrupt, EOFError):
                self.shutdown()
                break

    def initialize_self_peer(self):
        """Ensures the node registers itself in its own peer map."""
        with self.lock:
            self.peers[self.peer_id] = {
                "host": self.host,
                "port": self.port,
                "nodes": self.registered_nodes,
                "hash": generate_hash(self.peer_id),
                "last_seen": time.time()
            }
            self.save_config()

    def shutdown(self):
        """Graceful shutdown: send LEAVE, stop threads, close sockets."""
        print("\nShutting down...")
        send_leave(self)
        self.running = False

        # Final config flush
        with self.lock:
            self.save_config()

        try:
            self.sock.close()
        except Exception:
            pass
        try:
            self.gossip_sock.close()
        except Exception:
            pass

    def start(self):
        """
        Starts all daemon service threads and enters command shell loop.

        Startup sequence:
          1. Register self in peer map
          2. Start multicast listener (ANNOUNCE/WELCOME/LEAVE)
          3. Start gossip listener (GOSSIP/DATA on unicast port)
          4. Send multicast ANNOUNCE (so existing peers discover us)
          5. Start gossip sender (periodic unicast to K random peers)
          6. Start health monitor (prune timed-out peers)
          7. Start config saver (batched disk writes)
          8. Enter command loop
        """
        self.initialize_self_peer()
        print(f"\nPeer started on {self.peer_id}")
        print(f"  Multicast: {MULTICAST_GROUP}:{MULTICAST_PORT}")
        print(f"  Gossip:    {self.host}:{GOSSIP_PORT}")

        # 1. Start listeners BEFORE announcing (so we catch WELCOME replies)
        start_discovery_listener(self)
        start_gossip_listener(self)

        # 2. Announce ourselves via multicast (blocking, takes ~3s)
        print("  Sending ANNOUNCE to network...")
        send_announce(self)
        print("  ANNOUNCE complete.")

        # 3. Start background services
        start_gossip_sender(self)
        start_health_monitor(self)
        start_config_saver(self)

        # 4. Enter interactive command shell
        self.command_loop()
