"""Configuration management module for saving and restoring node and peer states."""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional


class ConfigManager:
    """
    Manages loading and saving peer configurations to disk.

    Supports batched saving: call mark_dirty() when state changes,
    and a background saver thread flushes changes to disk periodically.
    """

    def __init__(self, port: int, storage_dir: Optional[str] = None):
        self.port = port
        if storage_dir:
            self.storage_dir = os.path.abspath(storage_dir)
        else:
            # Default to storage/configs in current working directory or relative to root
            self.storage_dir = os.path.abspath(os.path.join(".", "storage", "configs"))

        self.config_file = os.path.join(self.storage_dir, f"{self.port}.json")

        # Ensure directory exists
        os.makedirs(self.storage_dir, exist_ok=True)

        self._dirty = False
        self._dirty_lock = threading.Lock()

    def save_config(
        self,
        peer_id: str,
        host: str,
        registered_nodes: List[str],
        peers: Dict[str, Any],
        sent: Optional[List[Any]] = None,
        recieve: Optional[List[Any]] = None,
    ):
        """Saves current state (registered nodes and discovered peers) to config file."""
        data = {
            "peer_id": peer_id,
            "host": host,
            "port": self.port,
            "registered_nodes": list(registered_nodes),
            "peers": dict(peers),
            "sent": list(sent or []),
            "recieve": list(recieve or []),
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def mark_dirty(self):
        """Flag that config has changed and requires saving."""
        with self._dirty_lock:
            self._dirty = True

    def is_dirty(self) -> bool:
        """Check if unsaved changes exist."""
        with self._dirty_lock:
            return self._dirty

    def clear_dirty(self):
        """Clear dirty flag after successful save."""
        with self._dirty_lock:
            self._dirty = False

    def load_config(self) -> Optional[Dict[str, Any]]:
        """Loads and returns configuration dictionary if file exists, else None."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None


def start_config_saver(node: Any, interval: float = 5.0) -> threading.Thread:
    """
    Start a background daemon thread that flushes config to disk
    periodically if marked dirty.
    """
    def saver_loop():
        while getattr(node, "running", True):
            time.sleep(interval)
            config_mgr = getattr(node, "config_manager", None)
            if config_mgr and config_mgr.is_dirty():
                lock = getattr(node, "lock", None)
                if lock:
                    with lock:
                        if hasattr(node, "save_config"):
                            node.save_config()
                else:
                    if hasattr(node, "save_config"):
                        node.save_config()
                config_mgr.clear_dirty()

    thread = threading.Thread(target=saver_loop, daemon=True, name="ConfigSaverThread")
    thread.start()
    return thread
