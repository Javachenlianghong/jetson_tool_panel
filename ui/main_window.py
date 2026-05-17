#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main window for Jetson Tool Panel."""

import base64
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from core.command_runner import CommandWorker, format_command
from core.paths import DEFAULTS, PATHS
from core.settings import settings_bool
from services import display_service, proxy_service, ssh_service
from ui.pages.display_page import build_display_page
from ui.pages.help_page import build_help_page
from ui.pages.proxy_page import build_proxy_page
from ui.pages.transfer_page import build_transfer_page


def local_ipv4_candidates():
    """Return likely non-loopback IPv4 addresses for the current Windows host."""
    addresses = []

    try:
        host_names = [socket.gethostname(), socket.getfqdn()]
        for host_name in host_names:
            for address in socket.gethostbyname_ex(host_name)[2]:
                if address not in addresses and not address.startswith("127."):
                    addresses.append(address)
    except OSError:
        pass

    # This UDP trick does not send packets; it asks the OS which source address
    # it would use for an external route.
    for target in ("8.8.8.8", "1.1.1.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((target, 80))
            address = sock.getsockname()[0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
        except OSError:
            pass
        finally:
            sock.close()

    return sorted(addresses, key=address_rank)


def address_rank(ip_address):
    parts = ip_address.split(".")
    last_octet = parts[-1] if len(parts) == 4 else ""
    rank = 50

    if ip_address.startswith("192.168.1."):
        rank = 0
    elif ip_address.startswith("192.168."):
        rank = 5
    elif ip_address.startswith("10."):
        rank = 10
    elif ip_address.startswith("172."):
        rank = 15

    if ip_address.startswith("198.18.") or ip_address.startswith("198.19."):
        rank += 50
    if last_octet == "1":
        rank += 12

    return (rank, ip_address)


def default_remote_cidr(ip_address):
    parts = ip_address.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".0/24"
    return "192.168.1.0/24"


class JetsonControlPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(str(PATHS.config_path), QSettings.IniFormat)
        self.worker = None
        self.defaults = DEFAULTS
        self.paths = PATHS

        self.ip_combo = None
        self.port_spin = None
        self.remote_address_edit = None
        self.clash_program_edit = None
        self.remote_edit = None
        self.remote_path_edit = None
        self.local_root_edit = None
        self.full_sync_check = None
        self.dry_run_check = None
        self.no_delete_check = None
        self.display_output_combo = None
        self.resolution_combo = None
        self.refresh_rate_spin = None
        self.display_env_edit = None
        self.xauthority_edit = None
        self.framebuffer_fallback_check = None
        self.log_edit = None
        self.stop_button = None
        self.command_buttons = []
        self.nav_buttons = []
        self.page_stack = None
        self.current_command_title = None
        self.status_labels = {}
        self.status_dots = {}

        self.setWindowTitle("Jetson 工具面板")
        self.resize(1080, 760)
        self._build_ui()
        self._apply_style()
        self.refresh_ips()
        self._load_settings()
        self._append_log("就绪。")

    def _build_ui(self):
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        main = QWidget()
        main.setObjectName("MainSurface")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        title = QLabel("Jetson 工具面板")
        title.setObjectName("Title")
        subtitle = QLabel("Windows Clash 代理、Jetson SSH、项目同步与显示设置。")
        subtitle.setObjectName("Subtitle")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_layout.addLayout(header_text, 1)
        header_layout.addWidget(self._build_status_strip(), 2)
        main_layout.addLayout(header_layout)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("PageStack")
        self.page_stack.addWidget(build_proxy_page(self))
        self.page_stack.addWidget(build_transfer_page(self))
        self.page_stack.addWidget(build_display_page(self))
        self.page_stack.addWidget(build_help_page(self))
        main_layout.addWidget(self.page_stack, 1)

        log_header = QHBoxLayout()
        log_title = QLabel("日志")
        log_title.setObjectName("SectionTitle")
        clear_button = QPushButton("清空日志")
        clear_button.clicked.connect(self.clear_log)
        self.stop_button = QPushButton("停止当前命令")
        self.stop_button.clicked.connect(self.stop_current_command)
        self.stop_button.setEnabled(False)
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        log_header.addWidget(clear_button)
        log_header.addWidget(self.stop_button)
        main_layout.addLayout(log_header)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        log_font = QFont("Consolas")
        log_font.setStyleHint(QFont.Monospace)
        log_font.setPointSize(10)
        self.log_edit.setFont(log_font)
        self.log_edit.setMinimumHeight(120)
        self.log_edit.setMaximumHeight(180)
        main_layout.addWidget(self.log_edit)

        root_layout.addWidget(main, 1)
        self.setCentralWidget(central)

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(148)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(8)

        brand = QLabel("Jetson")
        brand.setObjectName("SidebarBrand")
        product = QLabel("Tool Panel")
        product.setObjectName("SidebarProduct")
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addSpacing(14)

        style = self.style()
        nav_specs = [
            ("代理", style.standardIcon(QStyle.SP_DriveNetIcon)),
            ("项目传输", style.standardIcon(QStyle.SP_DirIcon)),
            ("显示设置", style.standardIcon(QStyle.SP_ComputerIcon)),
            ("命令参考", style.standardIcon(QStyle.SP_FileDialogInfoView)),
        ]
        for index, (text, icon) in enumerate(nav_specs):
            button = self._build_nav_button(text, icon)
            button.clicked.connect(lambda checked=False, page=index: self._switch_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        settings_button = self._build_nav_button("设置", style.standardIcon(QStyle.SP_FileDialogDetailedView))
        settings_button.setCheckable(False)
        settings_button.clicked.connect(lambda: self._append_log("设置入口暂未启用；常用设置会自动保存到 settings.ini。"))
        about_button = self._build_nav_button("关于", style.standardIcon(QStyle.SP_MessageBoxInformation))
        about_button.setCheckable(False)
        about_button.clicked.connect(self._show_about)
        layout.addWidget(settings_button)
        layout.addWidget(about_button)
        return sidebar

    def _build_nav_button(self, text, icon=None):
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setMinimumHeight(38)
        button.setCursor(Qt.PointingHandCursor)
        if icon is not None:
            button.setIcon(icon)
        return button

    def _build_status_strip(self):
        strip = QWidget()
        strip.setObjectName("StatusStrip")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_status_card("ssh", "SSH 连接", "未测试", "未连接"))
        layout.addWidget(self._build_status_card("proxy", "代理状态", "未启用", "等待操作"))
        layout.addWidget(self._build_status_card("display", "显示状态", "未查询", "DISPLAY :0"))
        return strip

    def _build_status_card(self, kind, title, value, detail):
        card = QFrame()
        card.setObjectName("StatusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setObjectName("StatusDot")
        dot.setProperty("state", "pending")
        title_label = QLabel(title)
        title_label.setObjectName("StatusTitle")
        title_row.addWidget(dot)
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        value_label = QLabel(value)
        value_label.setObjectName("StatusValue")
        detail_label = QLabel(detail)
        detail_label.setObjectName("StatusDetail")
        detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addLayout(title_row)
        layout.addWidget(value_label)
        layout.addWidget(detail_label)
        self.status_dots[kind] = dot
        self.status_labels[kind] = {
            "value": value_label,
            "detail": detail_label,
        }
        return card

    def _switch_page(self, index):
        if not self.page_stack:
            return
        if index < 0 or index >= self.page_stack.count():
            index = 0
        self.page_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        self.settings.setValue("window/current_page", index)

    def _update_status(self, kind, state, detail):
        labels = self.status_labels.get(kind)
        dot = self.status_dots.get(kind)
        if not labels or not dot:
            return
        labels["value"].setText(state)
        labels["detail"].setText(detail)
        dot_state = "ok" if state in ("已连接", "已启用", "已查询", "已设置") else "pending"
        if "失败" in state or "错误" in state:
            dot_state = "error"
        dot.setProperty("state", dot_state)
        dot.style().unpolish(dot)
        dot.style().polish(dot)

    def _show_about(self):
        QMessageBox.information(
            self,
            "关于",
            "Jetson 工具面板\n\n用于管理 Windows 代理、Jetson SSH、项目同步与显示分辨率。",
        )

    def _bind_line_edits(self, primary, secondary):
        primary.textChanged.connect(
            lambda text: secondary.setText(text) if secondary.text() != text else None
        )
        secondary.textChanged.connect(
            lambda text: primary.setText(text) if primary.text() != text else None
        )

    def _bind_checkboxes(self, primary, secondary):
        primary.toggled.connect(
            lambda checked: secondary.setChecked(checked) if secondary.isChecked() != checked else None
        )
        secondary.toggled.connect(
            lambda checked: primary.setChecked(checked) if primary.isChecked() != checked else None
        )

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f4f6fa;
            }
            QWidget#MainSurface {
                background: #f4f6fa;
            }
            QFrame#Sidebar {
                background: #ffffff;
                border-right: 1px solid #dde3ec;
            }
            QLabel#SidebarBrand {
                color: #172033;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#SidebarProduct {
                color: #667085;
                font-size: 12px;
            }
            QLabel#Title {
                color: #172033;
                font-size: 23px;
                font-weight: 700;
            }
            QLabel#Subtitle {
                color: #667085;
                font-size: 13px;
            }
            QLabel#SectionTitle {
                color: #172033;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#PanelTitle {
                color: #172033;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#PanelLead {
                color: #172033;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#MutedText {
                color: #667085;
                font-size: 12px;
            }
            QFrame#Panel {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 8px;
            }
            QFrame#StatusCard {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 8px;
            }
            QLabel#StatusTitle {
                color: #667085;
                font-size: 11px;
            }
            QLabel#StatusValue {
                color: #172033;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#StatusDetail {
                color: #667085;
                font-size: 11px;
            }
            QLabel#StatusDot {
                color: #a6b0c0;
                font-size: 12px;
            }
            QLabel#StatusDot[state="ok"] {
                color: #16a34a;
            }
            QLabel#StatusDot[state="error"] {
                color: #dc2626;
            }
            QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
                background: #ffffff;
                border: 1px solid #d4dbe7;
                border-radius: 6px;
                color: #172033;
                padding: 7px;
                selection-background-color: #2563eb;
            }
            QPlainTextEdit {
                background: #fbfcfe;
            }
            QPlainTextEdit#ReferenceText {
                background: #fbfcfe;
                border-color: #dde3ec;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #ccd5e2;
                border-radius: 6px;
                color: #172033;
                min-height: 28px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #f3f7ff;
                border-color: #93b4f7;
            }
            QPushButton:pressed {
                background: #e8f0ff;
            }
            QPushButton:disabled {
                background: #edf1f6;
                color: #98a2b3;
                border-color: #d8dee8;
            }
            QPushButton#PrimaryButton {
                background: #2563eb;
                border-color: #2563eb;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
                border-color: #1d4ed8;
            }
            QPushButton#NavButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                color: #465568;
                padding: 8px 10px;
                text-align: left;
            }
            QPushButton#NavButton:hover {
                background: #f4f7fb;
                border-color: #e5ebf3;
            }
            QPushButton#NavButton:checked {
                background: #eff6ff;
                border-color: #bfdbfe;
                color: #2563eb;
                font-weight: 700;
            }
            QLabel#Note {
                background: #f8fbff;
                border: 1px solid #dbeafe;
                border-radius: 6px;
                color: #465568;
                padding: 10px;
            }
            """
        )

    def refresh_ips(self):
        addresses = local_ipv4_candidates()
        current = self.ip_combo.currentText().strip() if self.ip_combo else ""
        self.ip_combo.clear()
        if addresses:
            self.ip_combo.addItems(addresses)
        else:
            self.ip_combo.addItem("192.168.1.11")

        if current:
            index = self.ip_combo.findText(current)
            if index >= 0:
                self.ip_combo.setCurrentIndex(index)
            else:
                self.ip_combo.setEditText(current)

        self._sync_default_cidr(self.ip_combo.currentText())
        self._append_log("已刷新本机 IPv4: " + ", ".join(addresses or ["未自动识别"]))

    def choose_clash_program(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Clash Verge 程序",
            str(Path(self.defaults.clash_program).parent),
            "Executable (*.exe);;All files (*.*)",
        )
        if path:
            self.clash_program_edit.setText(path)

    def choose_local_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Windows 保存目录", self.local_root_edit.text())
        if path:
            self.local_root_edit.setText(path)

    def clear_log(self):
        self.log_edit.clear()

    def _set_combo_text(self, combo, text):
        if text is None:
            return
        text = str(text)
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setEditText(text)

    def _setting_int(self, key, default):
        value = self.settings.value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _load_settings(self):
        geometry = self.settings.value("window/geometry")
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except TypeError:
                pass

        self._set_combo_text(self.ip_combo, self.settings.value("proxy/windows_ip", self.ip_combo.currentText()))
        self.port_spin.setValue(self._setting_int("proxy/port", self.defaults.proxy_port))
        self.remote_address_edit.setText(str(self.settings.value("proxy/remote_address", self.remote_address_edit.text())))
        self.clash_program_edit.setText(str(self.settings.value("proxy/clash_program", self.clash_program_edit.text())))

        self.remote_edit.setText(str(self.settings.value("ssh/remote", self.defaults.remote)))
        self.remote_path_edit.setText(str(self.settings.value("ssh/remote_path", self.defaults.remote_path)))
        self.local_root_edit.setText(str(self.settings.value("transfer/local_root", str(self.paths.app_dir))))
        self.full_sync_check.setChecked(settings_bool(self.settings.value("sync/full"), False))
        self.dry_run_check.setChecked(settings_bool(self.settings.value("sync/dry_run"), False))
        self.no_delete_check.setChecked(settings_bool(self.settings.value("sync/no_delete"), False))

        self._set_combo_text(self.display_output_combo, self.settings.value("display/output", "auto"))
        self._set_combo_text(self.resolution_combo, self.settings.value("display/resolution", "1920x1080"))
        self.refresh_rate_spin.setValue(self._setting_int("display/refresh_rate", 60))
        self.display_env_edit.setText(str(self.settings.value("display/display_env", ":0")))
        self.xauthority_edit.setText(str(self.settings.value("display/xauthority", "$HOME/.Xauthority")))
        self.framebuffer_fallback_check.setChecked(
            settings_bool(self.settings.value("display/framebuffer_fallback"), True)
        )
        self._switch_page(self._setting_int("window/current_page", 0))

    def _save_settings(self):
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/current_page", self.page_stack.currentIndex() if self.page_stack else 0)

        self.settings.setValue("proxy/windows_ip", self.ip_combo.currentText().strip())
        self.settings.setValue("proxy/port", self.port_spin.value())
        self.settings.setValue("proxy/remote_address", self.remote_address_edit.text().strip())
        self.settings.setValue("proxy/clash_program", self.clash_program_edit.text().strip())

        self.settings.setValue("ssh/remote", self.remote_edit.text().strip())
        self.settings.setValue("ssh/remote_path", self.remote_path_edit.text().strip())
        self.settings.setValue("transfer/local_root", self.local_root_edit.text().strip())
        self.settings.setValue("sync/full", self.full_sync_check.isChecked())
        self.settings.setValue("sync/dry_run", self.dry_run_check.isChecked())
        self.settings.setValue("sync/no_delete", self.no_delete_check.isChecked())

        self.settings.setValue("display/output", self.display_output_combo.currentText().strip())
        self.settings.setValue("display/resolution", self.resolution_combo.currentText().strip())
        self.settings.setValue("display/refresh_rate", self.refresh_rate_spin.value())
        self.settings.setValue("display/display_env", self.display_env_edit.text().strip())
        self.settings.setValue("display/xauthority", self.xauthority_edit.text().strip())
        self.settings.setValue("display/framebuffer_fallback", self.framebuffer_fallback_check.isChecked())
        self.settings.sync()

    def _sync_default_cidr(self, ip_address):
        if not self.remote_address_edit:
            return
        value = self.remote_address_edit.text().strip()
        if not value or value.endswith(".0/24"):
            self.remote_address_edit.setText(default_remote_cidr(ip_address.strip()))

    def _append_log(self, message):
        if not self.log_edit:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_edit.appendPlainText("[{}] {}".format(timestamp, message))
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    def _set_running(self, running):
        for button in self.command_buttons:
            button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _run_command(self, title, command, cwd=None):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "命令正在运行", "请等待当前命令结束，或先点击“停止当前命令”。")
            return

        self._save_settings()
        self._append_log("")
        self._append_log("开始: " + title)
        self._append_log("+ " + format_command(command))
        self._set_running(True)
        self.current_command_title = title

        self.worker = CommandWorker(command, cwd=cwd, parent=self)
        self.worker.output.connect(self._append_log)
        self.worker.failed_to_start.connect(self._command_failed_to_start)
        self.worker.finished_ok.connect(self._command_finished)
        self.worker.start()

    def _command_failed_to_start(self, error):
        self._append_log("无法启动命令: " + error)
        self._set_running(False)

    def _command_finished(self, return_code):
        title = self.current_command_title or ""
        if return_code == 0:
            self._append_log("命令完成。")
            self._handle_command_success(title)
        else:
            self._append_log("命令失败，退出码: {}".format(return_code))
        self._set_running(False)
        self.current_command_title = None

    def _handle_command_success(self, title):
        if title == "测试 SSH":
            self._update_status("ssh", "已连接", self.remote_edit.text().strip())
        elif title in ("启用临时防火墙规则", "以管理员窗口启用防火墙规则"):
            detail = "{}:{}".format(self.ip_combo.currentText().strip(), self.port_spin.value())
            self._update_status("proxy", "已启用", detail)
        elif title == "移除临时防火墙规则":
            self._update_status("proxy", "未启用", "规则已移除")
        elif title == "查询 Jetson 显示器":
            self._update_status("display", "已查询", "DISPLAY {}".format(self.display_env_edit.text().strip() or ":0"))
        elif title == "设置 Jetson 分辨率":
            self._update_status("display", "已设置", self.resolution_combo.currentText().strip())
        elif title == "恢复 Jetson 显示自动模式":
            self._update_status("display", "已设置", "自动模式")

    def stop_current_command(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate_process()
            self._append_log("已请求停止当前命令。")

    def enable_firewall_rule(self):
        if not self.paths.windows_proxy_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.windows_proxy_script))
            return
        self._run_command(
            "启用临时防火墙规则",
            proxy_service.firewall_args(
                self.paths.windows_proxy_script,
                self.port_spin.value(),
                self.remote_address_edit.text().strip(),
                self.clash_program_edit.text().strip(),
            ),
        )

    def enable_firewall_rule_elevated(self):
        if not self.paths.windows_proxy_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.windows_proxy_script))
            return
        command = proxy_service.elevated_firewall_args(
            self.paths.windows_proxy_script,
            self.port_spin.value(),
            self.remote_address_edit.text().strip(),
            self.clash_program_edit.text().strip(),
        )
        self._run_command("以管理员窗口启用防火墙规则", command)

    def remove_firewall_rule(self):
        if not self.paths.windows_proxy_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.windows_proxy_script))
            return
        self._run_command(
            "移除临时防火墙规则",
            proxy_service.firewall_args(
                self.paths.windows_proxy_script,
                self.port_spin.value(),
                self.remote_address_edit.text().strip(),
                self.clash_program_edit.text().strip(),
                include_stop=True,
            ),
        )

    def proxy_command_text(self):
        return proxy_service.proxy_command_text(
            self.ip_combo.currentText().strip(),
            self.port_spin.value(),
        )

    def copy_proxy_command(self):
        command = self.proxy_command_text()
        QApplication.clipboard().setText(command)
        self._append_log("已复制 Jetson 命令: " + command)

    def test_ssh(self):
        remote = self.remote_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请填写 Jetson SSH，例如 jetson@192.168.55.1。")
            return
        self._run_command("测试 SSH", ssh_service.test_ssh_command(remote), cwd=self.paths.app_dir)

    def _remote_or_warn(self):
        remote = self.remote_edit.text().strip() if self.remote_edit else ""
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请先在“项目传输”页填写 Jetson SSH。")
            return None
        return remote

    def _run_jetson_command(self, title, remote_command):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._run_command(
            title,
            ssh_service.remote_ssh_command(remote, remote_command),
            cwd=self.paths.app_dir,
        )

    def query_jetson_displays(self):
        command = display_service.query_display_command(
            self.display_env_edit.text().strip(),
            self.xauthority_edit.text().strip(),
        )
        self._run_jetson_command("查询 Jetson 显示器", command)

    def set_jetson_resolution(self):
        output = self.display_output_combo.currentText().strip() if self.display_output_combo else "auto"
        mode = self.resolution_combo.currentText().strip() if self.resolution_combo else "1920x1080"
        rate = self.refresh_rate_spin.value() if self.refresh_rate_spin else 0
        framebuffer_fallback = (
            self.framebuffer_fallback_check.isChecked()
            if self.framebuffer_fallback_check
            else True
        )

        if not mode or "x" not in mode.lower():
            QMessageBox.warning(self, "分辨率格式不正确", "请填写类似 1920x1080 的分辨率。")
            return

        remote_script = display_service.set_resolution_command(
            self.display_env_edit.text().strip(),
            self.xauthority_edit.text().strip(),
            output,
            mode,
            rate,
            framebuffer_fallback,
        )
        self._run_jetson_command("设置 Jetson 分辨率", remote_script)

    def auto_jetson_display(self):
        output = self.display_output_combo.currentText().strip() if self.display_output_combo else "auto"
        framebuffer_fallback = (
            self.framebuffer_fallback_check.isChecked()
            if self.framebuffer_fallback_check
            else True
        )
        remote_script = display_service.auto_display_command(
            self.display_env_edit.text().strip(),
            self.xauthority_edit.text().strip(),
            output,
            framebuffer_fallback,
        )
        self._run_jetson_command("恢复 Jetson 显示自动模式", remote_script)

    def configure_ssh_key(self):
        remote = self.remote_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请填写 Jetson SSH，例如 jetson@192.168.55.1。")
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
        remote = self.remote_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请填写 Jetson SSH，例如 jetson@192.168.55.1。")
            return
        if not self.paths.jetson_proxy_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.jetson_proxy_script))
            return

        self._run_command(
            "上传代理脚本到 Jetson",
            ssh_service.upload_proxy_script_command(self.paths.jetson_proxy_script, remote),
            cwd=self.paths.app_dir,
        )

    def pull_from_jetson(self):
        remote = self.remote_edit.text().strip()
        remote_path = self.remote_path_edit.text().strip()
        local_root = Path(self.local_root_edit.text().strip())
        if not remote or not remote_path:
            QMessageBox.warning(self, "缺少参数", "请填写 Jetson SSH 和 Jetson 项目路径。")
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
        command = ssh_service.sync_command(
            self.paths.sync_script,
            self.remote_edit.text().strip(),
            self.remote_path_edit.text().strip(),
            init=True,
        )
        self._run_command("初始化同步状态", command, cwd=self.paths.project_dir)

    def sync_to_jetson(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return

        command = ssh_service.sync_command(
            self.paths.sync_script,
            self.remote_edit.text().strip(),
            self.remote_path_edit.text().strip(),
            full=self.full_sync_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            no_delete=self.no_delete_check.isChecked(),
        )
        self._run_command("同步到 Jetson", command, cwd=self.paths.project_dir)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(
                self,
                "命令仍在运行",
                "当前命令仍在运行，是否停止并退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.terminate_process()
            self.worker.wait(3000)
        self._save_settings()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = JetsonControlPanel()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
