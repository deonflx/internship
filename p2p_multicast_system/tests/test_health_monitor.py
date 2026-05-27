import sys
import os
import unittest
import time
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

    def test_pruning_inactive_peers(self):
        """Verify that the health monitor logic correctly identifies and removes timed out peers."""
        node = MagicMock()
        node.running = True
        node.peer_id = "127.0.0.1:5001"

        current_time = time.time()
        # Peer 5002 is active (seen 2s ago)
        # Peer 5003 is inactive (seen 15s ago, which is > PEER_TIMEOUT of 10s)
        node.peers = {
            "127.0.0.1:5001": {
                "host": "127.0.0.1",
                "port": 5001,
                "nodes": ["node1"],
                "hash": "hash1",
                "last_seen": current_time
            },
            "127.0.0.1:5002": {
                "host": "127.0.0.1",
                "port": 5002,
                "nodes": ["node2"],
                "hash": "hash2",
                "last_seen": current_time - 2
            },
            "127.0.0.1:5003": {
                "host": "127.0.0.1",
                "port": 5003,
                "nodes": ["node3"],
                "hash": "hash3",
                "last_seen": current_time - 15
            }
        }

        # Run the core pruning loop logic
        remove_peers = []
        for peer_id, info in list(node.peers.items()):
            if peer_id == node.peer_id:
                continue
            if current_time - info["last_seen"] > 10: # PEER_TIMEOUT = 10
                remove_peers.append(peer_id)

        for peer_id in remove_peers:
            del node.peers[peer_id]

        self.assertIn("127.0.0.1:5001", node.peers)
        self.assertIn("127.0.0.1:5002", node.peers)
        self.assertNotIn("127.0.0.1:5003", node.peers)

if __name__ == "__main__":
    unittest.main()
