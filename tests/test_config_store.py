import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.config_store import ProjectConfigStore


class ProjectConfigStoreTest(unittest.TestCase):
    def _store(self, root):
        defaults = SimpleNamespace(
            remote="jetson@192.168.55.1",
            remote_path="/home/jetson/project",
            proxy_port=7897,
        )
        paths = SimpleNamespace(
            app_dir=Path(root),
            project_dir=Path(root) / "project",
        )
        return ProjectConfigStore(Path(root) / "config" / "projects.json", defaults, paths)

    def test_creates_default_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            self.assertTrue(store.path.exists())
            self.assertEqual(store.active_device()["ssh"], "jetson@192.168.55.1")
            self.assertEqual(store.active_project()["remote_root"], "/home/jetson/project")

    def test_upserts_device_and_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            device_id = store.upsert_device({
                "id": "rk3588",
                "name": "RK3588",
                "type": "rk3588",
                "ssh": "root@192.168.1.30",
                "proxy_host": "192.168.1.11",
                "proxy_port": 7897,
            })
            project_id = store.upsert_project({
                "id": "demo",
                "device_id": device_id,
                "name": "Demo",
                "local_root": "C:/demo",
                "remote_root": "/home/root/demo",
                "build_command": "make",
                "run_command": "./demo",
                "stop_pattern": "demo",
                "log_target": "run.log",
                "model_profiles": [],
            })
            store.set_active_project(project_id)
            self.assertEqual(store.active_device()["id"], "rk3588")
            self.assertEqual(store.active_project()["run_command"], "./demo")


if __name__ == "__main__":
    unittest.main()
