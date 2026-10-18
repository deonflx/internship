"""UDP Multicast Discovery module for discovering peers, announces, and welcome negotiations."""

import json
import threading
import time
from typing import Any, Dict
from p2p_network.constants import (
    ANNOUNCE_REPEATS,
    BUFFER_SIZE,
    GOSSIP_PORT,
    MULTICAST_GROUP,
    MULTICAST_PORT,
)
from p2p_network.utils import generate_hash


def send_announce(node: Any, repeats: int = ANNOUNCE_REPEATS, interval: float = 1.0):
    """
    Broadcasts a multicast ANNOUNCE message so existing peers discover this node.
    Sent multiple times over UDP for reliable delivery.
    """
    message = {
        "type": "ANNOUNCE",
        "peer_id": node.peer_id,
        "host": node.host,
        "port": node.port,
        "nodes": list(getattr(node, "registered_nodes", [])),
        "hash": generate_hash(node.peer_id),
    }
    payload = json.dumps(message).encode("utf-8")

    for _ in range(repeats):
        try:
            node.sock.sendto(payload, (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception:
            pass
        if interval > 0:
            time.sleep(interval)


def send_leave(node: Any):
    """
    Sends a multicast LEAVE message to cleanly notify peers of node shutdown.
    """
    message = {
        "type": "LEAVE",
        "peer_id": node.peer_id,
    }
    try:
        node.sock.sendto(
            json.dumps(message).encode("utf-8"),
            (MULTICAST_GROUP, MULTICAST_PORT),
        )
    except Exception:
        pass


def handle_announce(node: Any, message: Dict[str, Any]):
    """
    Handle incoming multicast ANNOUNCE message.
    Registers the peer and responds with a unicast WELCOME containing known peers.
    """
    peer_id = message["peer_id"]
    peer_manager = getattr(node, "peer_manager", None)
    if peer_manager is not None:
        peer_manager.add_or_update(
            peer_id=peer_id,
            host=message["host"],
            port=message["port"],
            nodes=message.get("nodes", []),
            hash_val=message.get("hash", ""),
            last_seen=time.time(),
        )
        if hasattr(node, "config_manager"):
            node.config_manager.mark_dirty()
        known_peers = peer_manager.get_gossip_dict()
    else:
        with getattr(node, "lock", threading.Lock()):
            node.peers[peer_id] = {
                "host": message["host"],
                "port": message["port"],
                "nodes": message.get("nodes", []),
                "hash": message.get("hash", ""),
                "last_seen": time.time(),
            }
            if hasattr(node, "config_manager"):
                node.config_manager.mark_dirty()
            known_peers = {
                pid: {
                    "host": info["host"],
                    "port": info["port"],
                    "nodes": info.get("nodes", []),
                    "hash": info.get("hash", ""),
                    "last_seen": info.get("last_seen", time.time()),
                }
                for pid, info in node.peers.items()
            }

    # Respond via unicast WELCOME to sender's gossip port
    welcome_msg = {
        "type": "WELCOME",
        "peer_id": node.peer_id,
        "known_peers": known_peers,
    }
    try:
        if hasattr(node, "gossip_sock"):
            node.gossip_sock.sendto(
                json.dumps(welcome_msg).encode("utf-8"),
                (message["host"], GOSSIP_PORT),
            )
    except Exception:
        pass

    print(f"\n  Discovered new peer: {peer_id}")


def handle_welcome(node: Any, message: Dict[str, Any]):
    """Handle incoming WELCOME reply and bootstrap peer list."""
    incoming_peers = message.get("known_peers", {})
    merge_peer_list(node, incoming_peers)


def handle_leave(node: Any, message: Dict[str, Any]):
    """Handle graceful departure notification from a peer."""
    peer_id = message["peer_id"]
    peer_manager = getattr(node, "peer_manager", None)
    if peer_manager is not None:
        if peer_manager.remove(peer_id):
            if hasattr(node, "config_manager"):
                node.config_manager.mark_dirty()
            print(f"\n  Peer left: {peer_id}")
    else:
        with getattr(node, "lock", threading.Lock()):
            if peer_id in getattr(node, "peers", {}):
                del node.peers[peer_id]
                if hasattr(node, "config_manager"):
                    node.config_manager.mark_dirty()
                print(f"\n  Peer left: {peer_id}")


def handle_gossip_message(node: Any, message: Dict[str, Any]):
    """Handle incoming periodic gossip packet."""
    sender_id = message.get("peer_id")
    peer_manager = getattr(node, "peer_manager", None)
    if peer_manager is not None:
        if sender_id:
            peer_manager.update_last_seen(sender_id)
    else:
        with getattr(node, "lock", threading.Lock()):
            if sender_id and sender_id in getattr(node, "peers", {}):
                node.peers[sender_id]["last_seen"] = time.time()

    incoming_peers = message.get("known_peers", {})
    merge_peer_list(node, incoming_peers)


def handle_data_message(node: Any, message: Dict[str, Any]):
    """Handle incoming unicast DATA message."""
    dest = message.get("dest_peer_id")
    if dest != node.peer_id:
        return

    data_entry = [message["data"], message["peer_id"], dest]
    with getattr(node, "lock", threading.Lock()):
        if not hasattr(node, "recieve"):
            node.recieve = []
        if data_entry not in node.recieve:
            node.recieve.append(data_entry)
            if hasattr(node, "config_manager"):
                node.config_manager.mark_dirty()
            print(f"\n  Received message from {message['peer_id']}: {message['data']}")


def merge_peer_list(node: Any, incoming_peers: Dict[str, Dict[str, Any]]):
    """Merges incoming peer dictionary into node's known peers."""
    peer_manager = getattr(node, "peer_manager", None)
    if peer_manager is not None:
        if peer_manager.merge_peers(incoming_peers):
            if hasattr(node, "config_manager"):
                node.config_manager.mark_dirty()
    else:
        updated = False
        with getattr(node, "lock", threading.Lock()):
            for pid, info in incoming_peers.items():
                if pid == node.peer_id:
                    continue
                if pid not in node.peers:
                    node.peers[pid] = {
                        "host": info["host"],
                        "port": info["port"],
                        "nodes": list(info.get("nodes", [])),
                        "hash": info.get("hash", ""),
                        "last_seen": info.get("last_seen", time.time()),
                    }
                    updated = True
                else:
                    existing = node.peers[pid]
                    incoming_seen = info.get("last_seen", 0)
                    if incoming_seen > existing.get("last_seen", 0):
                        existing["last_seen"] = incoming_seen
                        existing["nodes"] = list(info.get("nodes", existing.get("nodes", [])))
                        existing["hash"] = info.get("hash", existing.get("hash", ""))
                        updated = True

            if updated and hasattr(node, "config_manager"):
                node.config_manager.mark_dirty()


def start_discovery_listener(node: Any) -> threading.Thread:
    """
    Starts listening on multicast socket for ANNOUNCE, WELCOME, LEAVE, DISCOVER packets.
    """
    def listen_loop():
        while getattr(node, "running", True):
            try:
                data, addr = node.sock.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode("utf-8"))

                if message.get("peer_id") == node.peer_id:
                    continue

                msg_type = message.get("type", "")
                if msg_type in ("ANNOUNCE", "DISCOVER"):
                    handle_announce(node, message)
                elif msg_type == "WELCOME":
                    handle_welcome(node, message)
                elif msg_type == "LEAVE":
                    handle_leave(node, message)

            except Exception:
                pass

    thread = threading.Thread(target=listen_loop, daemon=True, name="DiscoveryListenerThread")
    thread.start()
    return thread


class MulticastDiscovery:
    """Encapsulates multicast discovery services for an active node."""

    def __init__(self, node: Any):
        self.node = node

    def announce(self, repeats: int = ANNOUNCE_REPEATS):
        """Broadcast announce packet."""
        send_announce(self.node, repeats=repeats)

    def leave(self):
        """Broadcast leave packet."""
        send_leave(self.node)

    def start_listener(self) -> threading.Thread:
        """Start discovery listener thread."""
        return start_discovery_listener(self.node)


# Aliases for backwards compatibility with existing core/discovery tests
_handle_announce = handle_announce
_handle_welcome = handle_welcome
_handle_leave = handle_leave
_handle_gossip = handle_gossip_message
_handle_data = handle_data_message
_merge_peer_list = merge_peer_list
