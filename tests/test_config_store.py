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

    def test_recovers_and_saves_malformed_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config" / "projects.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text("{not valid json", encoding="utf-8")

            store = self._store(tmp)

            self.assertTrue(config_path.exists())
            self.assertTrue(config_path.with_suffix(".json.broken").exists())
            self.assertEqual(store.active_device()["ssh"], "jetson@192.168.55.1")
            self.assertIn('"version": 1', config_path.read_text(encoding="utf-8"))

    def test_normalizes_and_saves_partial_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config" / "projects.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"devices": [{"id": "dev"}], "projects": []}', encoding="utf-8")

            store = self._store(tmp)

            saved = config_path.read_text(encoding="utf-8")
            self.assertEqual(store.active_device()["name"], "dev")
            self.assertTrue(store.projects())
            self.assertIn('"active_device_id": "dev"', saved)
            self.assertIn('"projects"', saved)


if __name__ == "__main__":
    unittest.main()
