import time
import threading
from utils.constants import PEER_TIMEOUT

def start_health_monitor(node) -> threading.Thread:
    """
    Starts a background thread that monitors peer activity.
    Uses timestamp-based timeout: if a peer's `last_seen` is older than
    PEER_TIMEOUT seconds, it is removed from the active peer list.

    This works correctly with gossip since `last_seen` is updated whenever
    we hear about a peer from any gossip source (not just from the peer directly).
    """
    def monitor_loop():
        while node.running:
            remove_peers = []
            now = time.time()

            with node.lock:
                for peer_id, info in list(node.peers.items()):
                    if peer_id == node.peer_id:
                        continue

                    elapsed = now - info.get("last_seen", now)
                    if elapsed > PEER_TIMEOUT:
                        remove_peers.append(peer_id)

                if remove_peers:
                    for peer_id in remove_peers:
                        del node.peers[peer_id]
                        print(f"\nRemoved inactive peer: {peer_id}")
                    node.config_manager.mark_dirty()

            time.sleep(2)

    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    return thread
