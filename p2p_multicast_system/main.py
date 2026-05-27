import sys
import os

# Add the directory containing main.py to sys.path to allow execution 
# without needing extra environment variables (PYTHONPATH) setup.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.node import P2PNode

def main():
    """Main entrypoint for starting a P2P Multicast node."""
    try:
        node = P2PNode()
        node.start()
    except KeyboardInterrupt:
        print("\nShutdown signal received. Exiting peer node...")
        sys.exit(0)

if __name__ == "__main__":
    main()
