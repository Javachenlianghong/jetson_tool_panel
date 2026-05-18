"""SSH terminal UI controller."""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from core.ssh_workers import SshTerminalWorker


class TerminalControllerMixin:
    def terminal_connect(self, password=None):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.terminal_worker and self.terminal_worker.isRunning():
            QMessageBox.information(self, "终端已连接", "当前 SSH 终端会话仍在运行。")
            return
        if self.terminal_status_label:
            self.terminal_status_label.setText("连接中...")
        if self.terminal_output_edit:
            terminal_text = self.terminal_buffer.to_text()
            prefix = "\n" if terminal_text and not terminal_text.endswith("\n") else ""
            self._terminal_append_text("{}[连接] {}\n".format(prefix, remote))
        self.terminal_worker = SshTerminalWorker(remote, password=password, parent=self)
        self.terminal_worker.output.connect(self._terminal_output)
        self.terminal_worker.connected.connect(self._terminal_connected)
        self.terminal_worker.auth_failed.connect(self._terminal_auth_failed)
        self.terminal_worker.failed.connect(self._terminal_failed)
        self.terminal_worker.disconnected.connect(self._terminal_disconnected)
        self.terminal_worker.start()
        self._refresh_task_center()

    def terminal_disconnect(self):
        if self.terminal_worker and self.terminal_worker.isRunning():
            self.terminal_worker.stop()
            self.terminal_worker.wait(2000)
        if self.terminal_status_label:
            self.terminal_status_label.setText("已断开")
        self._refresh_task_center()

    def terminal_send_text(self, text, warn=False):
        if not text:
            return
        if not self.terminal_worker or not self.terminal_worker.isRunning():
            if warn:
                QMessageBox.warning(self, "终端未连接", "请先连接 SSH 终端。")
            elif self.terminal_status_label:
                self.terminal_status_label.setText("未连接")
            return
        self.terminal_worker.send_text(text)

    def terminal_interrupt(self):
        if self.terminal_worker and self.terminal_worker.isRunning():
            self.terminal_worker.send_interrupt()

    def terminal_clear(self):
        self.terminal_buffer.clear()
        if self.terminal_output_edit:
            self.terminal_output_edit.clear()

    def terminal_send_quick_command(self):
        if self.terminal_quick_command_combo is None:
            return
        command = self.terminal_quick_command_combo.currentText().strip()
        mapping = {
            "cd 项目目录": "cd {}".format(self.remote_path_edit.text().strip() or "~"),
            "检测 DISPLAY": "printf 'DISPLAY=%s\\nXAUTHORITY=%s\\n' \"$DISPLAY\" \"$XAUTHORITY\"; xdpyinfo >/dev/null 2>&1 && echo DISPLAY_OK || echo DISPLAY_FAIL",
            "查看 run-control.log": "tail -n 120 -f run-control.log",
            "停止 tegrastats": "pkill -f tegrastats || true",
        }
        self.terminal_send_text(mapping.get(command, command) + "\n", warn=True)

    def terminal_cd_project(self):
        self.terminal_send_text("cd {}\n".format(self.remote_path_edit.text().strip() or "~"), warn=True)

    def terminal_check_display(self):
        self.terminal_send_text(
            "printf 'DISPLAY=%s\\nXAUTHORITY=%s\\n' \"$DISPLAY\" \"$XAUTHORITY\"; "
            "xdpyinfo >/dev/null 2>&1 && echo DISPLAY_OK || echo DISPLAY_FAIL\n",
            warn=True,
        )

    def _terminal_append_text(self, text):
        self.terminal_buffer.feed(text)
        if self.terminal_output_edit is None:
            return
        self.terminal_output_edit.setPlainText(self.terminal_buffer.to_text())
        cursor = self.terminal_output_edit.textCursor()
        cursor.setPosition(self.terminal_buffer.cursor_offset())
        self.terminal_output_edit.setTextCursor(cursor)
        self.terminal_output_edit.verticalScrollBar().setValue(self.terminal_output_edit.verticalScrollBar().maximum())

    def _terminal_output(self, text):
        if "[host key]" in text:
            for line in str(text).splitlines():
                if "[host key]" in line:
                    self._append_log("SSH 终端: " + line)
        self._terminal_append_text(text)

    def _terminal_connected(self, display):
        self.terminal_password = self.terminal_worker.password if self.terminal_worker else self.terminal_password
        if self.terminal_password and not self.sftp_password:
            self.sftp_password = self.terminal_password
        if self.terminal_status_label:
            self.terminal_status_label.setText("已连接: " + display)
        self._update_status("ssh", "已连接", display)
        self._append_log("SSH 终端已连接: " + display)
        if self.terminal_output_edit:
            self.terminal_output_edit.setFocus()
        if self.terminal_export_display_check and self.terminal_export_display_check.isChecked():
            QTimer.singleShot(300, self._send_terminal_display_exports)
        if self.remote_files_table is not None:
            QTimer.singleShot(200, self.refresh_remote_files)
        self._refresh_task_center()

    def _send_terminal_display_exports(self):
        if not self.terminal_export_display_check or not self.terminal_export_display_check.isChecked():
            return
        if not self.terminal_worker or not self.terminal_worker.isRunning():
            return
        self.terminal_worker.send_text(
            "export DISPLAY=:0\n"
            "export XAUTHORITY=/home/jetson/.Xauthority\n"
        )
        self._append_log("SSH 终端已发送图形环境变量: DISPLAY=:0, XAUTHORITY=/home/jetson/.Xauthority")

    def _terminal_auth_failed(self, error):
        if self.terminal_worker and self.terminal_worker.password:
            self._terminal_failed(error)
            return
        password = self._prompt_ssh_password("SSH 认证")
        if password is None:
            self._terminal_failed("SSH 认证失败。")
            return
        self.terminal_password = password
        self.terminal_worker = None
        self.terminal_connect(password=password)

    def _terminal_failed(self, error):
        if self.terminal_status_label:
            self.terminal_status_label.setText("连接失败")
        self._terminal_append_text("\n[错误] {}\n".format(error))
        self._append_log("SSH 终端错误: " + str(error))
        self._refresh_task_center()

    def _terminal_disconnected(self):
        if self.terminal_status_label and self.terminal_status_label.text().startswith("已连接"):
            self.terminal_status_label.setText("已断开")
        self._refresh_task_center()
