import stat
import unittest

from core.model_workers import scan_remote_model_files


class FakeAttr:
    def __init__(self, filename, mode):
        self.filename = filename
        self.st_mode = mode
        self.st_size = 0
        self.st_mtime = 0


class FakeSftp:
    def __init__(self, tree):
        self.tree = tree

    def normalize(self, path):
        return path.rstrip("/") or "."

    def listdir_attr(self, path):
        return self.tree.get(path, [])


def directory(name):
    return FakeAttr(name, stat.S_IFDIR | 0o755)


def file(name):
    return FakeAttr(name, stat.S_IFREG | 0o644)


class ModelWorkersTest(unittest.TestCase):
    def test_scan_remote_model_files_returns_relative_model_paths(self):
        sftp = FakeSftp({
            "/home/jetson/project": [
                directory("models"),
                directory(".git"),
                file("README.md"),
                file("root.engine"),
            ],
            "/home/jetson/project/models": [
                file("yolov8n.onnx"),
                file("notes.txt"),
                directory("nested"),
            ],
            "/home/jetson/project/models/nested": [
                file("best.pt"),
            ],
            "/home/jetson/project/.git": [
                file("ignored.onnx"),
            ],
        })

        result = scan_remote_model_files(sftp, "/home/jetson/project")

        self.assertEqual(result, ["root.engine", "models/yolov8n.onnx", "models/nested/best.pt"])

    def test_scan_remote_model_files_honors_cancel_check(self):
        sftp = FakeSftp({
            "/project": [
                file("model.onnx"),
            ],
        })

        self.assertEqual(scan_remote_model_files(sftp, "/project", cancel_check=lambda: True), [])


if __name__ == "__main__":
    unittest.main()
