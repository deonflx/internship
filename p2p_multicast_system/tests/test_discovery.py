import sys
import os
import json
import time
import unittest
from unittest.mock import MagicMock, patch, call

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.discovery import (
    send_announce, start_gossip_sender, start_gossip_listener,
    start_discovery_listener, send_leave, send_data_to_peer,
    _handle_announce, _handle_welcome, _handle_leave,
    _handle_gossip, _handle_data, _merge_peer_list
)


class TestSendAnnounce(unittest.TestCase):
    """Tests for the multicast ANNOUNCE sent on startup."""

    @patch('core.discovery.time.sleep')
    def test_send_announce_sends_multicast(self, mock_sleep):
        """Verify ANNOUNCE is sent via multicast to the correct group."""
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.host = "192.168.1.10"
        node.port = 5001
        node.registered_nodes = ["sensor1"]

        send_announce(node)

        # Should be called ANNOUNCE_REPEATS times (3)
        self.assertEqual(node.sock.sendto.call_count, 3)

        # Verify the payload is a valid ANNOUNCE message
        first_call = node.sock.sendto.call_args_list[0]
        payload = json.loads(first_call[0][0].decode())
        self.assertEqual(payload["type"], "ANNOUNCE")
        self.assertEqual(payload["peer_id"], "192.168.1.10:5001")
        self.assertNotIn("sent", payload)  # No sent list in ANNOUNCE


class TestSendLeave(unittest.TestCase):
    """Tests for the multicast LEAVE sent on graceful shutdown."""

    def test_send_leave_sends_multicast(self):
        """Verify LEAVE is sent via multicast."""
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"

        send_leave(node)

        node.sock.sendto.assert_called_once()
        payload = json.loads(node.sock.sendto.call_args[0][0].decode())
        self.assertEqual(payload["type"], "LEAVE")
        self.assertEqual(payload["peer_id"], "192.168.1.10:5001")


class TestSendDataToPeer(unittest.TestCase):
    """Tests for direct unicast DATA message delivery."""

    def test_send_data_to_known_peer(self):
        """Verify DATA message is sent via unicast to the destination peer."""
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = MagicMock()
        node.peers = {
            "192.168.1.20:5002": {"host": "192.168.1.20", "port": 5002}
        }
        # Make the lock context manager work properly
        node.lock.__enter__ = MagicMock(return_value=None)
        node.lock.__exit__ = MagicMock(return_value=False)

        result = send_data_to_peer(node, "192.168.1.20:5002", "hello")

        self.assertTrue(result)
        node.gossip_sock.sendto.assert_called_once()
        payload = json.loads(node.gossip_sock.sendto.call_args[0][0].decode())
        self.assertEqual(payload["type"], "DATA")
        self.assertEqual(payload["data"], "hello")

    def test_send_data_to_unknown_peer_returns_false(self):
        """Verify sending to unknown peer returns False."""
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = MagicMock()
        node.peers = {}
        node.lock.__enter__ = MagicMock(return_value=None)
        node.lock.__exit__ = MagicMock(return_value=False)

        result = send_data_to_peer(node, "192.168.1.99:9999", "hello")

        self.assertFalse(result)
        node.gossip_sock.sendto.assert_not_called()


class TestThreadStarters(unittest.TestCase):
    """Tests that background threads are started as daemon threads."""

    @patch('core.discovery.threading.Thread')
    def test_start_gossip_sender(self, mock_thread):
        """Verify gossip sender starts a daemon thread."""
        node = MagicMock()
        node.running = True

        thread = start_gossip_sender(node)

        self.assertIsNotNone(thread)
        mock_thread.assert_called_once()
        self.assertTrue(mock_thread.call_args_list[0][1]['daemon'])

    @patch('core.discovery.threading.Thread')
    def test_start_discovery_listener(self, mock_thread):
        """Verify discovery listener starts a daemon thread."""
        node = MagicMock()
        node.running = True

        thread = start_discovery_listener(node)

        self.assertIsNotNone(thread)
        mock_thread.assert_called_once()
        self.assertTrue(mock_thread.call_args_list[0][1]['daemon'])

    @patch('core.discovery.threading.Thread')
    def test_start_gossip_listener(self, mock_thread):
        """Verify gossip listener starts a daemon thread."""
        node = MagicMock()
        node.running = True

        thread = start_gossip_listener(node)

        self.assertIsNotNone(thread)
        mock_thread.assert_called_once()
        self.assertTrue(mock_thread.call_args_list[0][1]['daemon'])


class TestHandleAnnounce(unittest.TestCase):
    """Tests for ANNOUNCE message handling."""

    def _make_node(self):
        import threading
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.peers = {
            "192.168.1.10:5001": {
                "host": "192.168.1.10", "port": 5001,
                "nodes": [], "hash": "abc", "last_seen": time.time()
            }
        }
        node.lock = threading.Lock()
        return node

    def test_adds_new_peer(self):
        """Verify ANNOUNCE from new peer adds it to peer list."""
        node = self._make_node()

        msg = {
            "type": "ANNOUNCE",
            "peer_id": "192.168.1.20:5002",
            "host": "192.168.1.20",
            "port": 5002,
            "nodes": ["sensor2"],
            "hash": "def"
        }
        _handle_announce(node, msg)

        self.assertIn("192.168.1.20:5002", node.peers)
        self.assertEqual(node.peers["192.168.1.20:5002"]["host"], "192.168.1.20")
        node.config_manager.mark_dirty.assert_called()

    def test_sends_welcome_reply(self):
        """Verify ANNOUNCE triggers a WELCOME reply via unicast."""
        node = self._make_node()

        msg = {
            "type": "ANNOUNCE",
            "peer_id": "192.168.1.20:5002",
            "host": "192.168.1.20",
            "port": 5002,
            "nodes": [],
            "hash": "def"
        }
        _handle_announce(node, msg)

        node.gossip_sock.sendto.assert_called_once()
        payload = json.loads(node.gossip_sock.sendto.call_args[0][0].decode())
        self.assertEqual(payload["type"], "WELCOME")


class TestHandleLeave(unittest.TestCase):
    """Tests for LEAVE message handling."""

    def test_removes_peer(self):
        """Verify LEAVE removes the peer from the list."""
        import threading
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = threading.Lock()
        node.peers = {
            "192.168.1.10:5001": {"host": "192.168.1.10", "port": 5001,
                                   "nodes": [], "hash": "a", "last_seen": time.time()},
            "192.168.1.20:5002": {"host": "192.168.1.20", "port": 5002,
                                   "nodes": [], "hash": "b", "last_seen": time.time()}
        }

        _handle_leave(node, {"type": "LEAVE", "peer_id": "192.168.1.20:5002"})

        self.assertNotIn("192.168.1.20:5002", node.peers)
        self.assertIn("192.168.1.10:5001", node.peers)


class TestMergePeerList(unittest.TestCase):
    """Tests for the gossip peer-list merge logic."""

    def _make_node(self):
        import threading
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = threading.Lock()
        node.peers = {
            "192.168.1.10:5001": {
                "host": "192.168.1.10", "port": 5001,
                "nodes": ["s1"], "hash": "a", "last_seen": time.time()
            },
            "192.168.1.20:5002": {
                "host": "192.168.1.20", "port": 5002,
                "nodes": ["s2"], "hash": "b", "last_seen": 100.0
            }
        }
        return node

    def test_adds_unknown_peers(self):
        """Verify merging a peer list adds previously unknown peers."""
        node = self._make_node()

        incoming = {
            "192.168.1.30:5003": {
                "host": "192.168.1.30", "port": 5003,
                "nodes": ["s3"], "hash": "c", "last_seen": time.time()
            }
        }

        _merge_peer_list(node, incoming)

        self.assertIn("192.168.1.30:5003", node.peers)
        self.assertEqual(node.peers["192.168.1.30:5003"]["host"], "192.168.1.30")

    def test_updates_existing_peer_with_fresher_info(self):
        """Verify merge updates last_seen for existing peers when incoming is newer."""
        node = self._make_node()

        incoming = {
            "192.168.1.20:5002": {
                "host": "192.168.1.20", "port": 5002,
                "nodes": ["s2", "s2b"], "hash": "b2", "last_seen": 200.0
            }
        }

        _merge_peer_list(node, incoming)

        self.assertEqual(node.peers["192.168.1.20:5002"]["last_seen"], 200.0)
        self.assertEqual(node.peers["192.168.1.20:5002"]["nodes"], ["s2", "s2b"])

    def test_does_not_overwrite_self(self):
        """Verify merge never overwrites our own peer entry."""
        node = self._make_node()
        original_hash = node.peers["192.168.1.10:5001"]["hash"]

        incoming = {
            "192.168.1.10:5001": {
                "host": "192.168.1.10", "port": 5001,
                "nodes": ["EVIL"], "hash": "EVIL", "last_seen": time.time() + 999
            }
        }

        _merge_peer_list(node, incoming)

        # Our own entry should be unchanged
        self.assertEqual(node.peers["192.168.1.10:5001"]["hash"], original_hash)

    def test_does_not_downgrade_last_seen(self):
        """Verify merge does not downgrade last_seen to an older value."""
        node = self._make_node()
        node.peers["192.168.1.20:5002"]["last_seen"] = 300.0

        incoming = {
            "192.168.1.20:5002": {
                "host": "192.168.1.20", "port": 5002,
                "nodes": ["s2"], "hash": "b", "last_seen": 100.0
            }
        }

        _merge_peer_list(node, incoming)

        # Should remain at 300, not be downgraded to 100
        self.assertEqual(node.peers["192.168.1.20:5002"]["last_seen"], 300.0)


class TestHandleData(unittest.TestCase):
    """Tests for DATA message handling."""

    def test_adds_message_to_receive_list(self):
        """Verify DATA message is added to node.recieve."""
        import threading
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = threading.Lock()
        node.recieve = []

        msg = {
            "type": "DATA",
            "peer_id": "192.168.1.20:5002",
            "dest_peer_id": "192.168.1.10:5001",
            "data": "hello world"
        }

        _handle_data(node, msg)

        self.assertEqual(len(node.recieve), 1)
        self.assertEqual(node.recieve[0], ["hello world", "192.168.1.20:5002", "192.168.1.10:5001"])

    def test_ignores_messages_not_for_us(self):
        """Verify DATA messages addressed to other peers are ignored."""
        import threading
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = threading.Lock()
        node.recieve = []

        msg = {
            "type": "DATA",
            "peer_id": "192.168.1.20:5002",
            "dest_peer_id": "192.168.1.30:5003",  # NOT us
            "data": "not for us"
        }

        _handle_data(node, msg)

        self.assertEqual(len(node.recieve), 0)

    def test_deduplicates_messages(self):
        """Verify duplicate DATA messages are not added twice."""
        import threading
        node = MagicMock()
        node.peer_id = "192.168.1.10:5001"
        node.lock = threading.Lock()
        node.recieve = [["hello", "192.168.1.20:5002", "192.168.1.10:5001"]]

        msg = {
            "type": "DATA",
            "peer_id": "192.168.1.20:5002",
            "dest_peer_id": "192.168.1.10:5001",
            "data": "hello"
        }

        _handle_data(node, msg)

        # Should still be just 1 message (deduped)
        self.assertEqual(len(node.recieve), 1)


if __name__ == "__main__":
    unittest.main()
