import sys
import os
import unittest

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hashing import generate_hash

class TestHashing(unittest.TestCase):
    def test_hash_consistency(self):
        """Verify that hashing same value multiple times yields identical results."""
        val = "127.0.0.1:5001"
        h1 = generate_hash(val)
        h2 = generate_hash(val)
        self.assertEqual(h1, h2)

    def test_hash_length_and_type(self):
        """Verify that the generated hash is a valid SHA-256 string (64 characters)."""
        val = "test-node"
        h = generate_hash(val)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)

    def test_hash_uniqueness(self):
        """Verify that different values produce different hashes."""
        h1 = generate_hash("node1")
        h2 = generate_hash("node2")
        self.assertNotEqual(h1, h2)

if __name__ == "__main__":
    unittest.main()
