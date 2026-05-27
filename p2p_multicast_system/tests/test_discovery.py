import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.discovery import start_discovery_sender, start_discovery_listener

class TestDiscovery(unittest.TestCase):
    @patch('core.discovery.threading.Thread')
    def test_start_discovery_sender(self, mock_thread):
        """Verify that start_discovery_sender starts a background daemon thread."""
        node = MagicMock()
        node.running = True

        thread = start_discovery_sender(node)

        self.assertIsNotNone(thread)
        mock_thread.assert_called_once()
        # Ensure it is a daemon thread
        self.assertTrue(mock_thread.call_args_list[0][1]['daemon'])

    @patch('core.discovery.threading.Thread')
    def test_start_discovery_listener(self, mock_thread):
        """Verify that start_discovery_listener starts a background daemon thread."""
        node = MagicMock()
        node.running = True

        thread = start_discovery_listener(node)

        self.assertIsNotNone(thread)
        mock_thread.assert_called_once()
        # Ensure it is a daemon thread
        self.assertTrue(mock_thread.call_args_list[0][1]['daemon'])

if __name__ == "__main__":
    unittest.main()
