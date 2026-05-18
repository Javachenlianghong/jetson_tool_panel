import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services import paramiko_service


class ParamikoServiceTest(unittest.TestCase):
    def test_parse_remote_target(self):
        self.assertEqual(paramiko_service.parse_remote_target("192.168.55.1").display, "jetson@192.168.55.1")
        self.assertEqual(paramiko_service.parse_remote_target("192.168.55.1:2222").display, "jetson@192.168.55.1:2222")
        self.assertEqual(paramiko_service.parse_remote_target("root@192.168.1.30").display, "root@192.168.1.30")
        self.assertEqual(paramiko_service.parse_remote_target("root@192.168.1.30:2222").port, 2222)
        self.assertEqual(paramiko_service.parse_remote_target("root@[fe80::1]:2200").port, 2200)
        with self.assertRaises(ValueError):
            paramiko_service.parse_remote_target("")

    def test_sftp_attr_to_item(self):
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=4096, st_mtime=100)
        file_attr = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_size=12, st_mtime=101)

        self.assertTrue(paramiko_service.sftp_attr_to_item("demo", directory)["is_dir"])
        file_item = paramiko_service.sftp_attr_to_item("run.log", file_attr)
        self.assertFalse(file_item["is_dir"])
        self.assertEqual(file_item["permission"], "-rw-r--r--")

    def test_remote_path_helpers(self):
        self.assertEqual(paramiko_service.join_remote_path("/home/jetson", "demo"), "/home/jetson/demo")
        self.assertEqual(paramiko_service.parent_remote_path("/home/jetson/demo"), "/home/jetson")
        self.assertEqual(paramiko_service.parent_remote_path("/"), "/")

    def test_iter_local_transfer_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            single = root / "a.txt"
            single.write_text("a", encoding="utf-8")
            folder = root / "dir"
            empty = folder / "empty"
            empty.mkdir(parents=True)
            nested = folder / "nested" / "b.txt"
            nested.parent.mkdir(parents=True)
            nested.write_text("b", encoding="utf-8")

            sources = list(paramiko_service.iter_local_transfer_sources([single, folder]))
            entries = list(paramiko_service.iter_local_transfer_entries([folder]))

        rels = [rel for _source, rel in sources]
        self.assertIn("a.txt", rels)
        self.assertIn("dir/nested/b.txt", rels)
        entry_map = {rel: is_dir for _source, rel, is_dir in entries}
        self.assertTrue(entry_map["dir"])
        self.assertTrue(entry_map["dir/empty"])
        self.assertFalse(entry_map["dir/nested/b.txt"])


if __name__ == "__main__":
    unittest.main()
