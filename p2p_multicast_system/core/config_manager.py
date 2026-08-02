import os
import json

class ConfigManager:
    """
    Manages loading and saving peer configurations.
    Configs are saved under `storage/configs/<port>.json` relative to the root directory.
    """
    def __init__(self, port):
        self.port = port
        # Resolve config storage relative to this file's package root
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.storage_dir = os.path.join(base_dir, "storage", "configs")
        self.config_file = os.path.join(self.storage_dir, f"{port}.json")
        
        # Ensure the storage directory exists
        os.makedirs(self.storage_dir, exist_ok=True)

    def save_config(self, peer_id: str, host: str, registered_nodes: list, peers: dict,sent:list,recieve:list):
        """Saves current state (registered nodes and discovered peers) to config file."""
        data = {
            "peer_id": peer_id,
            "host": host,
            "port": self.port,
            "registered_nodes": registered_nodes,
            "peers": peers,
            "sent":sent,
            "recieve":recieve
        }
        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=4)

    def load_config(self) -> dict:
        """Loads and returns config if it exists, otherwise returns None."""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                return json.load(f)
        return None
