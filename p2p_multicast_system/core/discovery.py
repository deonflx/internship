import socket
import json
import time
import threading
from utils.constants import MULTICAST_GROUP, MULTICAST_PORT, DISCOVERY_INTERVAL, BUFFER_SIZE
from utils.hashing import generate_hash

def start_discovery_sender(node) -> threading.Thread:
    """
    Starts a background daemon thread that broadcasts the node's info
    periodically via UDP multicast.
    """
    def send_loop():
        while node.running:
            message = {
                "type": "DISCOVER",
                "peer_id": node.peer_id,
                "host": node.host,
                "port": node.port,
                "nodes": node.registered_nodes,
                "hash": generate_hash(node.peer_id)
            }
            try:
                node.sock.sendto(
                    json.dumps(message).encode(),
                    (MULTICAST_GROUP, MULTICAST_PORT)
                )
            except Exception:
                pass
            time.sleep(DISCOVERY_INTERVAL)

    thread = threading.Thread(target=send_loop, daemon=True)
    thread.start()
    return thread

def start_discovery_listener(node) -> threading.Thread:
    """
    Starts a background daemon thread that listens for discovery messages
    from other peers and registers them.
    """
    def listen_loop():
        while node.running:
            try:
                data, addr = node.sock.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())

                # Ignore discovery messages from self
                if message["peer_id"] == node.peer_id:
                    continue

                if message["type"] == "DISCOVER":
                    with node.lock:
                        node.peers[message["peer_id"]] = {
                            "host": message["host"],
                            "port": message["port"],
                            "nodes": message["nodes"],
                            "hash": message["hash"],
                            "last_seen": time.time()
                        }
                        node.save_config()
            except Exception:
                pass

    thread = threading.Thread(target=listen_loop, daemon=True)
    thread.start()
    return thread
