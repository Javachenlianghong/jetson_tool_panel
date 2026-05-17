import tempfile
import unittest
from pathlib import Path

from core.task_history import TaskHistoryStore


class TaskHistoryStoreTest(unittest.TestCase):
    def test_add_limits_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskHistoryStore(Path(tmp) / "history.json", limit=2)
            store.add({"title": "first"})
            store.add({"title": "second"})
            store.add({"title": "third"})
            history = store.load()
            self.assertEqual([item["title"] for item in history], ["third", "second"])


if __name__ == "__main__":
    unittest.main()
