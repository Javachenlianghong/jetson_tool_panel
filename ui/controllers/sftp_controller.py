"""SFTP file-browser UI controller."""

import hashlib
import os
import posixpath
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox, QTableWidgetItem

from core.ssh_workers import SftpWorker
from services import paramiko_service, remote_ops_service


class SftpControllerMixin:
    def _format_file_size(self, size, is_dir=False):
        if is_dir:
            return "<DIR>"
        try:
            size = int(size)
        except (TypeError, ValueError):
            return ""
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return "{} {}".format(int(value), unit)
                return "{:.1f} {}".format(value, unit)
            value /= 1024
        return str(size)

    def _format_mtime(self, mtime):
        try:
            if not int(mtime):
                return ""
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(mtime)))
        except (TypeError, ValueError, OSError):
            return ""

    def _set_file_table_rows(self, table, rows):
        if table is None:
            return
        table.setRowCount(0)
        for row_index, row in enumerate(rows):
            table.insertRow(row_index)
            name_item = QTableWidgetItem(row.get("name", ""))
            name_item.setData(Qt.UserRole, row)
            table.setItem(row_index, 0, name_item)
            table.setItem(row_index, 1, QTableWidgetItem(self._format_file_size(row.get("size", 0), row.get("is_dir", False))))
            table.setItem(row_index, 2, QTableWidgetItem(self._format_mtime(row.get("mtime", 0))))
            table.setItem(row_index, 3, QTableWidgetItem(row.get("permission", "")))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(False)

    def _selected_file_rows(self, table):
        rows = []
        if table is None:
            return rows
        seen = set()
        for item in table.selectedItems():
            row_index = item.row()
            if row_index in seen:
                continue
            seen.add(row_index)
            name_item = table.item(row_index, 0)
            if name_item:
                rows.append(name_item.data(Qt.UserRole) or {})
        return rows

    def _select_context_file_row(self, table, pos):
        if table is None:
            return []
        item = table.itemAt(pos)
        if item is not None:
            selected_rows = {selected.row() for selected in table.selectedItems()}
            if item.row() not in selected_rows:
                table.clearSelection()
                table.selectRow(item.row())
        return self._selected_file_rows(table)

    def _copy_to_clipboard(self, text, label):
        QApplication.clipboard().setText(text)
        if self.files_summary_label:
            self.files_summary_label.setText("已复制{}。".format(label))
        self._append_log("已复制{}: {}".format(label, text.replace("\n", " | ")))

    def copy_remote_selected_paths(self):
        rows = self._selected_file_rows(self.remote_files_table)
        paths = [row.get("path", "") for row in rows if row.get("path")]
        if not paths and self.remote_file_path_edit is not None:
            paths = [self.remote_file_path_edit.text().strip()]
        paths = [path for path in paths if path]
        if paths:
            self._copy_to_clipboard("\n".join(paths), "远端路径")

    def copy_local_selected_paths(self):
        rows = self._selected_file_rows(self.local_files_table)
        paths = [row.get("path", "") for row in rows if row.get("path")]
        if not paths and self.local_file_path_edit is not None:
            paths = [self.local_file_path_edit.text().strip()]
        paths = [path for path in paths if path]
        if paths:
            self._copy_to_clipboard("\n".join(paths), "本地路径")

    def _remote_cd_target_from_selection(self):
        rows = [row for row in self._selected_file_rows(self.remote_files_table) if row.get("path")]
        if len(rows) == 1:
            row = rows[0]
            path = row.get("path", "")
            if row.get("name") == ".." or row.get("is_dir"):
                return path
            return paramiko_service.parent_remote_path(path)
        return self.remote_file_path_edit.text().strip() if self.remote_file_path_edit is not None else ""

    def remote_open_selected_path(self, remote_path=None):
        path = str(remote_path or self._remote_cd_target_from_selection() or "").strip()
        if not path:
            QMessageBox.warning(self, "缺少远端路径", "没有可进入的远端目录。")
            return
        self.remote_file_path_edit.setText(path)
        self.refresh_remote_files()
        if self.files_summary_label:
            self.files_summary_label.setText("已进入远端目录: {}".format(path))

    def open_local_selected_path(self):
        rows = [row for row in self._selected_file_rows(self.local_files_table) if row.get("path")]
        raw_path = rows[0].get("path") if rows else (self.local_file_path_edit.text().strip() if self.local_file_path_edit else "")
        if not raw_path:
            return
        path = Path(raw_path)
        open_path = path if path.is_dir() else path.parent
        if not open_path.exists():
            QMessageBox.warning(self, "本地路径不存在", str(open_path))
            return
        self._open_local_path(open_path, "无法打开本地路径")

    def _open_local_path(self, path, error_title):
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.warning(self, error_title, str(exc))

    def _remote_preview_local_path(self, remote_path):
        base_name = posixpath.basename(str(remote_path).rstrip("/")) or "remote-file"
        safe_name = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in base_name
        ).strip("._") or "remote-file"
        digest = hashlib.sha1(str(remote_path).encode("utf-8")).hexdigest()[:10]
        return self.paths.config_dir / "remote_preview" / "{}-{}".format(digest, safe_name)

    def preview_remote_selected_file(self, row=None):
        rows = [row] if row is not None else [
            item for item in self._selected_file_rows(self.remote_files_table)
            if item.get("name") != ".."
        ]
        if not rows:
            QMessageBox.warning(self, "未选择远端文件", "请在远端文件列表中选择一个文件。")
            return
        if len(rows) != 1:
            QMessageBox.warning(self, "只能预览一个文件", "本地预览一次只能打开一个远端文件。")
            return
        row = rows[0]
        if row.get("is_dir"):
            QMessageBox.warning(self, "无法预览目录", "请选择具体文件；目录可以进入或下载。")
            return
        remote_path = row.get("path", "")
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "无法确定要预览的远端文件路径。")
            return
        size = int(row.get("size", 0) or 0)
        if size > 50 * 1024 * 1024:
            answer = QMessageBox.question(
                self,
                "文件较大",
                "该文件约 {}，预览需要先下载到本地缓存。是否继续？".format(self._format_file_size(size)),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        local_path = self._remote_preview_local_path(remote_path)
        self._start_sftp_worker("preview", {
            "remote_path": remote_path,
            "local_path": str(local_path),
        })

    def local_file_selection_changed(self):
        if self.sftp_worker and self.sftp_worker.isRunning():
            return
        rows = [row for row in self._selected_file_rows(self.local_files_table) if row.get("name") != ".."]
        if rows and self.files_summary_label:
            self.files_summary_label.setText("本地已选 {} 项".format(len(rows)))

    def remote_file_selection_changed(self):
        if self.sftp_worker and self.sftp_worker.isRunning():
            return
        rows = [row for row in self._selected_file_rows(self.remote_files_table) if row.get("name") != ".."]
        if rows and self.files_summary_label:
            self.files_summary_label.setText("远端已选 {} 项".format(len(rows)))

    def local_files_context_menu(self, pos):
        rows = [row for row in self._select_context_file_row(self.local_files_table, pos) if row.get("name") != ".."]
        menu = QMenu(self)
        upload_action = menu.addAction("上传选中")
        delete_action = menu.addAction("删除本地")
        menu.addSeparator()
        copy_action = menu.addAction("复制本地路径")
        open_action = menu.addAction("在资源管理器中打开")
        refresh_action = menu.addAction("刷新")
        if not rows:
            upload_action.setEnabled(False)
            delete_action.setEnabled(False)
        action = menu.exec_(self.local_files_table.viewport().mapToGlobal(pos))
        if action == upload_action:
            self.sftp_upload_selected()
        elif action == delete_action:
            self.delete_local_selected()
        elif action == copy_action:
            self.copy_local_selected_paths()
        elif action == open_action:
            self.open_local_selected_path()
        elif action == refresh_action:
            self.refresh_local_files()

    def remote_files_context_menu(self, pos):
        rows = [row for row in self._select_context_file_row(self.remote_files_table, pos) if row.get("name") != ".."]
        menu = QMenu(self)
        preview_action = menu.addAction("本地预览")
        download_action = menu.addAction("下载选中")
        cd_action = menu.addAction("进入此目录")
        mkdir_action = menu.addAction("新建远端目录")
        delete_action = menu.addAction("删除远端")
        menu.addSeparator()
        copy_action = menu.addAction("复制远端路径")
        refresh_action = menu.addAction("刷新")
        if not rows:
            preview_action.setEnabled(False)
            download_action.setEnabled(False)
            delete_action.setEnabled(False)
        elif len(rows) != 1 or rows[0].get("is_dir"):
            preview_action.setEnabled(False)
        action = menu.exec_(self.remote_files_table.viewport().mapToGlobal(pos))
        if action == preview_action:
            self.preview_remote_selected_file()
        elif action == download_action:
            self.sftp_download_selected()
        elif action == cd_action:
            self.remote_open_selected_path()
        elif action == mkdir_action:
            self.sftp_mkdir_remote()
        elif action == delete_action:
            self.sftp_delete_remote()
        elif action == copy_action:
            self.copy_remote_selected_paths()
        elif action == refresh_action:
            self.refresh_remote_files()

    def refresh_local_files(self, warn=True):
        path = Path(self.local_file_path_edit.text().strip() or str(self.paths.app_dir))
        if not path.exists():
            if warn:
                QMessageBox.warning(self, "本地路径不存在", str(path))
            elif self.files_summary_label:
                self.files_summary_label.setText("本地路径不存在: {}".format(path))
            return
        if path.is_file():
            path = path.parent
        self.local_file_path_edit.setText(str(path))
        rows = []
        parent = path.parent if path.parent != path else path
        rows.append({"name": "..", "path": str(parent), "is_dir": True, "size": 0, "mtime": 0, "permission": "<UP>"})
        for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            try:
                rows.append(paramiko_service.local_item(child))
            except OSError:
                pass
        self._set_file_table_rows(self.local_files_table, rows)
        if self.files_summary_label:
            self.files_summary_label.setText("本地 {}: {} 项".format(path, max(len(rows) - 1, 0)))

    def refresh_remote_files(self, password=None):
        remote = self._remote_or_warn()
        if not remote:
            return
        remote_path = self.remote_file_path_edit.text().strip() or "."
        self._start_sftp_worker("list", {"remote_path": remote_path}, password=password)

    def browse_local_file_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地目录", self.local_file_path_edit.text())
        if path:
            self.local_file_path_edit.setText(path)
            self.refresh_local_files()

    def local_files_up(self):
        path = Path(self.local_file_path_edit.text().strip() or ".")
        self.local_file_path_edit.setText(str(path.parent if path.parent != path else path))
        self.refresh_local_files()

    def remote_files_up(self):
        self.remote_file_path_edit.setText(paramiko_service.parent_remote_path(self.remote_file_path_edit.text()))
        self.refresh_remote_files()

    def local_file_item_activated(self, item):
        row = self.local_files_table.item(item.row(), 0)
        data = row.data(Qt.UserRole) if row else {}
        if data.get("is_dir"):
            self.local_file_path_edit.setText(data.get("path", self.local_file_path_edit.text()))
            self.refresh_local_files()

    def remote_file_item_activated(self, item):
        row = self.remote_files_table.item(item.row(), 0)
        data = row.data(Qt.UserRole) if row else {}
        if data.get("is_dir"):
            self.remote_file_path_edit.setText(data.get("path", self.remote_file_path_edit.text()))
            self.refresh_remote_files()
        else:
            self.preview_remote_selected_file(data)

    def _start_sftp_worker(self, action, payload, password=None):
        if self.sftp_worker and self.sftp_worker.isRunning():
            QMessageBox.warning(self, "SFTP 正在运行", "请等待当前 SFTP 操作结束，或先取消传输。")
            return
        remote = self._remote_or_warn()
        if not remote:
            return
        self.pending_sftp_refresh = None
        self.sftp_worker = SftpWorker(remote, action, payload, password=password if password is not None else self.sftp_password, parent=self)
        self.sftp_worker.listed.connect(self._sftp_listed)
        self.sftp_worker.progress.connect(self._sftp_progress)
        self.sftp_worker.file_progress.connect(self._sftp_file_progress)
        self.sftp_worker.message.connect(self._sftp_message)
        self.sftp_worker.finished_ok.connect(self._sftp_finished_ok)
        self.sftp_worker.auth_failed.connect(self._sftp_auth_failed)
        self.sftp_worker.failed.connect(self._sftp_failed)
        self.sftp_worker.finished.connect(self._sftp_worker_finished)
        self.sftp_worker.start()
        if self.files_summary_label:
            action_text = {
                "list": "刷新远端目录",
                "upload": "上传",
                "download": "下载",
                "preview": "本地预览",
                "mkdir": "新建远端目录",
                "delete_remote": "删除远端",
            }.get(action, action)
            self.files_summary_label.setText("SFTP {} 正在执行...".format(action_text))
        if self.transfer_progress_bar:
            self.transfer_progress_bar.setValue(0)

    def _sftp_listed(self, path, rows):
        self.remote_file_path_edit.setText(path)
        self._set_file_table_rows(self.remote_files_table, rows)
        if self.files_summary_label:
            self.files_summary_label.setText("远端 {}: {} 项".format(path, max(len(rows) - 1, 0)))

    def _sftp_progress(self, message, index, total):
        if self.files_summary_label:
            self.files_summary_label.setText("{} ({}/{})".format(message, index, total))
        if self.transfer_progress_bar:
            self.transfer_progress_bar.setValue(int(index * 100 / max(total, 1)))

    def _sftp_file_progress(self, message, index, total, done, file_size):
        file_percent = int(done * 100 / file_size) if file_size else 0
        overall = int(((index - 1) + (done / file_size if file_size else 0)) * 100 / max(total, 1))
        if self.files_summary_label:
            self.files_summary_label.setText(
                "{} ({}/{}, {}%)".format(message, index, total, file_percent)
            )
        if self.transfer_progress_bar:
            self.transfer_progress_bar.setValue(max(0, min(100, overall)))

    def _sftp_message(self, message):
        self._append_log("SFTP: " + str(message))

    def _sftp_finished_ok(self, message):
        if self.files_summary_label:
            self.files_summary_label.setText(message)
        if self.transfer_progress_bar and "完成" in message:
            self.transfer_progress_bar.setValue(100)
        action = self.sftp_worker.action if self.sftp_worker else ""
        payload = self.sftp_worker.payload if self.sftp_worker else {}
        if action in ("upload", "mkdir", "delete_remote"):
            self.pending_sftp_refresh = "remote"
        elif action == "download":
            self.pending_sftp_refresh = "local"
        elif action == "preview":
            if self.transfer_progress_bar:
                self.transfer_progress_bar.setValue(100)
            local_raw = payload.get("local_path", "")
            local_path = Path(local_raw) if local_raw else None
            if local_path is not None and local_path.exists():
                self._open_local_path(local_path, "无法预览远端文件")
        self._append_log("SFTP: " + message)

    def _sftp_auth_failed(self, error, retry):
        password = self._prompt_ssh_password("SFTP 认证")
        if password is None:
            self._sftp_failed("SFTP 认证失败: " + str(error))
            return
        self.sftp_password = password
        self.pending_sftp_retry = (retry, password)

    def _sftp_failed(self, error):
        if self.files_summary_label:
            self.files_summary_label.setText("SFTP 失败: " + str(error))
        self.pending_sftp_refresh = None
        self.pending_sftp_retry = None
        self._append_log("SFTP 失败: " + str(error))

    def _sftp_worker_finished(self):
        sender = self.sender()
        if sender is self.sftp_worker:
            self.sftp_worker = None
        if self.pending_sftp_retry:
            retry, password = self.pending_sftp_retry
            self.pending_sftp_retry = None
            self._start_sftp_worker(retry.get("action"), retry.get("payload"), password=password)
            return
        refresh_target = self.pending_sftp_refresh
        self.pending_sftp_refresh = None
        if refresh_target == "remote":
            QTimer.singleShot(100, self.refresh_remote_files)
        elif refresh_target == "local":
            QTimer.singleShot(0, self.refresh_local_files)

    def sftp_upload_selected(self):
        rows = [row for row in self._selected_file_rows(self.local_files_table) if row.get("name") != ".."]
        if not rows:
            QMessageBox.warning(self, "未选择本地文件", "请在左侧选择要上传的文件或目录。")
            return
        local_paths = [row.get("path") for row in rows if row.get("path")]
        self._start_sftp_worker("upload", {
            "local_paths": local_paths,
            "remote_dir": self.remote_file_path_edit.text().strip() or ".",
        })

    def sftp_download_selected(self):
        rows = [row for row in self._selected_file_rows(self.remote_files_table) if row.get("name") != ".."]
        if not rows:
            QMessageBox.warning(self, "未选择远端文件", "请在右侧选择要下载的文件或目录。")
            return
        remote_paths = [row.get("path") for row in rows if row.get("path")]
        self._start_sftp_worker("download", {
            "remote_paths": remote_paths,
            "local_dir": self.local_file_path_edit.text().strip() or str(self.paths.app_dir),
        })

    def sftp_mkdir_remote(self):
        name, ok = QInputDialog.getText(self, "新建远端目录", "目录名")
        if not ok or not name.strip():
            return
        directory_name = name.strip()
        if directory_name in (".", "..") or "/" in directory_name or "\\" in directory_name or ".." in directory_name:
            QMessageBox.warning(self, "目录名不安全", "请输入单级目录名，不能包含路径分隔符或 '..'。")
            return
        remote_path = paramiko_service.join_remote_path(self.remote_file_path_edit.text().strip() or ".", directory_name)
        reason = remote_ops_service.remote_path_refusal_reason(remote_path)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", reason)
            return
        self._start_sftp_worker("mkdir", {"remote_path": remote_path})

    def sftp_delete_remote(self):
        rows = [row for row in self._selected_file_rows(self.remote_files_table) if row.get("name") != ".."]
        if not rows:
            QMessageBox.warning(self, "未选择远端路径", "请在右侧选择要删除的路径。")
            return
        remote_paths = [row.get("path") for row in rows if row.get("path")]
        for remote_path in remote_paths:
            reason = remote_ops_service.remote_path_refusal_reason(remote_path, destructive=True)
            if reason:
                QMessageBox.warning(self, "远端路径不安全", "{}\n{}".format(remote_path, reason))
                return
        answer = QMessageBox.question(self, "确认删除远端路径", "确定删除选中的 {} 个远端路径？".format(len(remote_paths)), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._start_sftp_worker("delete_remote", {"remote_paths": remote_paths})

    def delete_local_selected(self):
        rows = [row for row in self._selected_file_rows(self.local_files_table) if row.get("name") != ".."]
        if not rows:
            QMessageBox.warning(self, "未选择本地路径", "请在左侧选择要删除的路径。")
            return
        answer = QMessageBox.question(self, "确认删除本地路径", "确定删除选中的 {} 个本地路径？".format(len(rows)), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        errors = []
        for row in rows:
            path = Path(row.get("path", ""))
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
            except OSError as exc:
                errors.append("{}: {}".format(path, exc))
        self.refresh_local_files()
        if errors:
            QMessageBox.warning(self, "部分本地路径删除失败", "\n".join(errors[:5]))
            self._append_log("本地删除失败: " + " | ".join(errors[:5]))

    def sftp_cancel_transfer(self):
        if self.sftp_worker and self.sftp_worker.isRunning():
            self.sftp_worker.cancel()
            if self.files_summary_label:
                self.files_summary_label.setText("正在取消传输...")
