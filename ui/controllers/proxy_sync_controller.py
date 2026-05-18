"""SSH key, proxy script and project sync controller."""

import base64
import os
import subprocess
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem

from services import proxy_service, ssh_service


class ProxySyncControllerMixin:
    def _update_sync_preview(self, preview):
        self.last_sync_preview = dict(preview or {})
        if self.sync_preview_summary_label is not None:
            notes = self.last_sync_preview.get("notes") or []
            suffix = (" " + " | ".join(notes[:2])) if notes else ""
            self.sync_preview_summary_label.setText(self.last_sync_preview.get("summary", "同步预览已更新。") + suffix)
        if self.sync_preview_table is None:
            return
        self.sync_preview_table.setRowCount(0)
        rows = self.last_sync_preview.get("rows") or []
        for row_index, row in enumerate(rows):
            self.sync_preview_table.insertRow(row_index)
            action = {
                "upload": "上传",
                "delete": "删除",
                "more": "更多",
            }.get(row.get("action"), row.get("action", ""))
            values = [action, row.get("path", ""), row.get("detail", "")]
            for column, value in enumerate(values):
                self.sync_preview_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.sync_preview_table.resizeColumnsToContents()
        self.sync_preview_table.horizontalHeader().setStretchLastSection(False)

    def configure_ssh_key(self):
        remote = self._remote_or_warn()
        if not remote:
            return

        self._save_settings()
        script = ssh_service.ssh_key_setup_script(remote)
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ]

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
            creationflags = subprocess.CREATE_NEW_CONSOLE

        try:
            subprocess.Popen(command, cwd=str(self.paths.app_dir), creationflags=creationflags)
        except Exception as exc:
            QMessageBox.critical(self, "无法打开配置窗口", str(exc))
            return

        self._append_log("已打开 SSH Key 配置窗口。按提示输入 Jetson 密码，完成后再点击“测试 SSH”。")

    def upload_proxy_script(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if not self.paths.jetson_proxy_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.jetson_proxy_script))
            return

        self._run_command(
            "上传代理脚本到 Jetson",
            ssh_service.upload_proxy_script_command(self.paths.jetson_proxy_script, remote),
            cwd=self.paths.app_dir,
        )

    def disable_jetson_proxy_config(self):
        if not self._remote_or_warn():
            return
        self.pending_terminal_command = proxy_service.disable_jetson_proxy_command().strip() + "\n"
        self._switch_page_by_key("terminal")
        self._append_log("已准备在 SSH 工作台取消 Jetson 代理配置；如出现 sudo 提示，请输入 Jetson 密码。")
        if self.terminal_worker and self.terminal_worker.isRunning():
            QTimer.singleShot(200, self._send_pending_terminal_command)
        else:
            self.terminal_connect()

    def pull_from_jetson(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        remote_path = self.remote_path_edit.text().strip()
        local_root = Path(self.local_root_edit.text().strip())
        if not remote_path:
            QMessageBox.warning(self, "缺少参数", "请填写 Jetson 项目路径。")
            return
        if not local_root.exists():
            QMessageBox.warning(self, "目录不存在", "Windows 保存目录不存在: {}".format(local_root))
            return

        self._run_command(
            "从 Jetson 拉取项目",
            ssh_service.pull_project_command(remote, remote_path),
            cwd=local_root,
        )

    def init_sync_state(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        remote = self._remote_or_warn()
        if not remote:
            return
        command = ssh_service.sync_command(
            self.paths.sync_script,
            remote,
            self.remote_path_edit.text().strip(),
            init=True,
        )
        self._run_command("初始化同步状态", command, cwd=self.paths.project_dir)

    def preview_sync_to_jetson(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        remote = self._remote_or_warn()
        if not remote:
            return
        command = ssh_service.sync_command(
            self.paths.sync_script,
            remote,
            self.remote_path_edit.text().strip(),
            full=self.full_sync_check.isChecked(),
            dry_run=True,
            no_delete=self.no_delete_check.isChecked(),
        )
        self._run_command("预览同步变更", command, cwd=self.paths.project_dir)

    def sync_to_jetson(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        remote = self._remote_or_warn()
        if not remote:
            return

        command = ssh_service.sync_command(
            self.paths.sync_script,
            remote,
            self.remote_path_edit.text().strip(),
            full=self.full_sync_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            no_delete=self.no_delete_check.isChecked(),
        )
        self._run_command("同步到 Jetson", command, cwd=self.paths.project_dir)
