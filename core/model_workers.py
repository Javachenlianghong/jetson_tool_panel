"""Workers for model deployment helpers."""

import posixpath
import time

from PyQt5.QtCore import QThread, pyqtSignal

from services import paramiko_service


MODEL_EXTENSIONS = (".onnx", ".engine", ".rknn", ".pt", ".pth", ".tflite")
SKIP_DIRS = {".git", "__pycache__", "build", "cmake-build-debug", "cmake-build-release"}


def scan_remote_model_files(sftp, root, max_depth=3, deadline=None, cancel_check=None):
    root = sftp.normalize(root or ".")
    candidates = []
    stack = [(root, 0)]
    while stack:
        if cancel_check and cancel_check():
            break
        if deadline and time.monotonic() > deadline:
            raise TimeoutError("扫描远端模型文件超时。")
        directory, depth = stack.pop()
        try:
            attrs = sftp.listdir_attr(directory)
        except OSError:
            continue
        for attr in attrs:
            if cancel_check and cancel_check():
                break
            name = attr.filename
            if name in (".", ".."):
                continue
            remote_path = paramiko_service.join_remote_path(directory, name)
            item = paramiko_service.sftp_attr_to_item(name, attr)
            if item.get("is_dir"):
                if depth < max_depth and name not in SKIP_DIRS:
                    stack.append((remote_path, depth + 1))
                continue
            if name.lower().endswith(MODEL_EXTENSIONS):
                relative = posixpath.relpath(remote_path, root)
                candidates.append(relative if not relative.startswith("..") else remote_path)
    return sorted(set(candidates), key=lambda item: (item.count("/"), item.lower()))


class RemoteModelScanWorker(QThread):
    candidates_ready = pyqtSignal(list)
    auth_failed = pyqtSignal(str)
    failed = pyqtSignal(str)
    message = pyqtSignal(str)

    def __init__(self, remote, workdir, password=None, timeout_seconds=20, parent=None):
        super().__init__(parent)
        self.remote = remote
        self.workdir = workdir or "."
        self.password = password
        self.timeout_seconds = max(1, int(timeout_seconds or 20))
        self._cancel = False
        self._client = None
        self._sftp = None

    def cancel(self):
        self._cancel = True
        self._close()

    def run(self):
        try:
            self.message.emit("正在扫描远端模型文件...")
            self._client, _target = paramiko_service.create_ssh_client(
                self.remote,
                password=self.password,
                timeout=min(self.timeout_seconds, 10),
            )
            self._sftp = self._client.open_sftp()
            deadline = time.monotonic() + self.timeout_seconds
            candidates = scan_remote_model_files(
                self._sftp,
                self.workdir,
                deadline=deadline,
                cancel_check=lambda: self._cancel,
            )
            if not self._cancel:
                self.candidates_ready.emit(candidates)
        except Exception as exc:
            if self._cancel:
                self.message.emit("模型文件扫描已取消。")
            elif "Authentication" in exc.__class__.__name__:
                self.auth_failed.emit(str(exc))
            else:
                self.failed.emit(str(exc))
        finally:
            self._close()

    def _close(self):
        try:
            if self._sftp is not None:
                self._sftp.close()
        except Exception:
            pass
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass
