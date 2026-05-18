"""QThread workers for Paramiko SSH shell and SFTP operations."""

import posixpath
import stat
import time
from pathlib import Path
from queue import Empty, Queue

from PyQt5.QtCore import QThread, pyqtSignal

from services import paramiko_service, remote_ops_service


class SshTerminalWorker(QThread):
    output = pyqtSignal(str)
    connected = pyqtSignal(str)
    disconnected = pyqtSignal()
    auth_failed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, remote, password=None, parent=None):
        super().__init__(parent)
        self.remote = remote
        self.password = password
        self._client = None
        self._channel = None
        self._running = True
        self._send_queue = Queue()

    def run(self):
        try:
            paramiko_service.ensure_paramiko()
            self._client, target = paramiko_service.create_ssh_client(self.remote, password=self.password)
            accepted = getattr(self._client, "_accepted_unknown_host", None)
            if accepted:
                self.output.emit("[host key] 首次连接已接受远端 host key: {}\n".format(accepted))
            save_error = getattr(self._client, "_host_key_save_error", None)
            if save_error:
                self.output.emit("[host key] 本地保存提示: {}\n".format(save_error))
            self._channel = self._client.invoke_shell(term="xterm", width=120, height=32)
            self._channel.settimeout(0.0)
            self.connected.emit(target.display)

            while self._running:
                self._drain_send_queue()
                if self._channel.recv_ready():
                    data = self._channel.recv(4096)
                    if not data:
                        break
                    self.output.emit(paramiko_service.decode_ssh_bytes(data))
                if self._channel.closed or self._channel.exit_status_ready():
                    break
                time.sleep(0.03)
        except Exception as exc:
            if not self._running:
                pass
            elif "Authentication" in exc.__class__.__name__:
                self.auth_failed.emit(str(exc))
            else:
                self.failed.emit(str(exc))
        finally:
            self._close()
            self.disconnected.emit()

    def _drain_send_queue(self):
        if self._channel is None:
            return
        while True:
            try:
                data = self._send_queue.get_nowait()
            except Empty:
                return
            self._channel.send(data)

    def send_text(self, text):
        self._send_queue.put(str(text))

    def send_interrupt(self):
        self._send_queue.put("\x03")

    def stop(self):
        self._running = False
        self._close()

    def _close(self):
        try:
            if self._channel is not None:
                self._channel.close()
        except Exception:
            pass
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass


class SftpWorker(QThread):
    listed = pyqtSignal(str, list)
    progress = pyqtSignal(str, int, int)
    file_progress = pyqtSignal(str, int, int, int, int)
    message = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    auth_failed = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, remote, action, payload=None, password=None, parent=None):
        super().__init__(parent)
        self.remote = remote
        self.action = action
        self.payload = dict(payload or {})
        self.password = password
        self._cancel = False
        self._client = None
        self._sftp = None

    def cancel(self):
        self._cancel = True
        self._close()

    def run(self):
        try:
            self._client, _target = paramiko_service.create_ssh_client(self.remote, password=self.password)
            self._emit_host_key_notice()
            self._sftp = self._client.open_sftp()
            if self.action == "list":
                self._list_remote()
            elif self.action == "mkdir":
                self._mkdir_remote()
            elif self.action == "delete_remote":
                self._delete_remote()
            elif self.action == "upload":
                self._upload()
            elif self.action == "download":
                self._download()
            else:
                raise ValueError("Unsupported SFTP action: {}".format(self.action))
        except Exception as exc:
            if "Authentication" in exc.__class__.__name__:
                self.auth_failed.emit(str(exc), {"action": self.action, "payload": self.payload})
            else:
                if self._cancel:
                    self.finished_ok.emit("传输已取消")
                else:
                    self.failed.emit(str(exc))
        finally:
            self._close()

    def _emit_host_key_notice(self):
        accepted = getattr(self._client, "_accepted_unknown_host", None)
        if accepted:
            self.message.emit("首次连接已接受远端 host key: {}".format(accepted))
        save_error = getattr(self._client, "_host_key_save_error", None)
        if save_error:
            self.message.emit("host key 本地保存提示: {}".format(save_error))

    def _list_remote(self):
        remote_path = self.payload.get("remote_path") or "."
        remote_path = self._sftp.normalize(remote_path)
        attrs = self._sftp.listdir_attr(remote_path)
        items = [paramiko_service.sftp_attr_to_item(attr.filename, attr) for attr in attrs]
        items.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        parent = paramiko_service.parent_remote_path(remote_path)
        rows = [{
            "name": "..",
            "is_dir": True,
            "size": 0,
            "mtime": 0,
            "permission": "<UP>",
            "path": parent,
        }]
        for item in items:
            item["path"] = paramiko_service.join_remote_path(remote_path, item["name"])
            rows.append(item)
        self.listed.emit(remote_path, rows)
        self.finished_ok.emit("远端目录已刷新: {}".format(remote_path))

    def _mkdir_remote(self):
        remote_path = self.payload.get("remote_path") or ""
        reason = remote_ops_service.remote_path_refusal_reason(remote_path)
        if reason:
            raise ValueError(reason)
        self._sftp.mkdir(remote_path)
        self.finished_ok.emit("已创建远端目录: {}".format(remote_path))

    def _delete_remote(self):
        remote_paths = self.payload.get("remote_paths") or []
        for remote_path in remote_paths:
            reason = remote_ops_service.remote_path_refusal_reason(remote_path, destructive=True)
            if reason:
                raise ValueError("{}: {}".format(remote_path, reason))
            self._delete_remote_path(remote_path)
        self.finished_ok.emit("已删除远端路径: {} 项".format(len(remote_paths)))

    def _delete_remote_path(self, remote_path):
        attr = self._sftp.stat(remote_path)
        if stat.S_ISDIR(attr.st_mode):
            for child in self._sftp.listdir_attr(remote_path):
                self._delete_remote_path(paramiko_service.join_remote_path(remote_path, child.filename))
            self._sftp.rmdir(remote_path)
        else:
            self._sftp.remove(remote_path)

    def _upload(self):
        local_paths = self.payload.get("local_paths") or []
        remote_dir = self.payload.get("remote_dir") or "."
        entries = list(paramiko_service.iter_local_transfer_entries(local_paths))
        total = len(entries)
        for index, (source, relative, is_dir) in enumerate(entries, start=1):
            if self._cancel:
                self.finished_ok.emit("传输已取消")
                return
            remote_path = paramiko_service.join_remote_path(remote_dir, relative)
            if is_dir:
                paramiko_service.ensure_remote_dir(self._sftp, remote_path)
                self.progress.emit("创建远端目录 {}".format(relative), index, total)
                continue
            paramiko_service.ensure_remote_dir(self._sftp, posixpath.dirname(remote_path))
            self.progress.emit("上传 {}".format(relative), index, total)
            self._sftp.put(
                str(source),
                remote_path,
                callback=self._progress_callback("上传 {}".format(relative), index, total),
            )
        self.finished_ok.emit("上传完成: {} 项".format(total))

    def _download(self):
        remote_paths = self.payload.get("remote_paths") or []
        local_dir = Path(self.payload.get("local_dir") or ".")
        local_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for remote_path in remote_paths:
            entries.extend(list(paramiko_service.remote_walk_entries(self._sftp, remote_path)))
        total = len(entries)
        for index, (remote_path, relative, is_dir) in enumerate(entries, start=1):
            if self._cancel:
                self.finished_ok.emit("传输已取消")
                return
            local_path = local_dir / Path(relative)
            if is_dir:
                local_path.mkdir(parents=True, exist_ok=True)
                self.progress.emit("创建本地目录 {}".format(relative), index, total)
                continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            self.progress.emit("下载 {}".format(relative), index, total)
            self._sftp.get(
                remote_path,
                str(local_path),
                callback=self._progress_callback("下载 {}".format(relative), index, total),
            )
        self.finished_ok.emit("下载完成: {} 项".format(total))

    def _progress_callback(self, message, index, total):
        def callback(done, file_size):
            if self._cancel:
                raise RuntimeError("传输已取消")
            self.file_progress.emit(message, index, total, int(done), int(file_size or 0))

        return callback

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
