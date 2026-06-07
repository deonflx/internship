import time
import threading
from utils.constants import PEER_TIMEOUT

def start_health_monitor(node) -> threading.Thread:
    """
    Starts a background thread that monitors peer activity.
    If a peer has not been seen (no DISCOVER message received) for more than
    PEER_TIMEOUT seconds, it is removed from the active peer list.
    """
    def monitor_loop():
        while node.running:
            remove_peers = []

            with node.lock:
                # Copy dictionary keys/items to avoid dict size mutation during iteration
                for peer_id, info in list(node.peers.items()):
                    if peer_id == node.peer_id:
                        continue

                    info["time"] += 2
                    if info["time"] > PEER_TIMEOUT:
                        remove_peers.append(peer_id)

                if remove_peers:
                    for peer_id in remove_peers:
                        del node.peers[peer_id]
                        print(f"\nRemoved inactive peer: {peer_id}")
                    node.save_config()

            time.sleep(2)

    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    return thread
