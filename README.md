# P2P Multicast System

A decentralized peer-to-peer multicast network system built using Python's standard libraries (`socket`, `threading`). It supports dynamic peer discovery via UDP multicast, registered node indexing, and automated heartbeat monitoring for peer health tracking.

## Reorganized Modular Architecture

The monolithic system has been organized into a robust structure to improve testability and maintainability:

```
p2p_multicast_system/
│
├── main.py                    # Application main entrypoint
│
├── core/                      # Core network and orchestrator package
│   ├── __init__.py
│   ├── node.py                # Main P2PNode class
│   ├── discovery.py           # Multicast sender and listener services
│   ├── health_monitor.py      # Heartbeat check and dead peer pruning service
│   └── config_manager.py      # State saving and configuration manager
│
├── utils/                     # Utility functions and settings package
│   ├── __init__.py
│   ├── hashing.py             # SHA-256 state hashing utility
│   └── constants.py           # Network settings and time durations
│
├── storage/                   # Configuration store
│   └── configs/               # Folder storing {port}.json peer states
│
├── docs/                      # Documentation
│   ├── design_document.md     # In-depth architectural design
│   ├── architecture_diagram.png # visual design diagram
│   └── workflow.md            # Interaction workflow details
│
└── tests/                     # Unit testing suite
    ├── test_hashing.py
    ├── test_discovery.py
    └── test_health_monitor.py
```

## Getting Started

### Prerequisites
- Python 3.8 or higher.
- `pytest` (Optional, for running tests). Install via `pip install -r requirements.txt`.

### How to Run
To boot a node:
1. In a terminal, run:
   ```bash
   python p2p_multicast_system/main.py
   ```
2. You will be prompted to enter a port (e.g. `5001`).
3. The peer node will initialize and start listing active peers.

To run multiple nodes locally:
1. Open a second terminal window.
2. Run the same command:
   ```bash
   python p2p_multicast_system/main.py
   ```
3. Enter a different port (e.g. `5002`).
4. Nodes will instantly discover each other using dynamic multicast notifications and save peer list state to `p2p_multicast_system/storage/configs/`.

### Commands
Once inside a node shell, you can use the following commands:
- `register`: Prompts for a channel/node string to associate with the current peer.
- `view nodes`: Prints list of all registered nodes across discovered peers.
- `view peers`: Prints IP/Port and SHA-256 state checksum hash of all active peers.
- `exit`: Shutdown the node gracefully.

## Running Tests

To run the complete suite of tests:
```bash
python -m unittest discover -s p2p_multicast_system/tests
```
Or, if you installed `pytest`:
```bash
pytest p2p_multicast_system/
```
