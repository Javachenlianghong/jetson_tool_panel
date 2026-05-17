"""Persistent recent command history."""

import json
from pathlib import Path


class TaskHistoryStore:
    def __init__(self, path, limit=100):
        self.path = Path(path)
        self.limit = limit

    def load(self):
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def add(self, entry):
        history = self.load()
        history.insert(0, dict(entry))
        history = history[: self.limit]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return history
