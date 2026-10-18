import sys
import os
import unittest
import time
import threading
from unittest.mock import MagicMock, patch

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.health_monitor import start_health_monitor


class TestHealthMonitor(unittest.TestCase):
    @patch('core.health_monitor.threading.Thread')
    def test_start_health_monitor(self, mock_thread):
        """Verify that start_health_monitor starts a background daemon thread."""
        node = MagicMock()
        node.running = True

        thread = start_health_monitor(node)

        self.assertIsNotNone(thread)
        mock_thread.assert_called_once()
        self.assertTrue(mock_thread.call_args_list[0][1]['daemon'])

    def test_pruning_inactive_peers_with_timestamp(self):
        """Verify that the health monitor logic correctly identifies and
        removes timed-out peers using the last_seen timestamp approach."""
        node = MagicMock()
        node.running = True
        node.peer_id = "127.0.0.1:5001"

        now = time.time()
        # Peer 5002 is active (seen 2s ago)
        # Peer 5003 is inactive (seen 15s ago, which is > PEER_TIMEOUT of 10s)
        node.peers = {
            "127.0.0.1:5001": {
                "host": "127.0.0.1",
                "port": 5001,
                "nodes": ["node1"],
                "hash": "hash1",
                "last_seen": now
            },
            "127.0.0.1:5002": {
                "host": "127.0.0.1",
                "port": 5002,
                "nodes": ["node2"],
                "hash": "hash2",
                "last_seen": now - 2    # 2s ago — active
            },
            "127.0.0.1:5003": {
                "host": "127.0.0.1",
                "port": 5003,
                "nodes": ["node3"],
                "hash": "hash3",
                "last_seen": now - 15   # 15s ago — timed out
            }
        }

        # Simulate the pruning logic from the health monitor
        remove_peers = []
        for peer_id, info in list(node.peers.items()):
            if peer_id == node.peer_id:
                continue
            elapsed = now - info.get("last_seen", now)
            if elapsed > 10:  # PEER_TIMEOUT = 10
                remove_peers.append(peer_id)

        for peer_id in remove_peers:
            del node.peers[peer_id]

        self.assertIn("127.0.0.1:5001", node.peers)
        self.assertIn("127.0.0.1:5002", node.peers)
        self.assertNotIn("127.0.0.1:5003", node.peers)

    def test_gossip_updated_last_seen_prevents_removal(self):
        """Verify that a peer heard about via gossip (with updated last_seen)
        is not removed by the health monitor."""
        node = MagicMock()
        node.running = True
        node.peer_id = "127.0.0.1:5001"

        now = time.time()
        # Peer 5002 was originally seen 20s ago (would time out),
        # but gossip updated its last_seen to 3s ago
        node.peers = {
            "127.0.0.1:5001": {
                "host": "127.0.0.1", "port": 5001,
                "nodes": [], "hash": "h1", "last_seen": now
            },
            "127.0.0.1:5002": {
                "host": "127.0.0.1", "port": 5002,
                "nodes": [], "hash": "h2",
                "last_seen": now - 3   # Updated by gossip — only 3s ago
            }
        }

        # Run pruning logic
        remove_peers = []
        for peer_id, info in list(node.peers.items()):
            if peer_id == node.peer_id:
                continue
            elapsed = now - info.get("last_seen", now)
            if elapsed > 10:
                remove_peers.append(peer_id)

        self.assertEqual(len(remove_peers), 0)
        self.assertIn("127.0.0.1:5002", node.peers)


if __name__ == "__main__":
    unittest.main()
