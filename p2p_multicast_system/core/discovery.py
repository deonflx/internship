import socket
import json
import time
import random
import threading
from utils.constants import (
    MULTICAST_GROUP, MULTICAST_PORT, GOSSIP_PORT,
    DISCOVERY_INTERVAL, BUFFER_SIZE,
    GOSSIP_FANOUT, ANNOUNCE_REPEATS
)
from utils.hashing import generate_hash


# ---------------------------------------------------------------------------
# Phase 1 — JOIN: Multicast ANNOUNCE (sent once on startup)
# ---------------------------------------------------------------------------

def send_announce(node):
    """
    Sends a multicast ANNOUNCE message so existing peers discover this node.
    Sent ANNOUNCE_REPEATS times at 1-second intervals for reliability
    (multicast is unreliable — packets can be dropped).
    """
    message = {
        "type": "ANNOUNCE",
        "peer_id": node.peer_id,
        "host": node.host,
        "port": node.port,
        "nodes": node.registered_nodes,
        "hash": generate_hash(node.peer_id)
    }
    payload = json.dumps(message).encode()

    for _ in range(ANNOUNCE_REPEATS):
        try:
            node.sock.sendto(payload, (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception:
            pass
        time.sleep(1)


# ---------------------------------------------------------------------------
# Phase 2 — STEADY STATE: Unicast GOSSIP (periodic, to K random peers)
# ---------------------------------------------------------------------------

def start_gossip_sender(node) -> threading.Thread:
    """
    Replaces the old start_discovery_sender. Instead of multicasting to ALL
    peers every interval, picks GOSSIP_FANOUT random peers and sends them
    the current known-peers list via unicast.

    Scaling: O(K) messages per interval instead of O(N).
    Convergence: O(log N) rounds for the full network to learn about all peers.
    """
    def gossip_loop():
        while node.running:
            time.sleep(DISCOVERY_INTERVAL)

            with node.lock:
                # Only gossip with peers other than ourselves
                peer_ids = [pid for pid in node.peers if pid != node.peer_id]

            if not peer_ids:
                continue

            # Pick K random peers to gossip with
            targets = random.sample(peer_ids, min(GOSSIP_FANOUT, len(peer_ids)))

            # Build compact peer list for gossip (exclude large fields)
            with node.lock:
                known_peers = {}
                for pid, info in node.peers.items():
                    known_peers[pid] = {
                        "host": info["host"],
                        "port": info["port"],
                        "nodes": info.get("nodes", []),
                        "hash": info.get("hash", ""),
                        "last_seen": info.get("last_seen", time.time())
                    }

            gossip_msg = {
                "type": "GOSSIP",
                "peer_id": node.peer_id,
                "known_peers": known_peers
            }
            payload = json.dumps(gossip_msg).encode()

            for target_id in targets:
                with node.lock:
                    target_info = node.peers.get(target_id)
                if target_info:
                    try:
                        # UNICAST to the target's gossip port — NOT multicast
                        node.gossip_sock.sendto(
                            payload,
                            (target_info["host"], GOSSIP_PORT)
                        )
                    except Exception:
                        pass

    thread = threading.Thread(target=gossip_loop, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Phase 4 — LEAVE: Multicast LEAVE (graceful shutdown)
# ---------------------------------------------------------------------------

def send_leave(node):
    """
    Sends a multicast LEAVE message so peers can immediately remove this node
    from their peer list (graceful shutdown). If the node crashes without
    sending LEAVE, the health monitor's timeout will clean it up.
    """
    message = {
        "type": "LEAVE",
        "peer_id": node.peer_id
    }
    try:
        node.sock.sendto(
            json.dumps(message).encode(),
            (MULTICAST_GROUP, MULTICAST_PORT)
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 3 — DATA: Direct unicast message delivery
# ---------------------------------------------------------------------------

def send_data_to_peer(node, dest_peer_id: str, data: str):
    """
    Sends a DATA message directly to the destination peer via unicast.
    This replaces the old mechanism of piggybacking messages on DISCOVER packets.
    """
    with node.lock:
        target_info = node.peers.get(dest_peer_id)

    if not target_info:
        print(f"  Peer {dest_peer_id} not found in peer list. Message queued for later.")
        return False

    message = {
        "type": "DATA",
        "peer_id": node.peer_id,
        "dest_peer_id": dest_peer_id,
        "data": data
    }
    try:
        node.gossip_sock.sendto(
            json.dumps(message).encode(),
            (target_info["host"], GOSSIP_PORT)
        )
        return True
    except Exception as e:
        print(f"  Failed to send to {dest_peer_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Listeners
# ---------------------------------------------------------------------------

def start_discovery_listener(node) -> threading.Thread:
    """
    Listens on the multicast socket for:
      - ANNOUNCE: A new peer is joining → add it and reply with WELCOME
      - WELCOME: Response to our ANNOUNCE → merge the sender's peer list
      - LEAVE:   A peer is departing → remove it immediately
      - DISCOVER: (backward compat) Old-style message → treat as ANNOUNCE
    """
    def listen_loop():
        while node.running:
            try:
                data, addr = node.sock.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())

                # Ignore messages from self
                if message.get("peer_id") == node.peer_id:
                    continue

                msg_type = message.get("type", "")

                if msg_type == "ANNOUNCE" or msg_type == "DISCOVER":
                    _handle_announce(node, message)

                elif msg_type == "WELCOME":
                    _handle_welcome(node, message)

                elif msg_type == "LEAVE":
                    _handle_leave(node, message)

            except Exception:
                pass

    thread = threading.Thread(target=listen_loop, daemon=True)
    thread.start()
    return thread


def start_gossip_listener(node) -> threading.Thread:
    """
    Listens on the dedicated gossip unicast socket for:
      - GOSSIP: Peer list exchange → merge with our known peers
      - DATA:   Direct message delivery → add to node.recieve
    """
    def listen_loop():
        while node.running:
            try:
                data, addr = node.gossip_sock.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())

                # Ignore messages from self
                if message.get("peer_id") == node.peer_id:
                    continue

                msg_type = message.get("type", "")

                if msg_type == "GOSSIP":
                    _handle_gossip(node, message)

                elif msg_type == "DATA":
                    _handle_data(node, message)

            except Exception:
                pass

    thread = threading.Thread(target=listen_loop, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

def _handle_announce(node, message):
    """
    A new peer announced itself via multicast.
    Add/update it in our peer list and reply with a unicast WELCOME
    containing our full peer list so it can bootstrap quickly.
    """
    peer_id = message["peer_id"]
    with node.lock:
        node.peers[peer_id] = {
            "host": message["host"],
            "port": message["port"],
            "nodes": message.get("nodes", []),
            "hash": message.get("hash", ""),
            "last_seen": time.time()
        }
        node.config_manager.mark_dirty()

    # Reply with WELCOME containing our peer list
    with node.lock:
        known_peers = {}
        for pid, info in node.peers.items():
            known_peers[pid] = {
                "host": info["host"],
                "port": info["port"],
                "nodes": info.get("nodes", []),
                "hash": info.get("hash", ""),
                "last_seen": info.get("last_seen", time.time())
            }

    welcome_msg = {
        "type": "WELCOME",
        "peer_id": node.peer_id,
        "known_peers": known_peers
    }
    try:
        node.gossip_sock.sendto(
            json.dumps(welcome_msg).encode(),
            (message["host"], GOSSIP_PORT)
        )
    except Exception:
        pass

    print(f"\n  Discovered new peer: {peer_id}")


def _handle_welcome(node, message):
    """
    A peer responded to our ANNOUNCE with its full peer list.
    Merge their peer list into ours to bootstrap discovery.
    """
    incoming_peers = message.get("known_peers", {})
    _merge_peer_list(node, incoming_peers)


def _handle_leave(node, message):
    """
    A peer is gracefully leaving the network.
    Remove it from our peer list immediately.
    """
    peer_id = message["peer_id"]
    with node.lock:
        if peer_id in node.peers:
            del node.peers[peer_id]
            node.config_manager.mark_dirty()
            print(f"\n  Peer left: {peer_id}")


def _handle_gossip(node, message):
    """
    Received a peer-list gossip from another node.
    Merge their known peers into ours and update the sender's last_seen.
    """
    sender_id = message["peer_id"]

    # Update sender's last_seen time
    with node.lock:
        if sender_id in node.peers:
            node.peers[sender_id]["last_seen"] = time.time()

    incoming_peers = message.get("known_peers", {})
    _merge_peer_list(node, incoming_peers)


def _handle_data(node, message):
    """
    Received a direct DATA message from another peer.
    Add it to our receive list.
    """
    dest = message.get("dest_peer_id")
    if dest != node.peer_id:
        return  # Not for us (shouldn't happen with unicast, but safety check)

    data_entry = [message["data"], message["peer_id"], dest]

    with node.lock:
        if data_entry not in node.recieve:
            node.recieve.append(data_entry)
            node.config_manager.mark_dirty()
            print(f"\n  Received message from {message['peer_id']}: {message['data']}")


# ---------------------------------------------------------------------------
# Utility: Peer list merge
# ---------------------------------------------------------------------------

def _merge_peer_list(node, incoming_peers: dict):
    """
    Merges an incoming peer list into the node's known peers.
    For each peer in the incoming list:
      - If unknown → add it (new discovery via gossip)
      - If known → update if incoming last_seen is more recent
    """
    updated = False
    with node.lock:
        for pid, info in incoming_peers.items():
            if pid == node.peer_id:
                continue  # Don't overwrite our own entry

            if pid not in node.peers:
                # New peer discovered via gossip
                node.peers[pid] = {
                    "host": info["host"],
                    "port": info["port"],
                    "nodes": info.get("nodes", []),
                    "hash": info.get("hash", ""),
                    "last_seen": info.get("last_seen", time.time())
                }
                updated = True
            else:
                # Existing peer — update if incoming info is fresher
                existing = node.peers[pid]
                incoming_seen = info.get("last_seen", 0)
                if incoming_seen > existing.get("last_seen", 0):
                    existing["last_seen"] = incoming_seen
                    existing["nodes"] = info.get("nodes", existing["nodes"])
                    existing["hash"] = info.get("hash", existing["hash"])
                    updated = True

        if updated:
            node.config_manager.mark_dirty()
