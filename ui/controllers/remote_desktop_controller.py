"""Remote desktop controller backed by x11vnc and an embedded VNC widget."""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from core.vnc_client import VncClientWorker
from services import remote_desktop_service


class RemoteDesktopControllerMixin:
    def install_remote_desktop_service(self):
        self._run_jetson_command("安装远程桌面组件", remote_desktop_service.x11vnc_install_command())

    def start_remote_desktop_service(self):
        display = self.remote_desktop_display_edit.text().strip() if self.remote_desktop_display_edit else ":0"
        xauthority = (
            self.remote_desktop_xauthority_edit.text().strip()
            if self.remote_desktop_xauthority_edit
            else "$HOME/.Xauthority"
        )
        port = self.remote_desktop_port_spin.value() if self.remote_desktop_port_spin else 5900
        self._set_remote_desktop_status("正在启动 Jetson x11vnc...")
        self._run_jetson_command(
            "启动远程桌面服务",
            remote_desktop_service.x11vnc_start_command(display, xauthority, port),
        )

    def stop_remote_desktop_service(self):
        port = self.remote_desktop_port_spin.value() if self.remote_desktop_port_spin else 5900
        self.disconnect_remote_desktop()
        self._run_jetson_command("停止远程桌面服务", remote_desktop_service.x11vnc_stop_command(port))

    def query_remote_desktop_service(self):
        port = self.remote_desktop_port_spin.value() if self.remote_desktop_port_spin else 5900
        self._run_jetson_command("查询远程桌面服务", remote_desktop_service.x11vnc_status_command(port))

    def start_and_connect_remote_desktop(self):
        self.start_remote_desktop_service()

    def connect_remote_desktop(self, password=None):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.remote_desktop_worker and self.remote_desktop_worker.isRunning():
            QMessageBox.information(self, "远程桌面已连接", "当前远程桌面会话仍在运行。")
            return
        port = self.remote_desktop_port_spin.value() if self.remote_desktop_port_spin else 5900
        self.remote_desktop_worker = VncClientWorker(
            remote,
            remote_port=port,
            password=password if password is not None else (self.sftp_password or self.terminal_password),
            parent=self,
        )
        self.remote_desktop_worker.connected.connect(self._remote_desktop_connected)
        self.remote_desktop_worker.framebuffer.connect(self._remote_desktop_framebuffer)
        self.remote_desktop_worker.status.connect(self._set_remote_desktop_status)
        self.remote_desktop_worker.auth_failed.connect(self._remote_desktop_auth_failed)
        self.remote_desktop_worker.failed.connect(self._remote_desktop_failed)
        self.remote_desktop_worker.disconnected.connect(self._remote_desktop_disconnected)
        if self.remote_desktop_view:
            self.remote_desktop_view.pointer_event.connect(self.remote_desktop_worker.send_pointer)
            self.remote_desktop_view.key_event.connect(self.remote_desktop_worker.send_key)
        self._set_remote_desktop_status("正在连接远程桌面...")
        self.remote_desktop_worker.start()
        self._refresh_task_center()

    def disconnect_remote_desktop(self):
        worker = self.remote_desktop_worker
        self.remote_desktop_worker = None
        if worker and self.remote_desktop_view:
            try:
                self.remote_desktop_view.pointer_event.disconnect(worker.send_pointer)
                self.remote_desktop_view.key_event.disconnect(worker.send_key)
            except TypeError:
                pass
        if worker and worker.isRunning():
            worker.stop()
            worker.wait(2000)
        if self.remote_desktop_view:
            self.remote_desktop_view.clear()
        self._set_remote_desktop_status("已断开远程桌面")
        self._refresh_task_center()

    def _remote_desktop_connected(self, width, height, name):
        if self.remote_desktop_worker:
            self.terminal_password = self.remote_desktop_worker.password or self.terminal_password
            if self.terminal_password and not self.sftp_password:
                self.sftp_password = self.terminal_password
        self._set_remote_desktop_status("已连接: {} ({}x{})".format(name, width, height))
        if self.remote_desktop_view:
            self.remote_desktop_view.setFocus()
        self._refresh_task_center()

    def _remote_desktop_framebuffer(self, image):
        if self.remote_desktop_view:
            self.remote_desktop_view.set_framebuffer(image)

    def _remote_desktop_auth_failed(self, error):
        worker = self.remote_desktop_worker
        if worker and worker.password:
            self._remote_desktop_failed(error)
            return
        password = self._prompt_ssh_password("远程桌面 SSH 认证")
        if password is None:
            self._remote_desktop_failed("SSH 认证失败。")
            return
        self.terminal_password = password
        self.remote_desktop_worker = None
        self.connect_remote_desktop(password=password)

    def _remote_desktop_failed(self, error):
        self._set_remote_desktop_status("连接失败: " + str(error))
        self._append_log("远程桌面错误: " + str(error))
        self._refresh_task_center()

    def _remote_desktop_disconnected(self):
        sender = self.sender()
        if sender and self.remote_desktop_view:
            try:
                self.remote_desktop_view.pointer_event.disconnect(sender.send_pointer)
                self.remote_desktop_view.key_event.disconnect(sender.send_key)
            except TypeError:
                pass
        if sender is self.remote_desktop_worker:
            self.remote_desktop_worker = None
        self._refresh_task_center()

    def _set_remote_desktop_status(self, status):
        self.remote_desktop_last_status = str(status or "未知")
        if self.remote_desktop_status_label:
            self.remote_desktop_status_label.setText(self.remote_desktop_last_status)

    def handle_remote_desktop_command_success(self, title):
        if title == "启动远程桌面服务":
            self._set_remote_desktop_status("x11vnc 已启动，正在连接...")
            QTimer.singleShot(600, self.connect_remote_desktop)
            return True
        if title == "停止远程桌面服务":
            self._set_remote_desktop_status("x11vnc 已停止")
            return True
        if title == "查询远程桌面服务":
            self._set_remote_desktop_status("远程桌面状态已写入底部日志")
            return True
        if title == "安装远程桌面组件":
            self._set_remote_desktop_status("x11vnc 安装命令已完成")
            return True
        return False

    def handle_remote_desktop_command_failure(self, title, return_code):
        if title not in ("启动远程桌面服务", "安装远程桌面组件", "查询远程桌面服务"):
            return False
        output = "\n".join(self.current_command_output).lower()
        if "x11vnc not found" in output or "x11vnc is missing" in output:
            self._set_remote_desktop_status(
                "Jetson 缺少 x11vnc：点击“安装 x11vnc”，或在 SSH 工作台执行 sudo apt-get install -y x11vnc"
            )
        elif "sudo password is required" in output:
            self._set_remote_desktop_status("安装需要 sudo 密码：请在 SSH 工作台执行日志里的 apt-get 命令")
        elif return_code == 127:
            self._set_remote_desktop_status("远程桌面组件缺失，请先安装 x11vnc")
        else:
            self._set_remote_desktop_status("远程桌面命令失败，退出码: {}".format(return_code))
        return True
