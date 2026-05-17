#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 control panel for the local Jetson helper scripts.

This GUI is intended to run on Windows. It wraps the existing PowerShell,
SCP, SSH, and sync commands without changing the original scripts.
"""

import os
import base64
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSettings, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)


IS_FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
TOOL_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent


def first_existing_path(*paths):
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def find_workspace_root():
    if not IS_FROZEN:
        return TOOL_DIR.parent

    candidates = [
        Path.cwd(),
        TOOL_DIR,
        TOOL_DIR.parent,
        TOOL_DIR.parent.parent,
    ]
    for candidate in candidates:
        if (candidate / "YoloV8-TensorRT-Jetson_Nano").exists():
            return candidate
    return TOOL_DIR


APP_DIR = find_workspace_root()
SCRIPT_DIR = first_existing_path(
    TOOL_DIR / "scripts",
    BUNDLE_DIR / "scripts",
    APP_DIR / "jetson_tool_panel" / "scripts",
)
CONFIG_PATH = TOOL_DIR / "settings.ini"


WINDOWS_PROXY_SCRIPT = first_existing_path(
    SCRIPT_DIR / "windows-clash-lan-temp.ps1",
    BUNDLE_DIR / "scripts" / "windows-clash-lan-temp.ps1",
    APP_DIR / "windows-clash-lan-temp.ps1",
)
JETSON_PROXY_SCRIPT = first_existing_path(
    SCRIPT_DIR / "jetson-proxy-session.sh",
    BUNDLE_DIR / "scripts" / "jetson-proxy-session.sh",
    APP_DIR / "jetson-proxy-session.sh",
)
PROJECT_DIR = first_existing_path(
    APP_DIR / "YoloV8-TensorRT-Jetson_Nano",
    TOOL_DIR / "YoloV8-TensorRT-Jetson_Nano",
)
SYNC_SCRIPT = PROJECT_DIR / "sync-to-jetson.py"

DEFAULT_PROXY_PORT = 7897
DEFAULT_REMOTE = "jetson@192.168.55.1"
DEFAULT_REMOTE_PATH = "/home/jetson/YoloV8-TensorRT-Jetson_Nano"
DEFAULT_CLASH_PROGRAM = r"C:\Program Files\Clash Verge\verge-mihomo.exe"


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


def quote_for_powershell(value):
    return "'" + value.replace("'", "''") + "'"


def quote_for_bash(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def format_command(command):
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return " ".join(quote_for_bash(part) for part in command)


def settings_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class CommandWorker(QThread):
    output = pyqtSignal(str)
    finished_ok = pyqtSignal(int)
    failed_to_start = pyqtSignal(str)

    def __init__(self, command, cwd=None, parent=None):
        super().__init__(parent)
        self.command = command
        self.cwd = str(cwd) if cwd else None
        self._process = None

    def run(self):
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.failed_to_start.emit(str(exc))
            return

        assert self._process.stdout is not None
        for line in self._process.stdout:
            self.output.emit(line.rstrip("\r\n"))

        return_code = self._process.wait()
        self.finished_ok.emit(return_code)

    def terminate_process(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()


class JetsonControlPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(str(CONFIG_PATH), QSettings.IniFormat)
        self.worker = None
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
        self.page_stack.addWidget(self._build_proxy_tab())
        self.page_stack.addWidget(self._build_transfer_tab())
        self.page_stack.addWidget(self._build_resolution_tab())
        self.page_stack.addWidget(self._build_help_tab())
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

    def _build_proxy_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        proxy_grid = QGridLayout()
        proxy_grid.setHorizontalSpacing(10)
        proxy_grid.setVerticalSpacing(10)

        self.ip_combo = QComboBox()
        self.ip_combo.setEditable(True)
        self.ip_combo.currentTextChanged.connect(self._sync_default_cidr)

        refresh_ip_button = QPushButton("刷新 IP")
        refresh_ip_button.clicked.connect(self.refresh_ips)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(DEFAULT_PROXY_PORT)

        self.remote_address_edit = QLineEdit("192.168.1.0/24")
        self.clash_program_edit = QLineEdit(DEFAULT_CLASH_PROGRAM)

        browse_button = QPushButton("浏览")
        browse_button.clicked.connect(self.choose_clash_program)

        proxy_grid.addWidget(QLabel("Windows IP"), 0, 0)
        proxy_grid.addWidget(self.ip_combo, 0, 1)
        proxy_grid.addWidget(QLabel("端口"), 0, 2)
        proxy_grid.addWidget(self.port_spin, 0, 3)
        proxy_grid.addWidget(refresh_ip_button, 0, 4)
        proxy_grid.addWidget(QLabel("允许访问网段"), 1, 0)
        proxy_grid.addWidget(self.remote_address_edit, 1, 1, 1, 4)
        proxy_grid.addWidget(QLabel("Clash Verge 程序"), 2, 0)
        proxy_grid.addWidget(self.clash_program_edit, 2, 1, 1, 3)
        proxy_grid.addWidget(browse_button, 2, 4)
        proxy_grid.setColumnStretch(1, 1)
        proxy_grid.setColumnStretch(3, 1)

        proxy_buttons = QHBoxLayout()
        enable_button = QPushButton("管理员窗口启用")
        enable_button.setObjectName("PrimaryButton")
        enable_button.clicked.connect(self.enable_firewall_rule_elevated)
        direct_enable_button = QPushButton("直接启用")
        direct_enable_button.clicked.connect(self.enable_firewall_rule)
        stop_rule_button = QPushButton("关闭防火墙规则")
        stop_rule_button.clicked.connect(self.remove_firewall_rule)
        copy_button = QPushButton("复制 Jetson 代理命令")
        copy_button.clicked.connect(self.copy_proxy_command)

        for button in (enable_button, direct_enable_button, stop_rule_button, copy_button):
            self.command_buttons.append(button)
            proxy_buttons.addWidget(button)
        proxy_buttons.addStretch(1)
        proxy_grid.addLayout(proxy_buttons, 3, 0, 1, 5)

        layout.addWidget(self._build_panel("代理配置（Windows Clash）", proxy_grid))

        ssh_grid = QGridLayout()
        ssh_grid.setHorizontalSpacing(10)
        ssh_grid.setVerticalSpacing(10)

        self.remote_edit = QLineEdit(DEFAULT_REMOTE)
        ssh_browse_button = QPushButton("...")
        ssh_browse_button.setEnabled(False)
        ssh_browse_button.setToolTip("SSH 地址直接在输入框中编辑")

        ssh_grid.addWidget(QLabel("SSH 地址"), 0, 0)
        ssh_grid.addWidget(self.remote_edit, 0, 1)
        ssh_grid.addWidget(ssh_browse_button, 0, 2)
        ssh_grid.setColumnStretch(1, 1)

        ssh_buttons = QHBoxLayout()
        ssh_button = QPushButton("测试 SSH")
        ssh_button.setObjectName("PrimaryButton")
        ssh_button.clicked.connect(self.test_ssh)
        setup_key_button = QPushButton("配置 SSH Key")
        setup_key_button.clicked.connect(self.configure_ssh_key)
        upload_proxy_button = QPushButton("上传代理脚本")
        upload_proxy_button.clicked.connect(self.upload_proxy_script)
        for button in (ssh_button, setup_key_button, upload_proxy_button):
            self.command_buttons.append(button)
            ssh_buttons.addWidget(button)
        ssh_buttons.addStretch(1)
        ssh_grid.addLayout(ssh_buttons, 1, 0, 1, 3)

        layout.addWidget(self._build_panel("Jetson SSH", ssh_grid))

        sync_grid = QGridLayout()
        sync_grid.setHorizontalSpacing(10)
        sync_grid.setVerticalSpacing(10)

        self.remote_path_edit = QLineEdit(DEFAULT_REMOTE_PATH)
        self.local_root_edit = QLineEdit(str(APP_DIR))

        choose_local_button = QPushButton("浏览")
        choose_local_button.clicked.connect(self.choose_local_root)

        sync_grid.addWidget(QLabel("本地项目根目录"), 0, 0)
        sync_grid.addWidget(self.local_root_edit, 0, 1)
        sync_grid.addWidget(choose_local_button, 0, 2)
        sync_grid.addWidget(QLabel("Jetson 项目路径"), 1, 0)
        sync_grid.addWidget(self.remote_path_edit, 1, 1, 1, 2)

        option_layout = QHBoxLayout()
        self.full_sync_check = QCheckBox("完整同步")
        self.dry_run_check = QCheckBox("只预览")
        self.no_delete_check = QCheckBox("不删除远端文件")
        option_layout.addWidget(self.full_sync_check)
        option_layout.addWidget(self.dry_run_check)
        option_layout.addWidget(self.no_delete_check)
        option_layout.addStretch(1)
        sync_grid.addLayout(option_layout, 2, 0, 1, 3)

        sync_buttons = QHBoxLayout()
        sync_button = QPushButton("同步到 Jetson")
        sync_button.setObjectName("PrimaryButton")
        sync_button.clicked.connect(self.sync_to_jetson)
        pull_button = QPushButton("从 Jetson 拉取项目")
        pull_button.clicked.connect(self.pull_from_jetson)
        init_button = QPushButton("初始化同步状态")
        init_button.clicked.connect(self.init_sync_state)
        for button in (sync_button, pull_button, init_button):
            self.command_buttons.append(button)
            sync_buttons.addWidget(button)
        sync_buttons.addStretch(1)
        sync_grid.addLayout(sync_buttons, 3, 0, 1, 3)
        sync_grid.setColumnStretch(1, 1)

        layout.addWidget(self._build_panel("项目同步", sync_grid))
        layout.addWidget(self._build_note("常用配置会自动保存；防火墙脚本需要管理员权限，建议优先使用“管理员窗口启用”。"))
        layout.addStretch(1)
        return page

    def _build_transfer_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(10)
        settings_grid.setVerticalSpacing(10)

        transfer_remote_edit = QLineEdit(self.remote_edit.text())
        transfer_remote_path_edit = QLineEdit(self.remote_path_edit.text())
        transfer_local_root_edit = QLineEdit(self.local_root_edit.text())
        self._bind_line_edits(self.remote_edit, transfer_remote_edit)
        self._bind_line_edits(self.remote_path_edit, transfer_remote_path_edit)
        self._bind_line_edits(self.local_root_edit, transfer_local_root_edit)

        choose_local_button = QPushButton("浏览")
        choose_local_button.clicked.connect(self.choose_local_root)

        settings_grid.addWidget(QLabel("Jetson SSH"), 0, 0)
        settings_grid.addWidget(transfer_remote_edit, 0, 1, 1, 2)
        settings_grid.addWidget(QLabel("Jetson 项目路径"), 1, 0)
        settings_grid.addWidget(transfer_remote_path_edit, 1, 1, 1, 2)
        settings_grid.addWidget(QLabel("Windows 保存目录"), 2, 0)
        settings_grid.addWidget(transfer_local_root_edit, 2, 1)
        settings_grid.addWidget(choose_local_button, 2, 2)
        settings_grid.setColumnStretch(1, 1)
        layout.addWidget(self._build_panel("Jetson SSH 与项目路径", settings_grid))

        option_layout = QHBoxLayout()
        transfer_full_sync_check = QCheckBox("完整同步")
        transfer_dry_run_check = QCheckBox("只预览")
        transfer_no_delete_check = QCheckBox("不删除远端文件")
        transfer_full_sync_check.setChecked(self.full_sync_check.isChecked())
        transfer_dry_run_check.setChecked(self.dry_run_check.isChecked())
        transfer_no_delete_check.setChecked(self.no_delete_check.isChecked())
        self._bind_checkboxes(self.full_sync_check, transfer_full_sync_check)
        self._bind_checkboxes(self.dry_run_check, transfer_dry_run_check)
        self._bind_checkboxes(self.no_delete_check, transfer_no_delete_check)
        option_layout.addWidget(transfer_full_sync_check)
        option_layout.addWidget(transfer_dry_run_check)
        option_layout.addWidget(transfer_no_delete_check)
        option_layout.addStretch(1)
        layout.addWidget(self._build_panel("同步选项", option_layout))

        buttons_grid = QGridLayout()
        buttons_grid.setHorizontalSpacing(10)
        buttons_grid.setVerticalSpacing(10)

        ssh_button = QPushButton("测试 SSH")
        ssh_button.setObjectName("PrimaryButton")
        ssh_button.clicked.connect(self.test_ssh)
        setup_key_button = QPushButton("配置 SSH Key")
        setup_key_button.clicked.connect(self.configure_ssh_key)
        upload_proxy_button = QPushButton("上传代理脚本")
        upload_proxy_button.clicked.connect(self.upload_proxy_script)
        sync_button = QPushButton("同步到 Jetson")
        sync_button.setObjectName("PrimaryButton")
        sync_button.clicked.connect(self.sync_to_jetson)
        pull_button = QPushButton("从 Jetson 拉取项目")
        pull_button.clicked.connect(self.pull_from_jetson)
        init_button = QPushButton("初始化同步状态")
        init_button.clicked.connect(self.init_sync_state)

        transfer_buttons = [
            ssh_button,
            setup_key_button,
            upload_proxy_button,
            sync_button,
            pull_button,
            init_button,
        ]
        for index, button in enumerate(transfer_buttons):
            self.command_buttons.append(button)
            buttons_grid.addWidget(button, index // 3, index % 3)
        buttons_grid.setColumnStretch(0, 1)
        buttons_grid.setColumnStretch(1, 1)
        buttons_grid.setColumnStretch(2, 1)
        layout.addWidget(self._build_panel("快速操作", buttons_grid))
        layout.addWidget(self._build_note("此页配置会与“代理”工作台中的 Jetson SSH 和项目同步面板保持同步。"))
        layout.addStretch(1)
        return page

    def _build_resolution_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.display_output_combo = QComboBox()
        self.display_output_combo.setEditable(True)
        self.display_output_combo.addItems(["auto", "HDMI-0", "HDMI-1", "DP-0", "DP-1", "eDP-1"])

        self.resolution_combo = QComboBox()
        self.resolution_combo.setEditable(True)
        self.resolution_combo.addItems([
            "1920x1080",
            "1280x720",
            "1366x768",
            "1600x900",
            "1024x768",
            "800x600",
            "2560x1440",
            "3840x2160",
        ])

        self.refresh_rate_spin = QSpinBox()
        self.refresh_rate_spin.setRange(0, 240)
        self.refresh_rate_spin.setValue(60)
        self.refresh_rate_spin.setSuffix(" Hz")
        self.refresh_rate_spin.setSpecialValueText("自动")

        self.display_env_edit = QLineEdit(":0")
        self.xauthority_edit = QLineEdit("$HOME/.Xauthority")
        self.framebuffer_fallback_check = QCheckBox("无 connected 显示器时设置 VNC/虚拟画布")
        self.framebuffer_fallback_check.setChecked(True)

        grid.addWidget(QLabel("使用 SSH"), 0, 0)
        grid.addWidget(QLabel("项目传输页里的 Jetson SSH 地址"), 0, 1, 1, 2)
        grid.addWidget(QLabel("显示输出口"), 1, 0)
        grid.addWidget(self.display_output_combo, 1, 1, 1, 2)
        grid.addWidget(QLabel("分辨率"), 2, 0)
        grid.addWidget(self.resolution_combo, 2, 1, 1, 2)
        grid.addWidget(QLabel("刷新率"), 3, 0)
        grid.addWidget(self.refresh_rate_spin, 3, 1, 1, 2)
        grid.addWidget(QLabel("DISPLAY"), 4, 0)
        grid.addWidget(self.display_env_edit, 4, 1, 1, 2)
        grid.addWidget(QLabel("XAUTHORITY"), 5, 0)
        grid.addWidget(self.xauthority_edit, 5, 1, 1, 2)
        grid.addWidget(QLabel("无头/VNC"), 6, 0)
        grid.addWidget(self.framebuffer_fallback_check, 6, 1, 1, 2)
        grid.setColumnStretch(1, 1)

        buttons = QHBoxLayout()
        query_button = QPushButton("查询显示器")
        query_button.clicked.connect(self.query_jetson_displays)
        set_button = QPushButton("设置分辨率")
        set_button.clicked.connect(self.set_jetson_resolution)
        auto_button = QPushButton("恢复自动")
        auto_button.clicked.connect(self.auto_jetson_display)

        for button in (query_button, set_button, auto_button):
            self.command_buttons.append(button)
            buttons.addWidget(button)
        buttons.addStretch(1)

        grid.addLayout(buttons, 7, 0, 1, 3)
        layout.addWidget(self._build_panel("Jetson 显示分辨率", grid))
        layout.addWidget(self._build_note(
            "说明：此功能通过 SSH 在 Jetson 的当前图形会话里执行 xrandr。"
            "设置通常只对当前桌面会话生效；如果 Jetson 没有启动桌面、使用 Wayland，"
            "或没有安装 xrandr，命令会失败并在日志中显示原因。"
        ))
        layout.addStretch(1)
        return page

    def _build_help_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        text = QPlainTextEdit()
        text.setObjectName("ReferenceText")
        text.setReadOnly(True)
        text.setPlainText(
            "常用命令参考\n\n"
            "1. Windows 开放 Clash 代理端口\n"
            "   管理员 PowerShell:\n"
            "   .\\windows-clash-lan-temp.ps1\n\n"
            "2. Jetson 当前终端启用代理\n"
            "   source ./jetson-proxy-session.sh <Windows_IP> 7897\n\n"
            "3. Jetson 当前终端关闭代理\n"
            "   proxyoff\n\n"
            "4. 从 Windows 上传代理脚本到 Jetson\n"
            "   scp -O .\\jetson-proxy-session.sh jetson@192.168.55.1:~/jetson-proxy-session.sh\n\n"
            "5. 配置 SSH Key\n"
            "   先生成 Windows 本机公钥，再输入 Jetson 密码写入 ~/.ssh/authorized_keys\n\n"
            "6. 查询 Jetson 显示器\n"
            "   DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority xrandr --query\n\n"
            "7. 设置 Jetson 分辨率\n"
            "   DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority xrandr --output HDMI-0 --mode 1920x1080 --rate 60\n\n"
            "8. 从 Jetson 拉取项目到 Windows\n"
            "   scp -O -r jetson@192.168.55.1:/home/jetson/YoloV8-TensorRT-Jetson_Nano .\n\n"
            "9. 同步 Windows 项目改动到 Jetson\n"
            "   py -3 .\\YoloV8-TensorRT-Jetson_Nano\\sync-to-jetson.py\n"
        )
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ref_layout = QVBoxLayout()
        ref_layout.addWidget(text)
        layout.addWidget(self._build_panel("命令参考", ref_layout), 1)
        return page

    def _build_panel(self, title, content_layout):
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")
        layout.addWidget(title_label)
        layout.addLayout(content_layout)
        return panel

    def _build_note(self, content):
        note = QLabel(content)
        note.setWordWrap(True)
        note.setObjectName("Note")
        return note

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
            str(Path(DEFAULT_CLASH_PROGRAM).parent),
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
        self.port_spin.setValue(self._setting_int("proxy/port", DEFAULT_PROXY_PORT))
        self.remote_address_edit.setText(str(self.settings.value("proxy/remote_address", self.remote_address_edit.text())))
        self.clash_program_edit.setText(str(self.settings.value("proxy/clash_program", self.clash_program_edit.text())))

        self.remote_edit.setText(str(self.settings.value("ssh/remote", DEFAULT_REMOTE)))
        self.remote_path_edit.setText(str(self.settings.value("ssh/remote_path", DEFAULT_REMOTE_PATH)))
        self.local_root_edit.setText(str(self.settings.value("transfer/local_root", str(APP_DIR))))
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

    def _proxy_args(self, include_stop=False):
        args = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WINDOWS_PROXY_SCRIPT),
            "-Port",
            str(self.port_spin.value()),
            "-RemoteAddress",
            self.remote_address_edit.text().strip(),
        ]
        program = self.clash_program_edit.text().strip()
        if program:
            args.extend(["-Program", program])
        if include_stop:
            args.append("-Stop")
        return args

    def enable_firewall_rule(self):
        if not WINDOWS_PROXY_SCRIPT.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(WINDOWS_PROXY_SCRIPT))
            return
        self._run_command("启用临时防火墙规则", self._proxy_args())

    def enable_firewall_rule_elevated(self):
        if not WINDOWS_PROXY_SCRIPT.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(WINDOWS_PROXY_SCRIPT))
            return

        script = str(WINDOWS_PROXY_SCRIPT)
        arguments = [
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            quote_for_powershell(script),
            "-Port",
            str(self.port_spin.value()),
            "-RemoteAddress",
            quote_for_powershell(self.remote_address_edit.text().strip()),
        ]
        program = self.clash_program_edit.text().strip()
        if program:
            arguments.extend(["-Program", quote_for_powershell(program)])

        start_process_args = " ".join(arguments)
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Start-Process powershell -Verb RunAs -ArgumentList {}".format(
                quote_for_powershell(start_process_args)
            ),
        ]
        self._run_command("以管理员窗口启用防火墙规则", command)

    def remove_firewall_rule(self):
        if not WINDOWS_PROXY_SCRIPT.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(WINDOWS_PROXY_SCRIPT))
            return
        self._run_command("移除临时防火墙规则", self._proxy_args(include_stop=True))

    def proxy_command_text(self):
        return "source ./jetson-proxy-session.sh {} {}".format(
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
        self._run_command(
            "测试 SSH",
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=8",
                "-o", "StrictHostKeyChecking=accept-new",
                remote,
                "echo Jetson SSH OK && uname -a",
            ],
            cwd=APP_DIR,
        )

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
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=8",
                "-o", "StrictHostKeyChecking=accept-new",
                remote,
                remote_command,
            ],
            cwd=APP_DIR,
        )

    def _display_env_prefix(self):
        display = self.display_env_edit.text().strip() if self.display_env_edit else ":0"
        xauthority = self.xauthority_edit.text().strip() if self.xauthority_edit else "$HOME/.Xauthority"
        if not display:
            display = ":0"

        prefix = "export DISPLAY={}; ".format(quote_for_bash(display))
        if xauthority:
            if xauthority == "$HOME/.Xauthority":
                prefix += 'export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"; '
            else:
                prefix += "export XAUTHORITY={}; ".format(quote_for_bash(xauthority))
        return prefix

    def query_jetson_displays(self):
        command = (
            self._display_env_prefix()
            + "echo DISPLAY=$DISPLAY; "
            + "echo XAUTHORITY=$XAUTHORITY; "
            + "if ! command -v xrandr >/dev/null 2>&1; then "
            + "echo 'xrandr not found. Install it with: sudo apt install x11-xserver-utils'; exit 127; "
            + "fi; "
            + "xrandr --query"
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

        remote_script = self._display_env_prefix() + r"""
set -e
if ! command -v xrandr >/dev/null 2>&1; then
    echo "xrandr not found. Install it with: sudo apt install x11-xserver-utils"
    exit 127
fi

output=__OUTPUT__
mode=__MODE__
rate=__RATE__
framebuffer_fallback=__FRAMEBUFFER_FALLBACK__

if [ -z "$output" ] || [ "$output" = "auto" ]; then
    output="$(xrandr --query | awk '$2 == "connected" { print $1; exit }')"
fi

if [ -z "$output" ]; then
    if [ "$framebuffer_fallback" = "1" ]; then
        echo "No connected display output found."
        echo "Applying framebuffer size only for headless/VNC session: $mode"
        xrandr --fb "$mode"
        echo "Framebuffer size applied."
        xrandr --query
        exit 0
    fi
    echo "No connected display output found."
    xrandr --query
    exit 1
fi

output_state="$(xrandr --query | awk -v out="$output" '$1 == out { print $2; exit }')"
if [ "$output_state" != "connected" ]; then
    if [ "$framebuffer_fallback" = "1" ]; then
        echo "Output $output is not connected; state is: ${output_state:-missing}"
        echo "Applying framebuffer size only for headless/VNC session: $mode"
        xrandr --fb "$mode"
        echo "Framebuffer size applied."
        xrandr --query
        exit 0
    fi
    echo "Output $output is not connected; state is: ${output_state:-missing}"
    xrandr --query
    exit 1
fi

echo "Output: $output"
echo "Requested mode: $mode"
echo "Requested refresh: $rate Hz"

if ! xrandr --query | awk -v out="$output" -v mode="$mode" '
    $1 == out && $2 == "connected" { inside = 1; next }
    inside && /^[^[:space:]]/ { inside = 0 }
    inside && $1 == mode { found = 1 }
    END { exit found ? 0 : 1 }
'; then
    echo "Mode $mode is not listed for $output. Trying to create a temporary mode..."
    width="${mode%x*}"
    height="${mode#*x}"
    height="${height%%_*}"

    if ! printf "%s %s\n" "$width" "$height" | grep -Eq '^[0-9]+ [0-9]+$'; then
        echo "Cannot create modeline from mode: $mode"
        exit 1
    fi

    generate_rate="$rate"
    if [ "$generate_rate" -le 0 ]; then
        generate_rate=60
    fi

    if command -v cvt >/dev/null 2>&1; then
        modeline="$(cvt "$width" "$height" "$generate_rate" | awk -F'Modeline ' '/Modeline/{print $2}')"
    elif command -v gtf >/dev/null 2>&1; then
        modeline="$(gtf "$width" "$height" "$generate_rate" | awk -F'Modeline ' '/Modeline/{print $2}')"
    else
        echo "Mode is unavailable and neither cvt nor gtf exists on Jetson."
        exit 1
    fi

    if [ -z "$modeline" ]; then
        echo "Failed to generate modeline."
        exit 1
    fi

    generated_mode="$(printf "%s\n" "$modeline" | awk '{print $1}' | tr -d '"')"
    modeline_args="$(printf "%s\n" "$modeline" | cut -d' ' -f2-)"
    echo "Generated mode: $generated_mode"
    xrandr --newmode "$generated_mode" $modeline_args 2>/dev/null || true
    xrandr --addmode "$output" "$generated_mode" 2>/dev/null || true
    mode="$generated_mode"
fi

if [ "$rate" -gt 0 ]; then
    if ! xrandr --output "$output" --mode "$mode" --rate "$rate"; then
        echo "Retrying without explicit refresh rate..."
        xrandr --output "$output" --mode "$mode"
    fi
else
    xrandr --output "$output" --mode "$mode"
fi

echo "Resolution applied."
xrandr --query
"""
        remote_script = (
            remote_script
            .replace("__OUTPUT__", quote_for_bash(output))
            .replace("__MODE__", quote_for_bash(mode))
            .replace("__RATE__", quote_for_bash(str(rate)))
            .replace("__FRAMEBUFFER_FALLBACK__", quote_for_bash("1" if framebuffer_fallback else "0"))
        )
        self._run_jetson_command("设置 Jetson 分辨率", remote_script)

    def auto_jetson_display(self):
        output = self.display_output_combo.currentText().strip() if self.display_output_combo else "auto"
        framebuffer_fallback = (
            self.framebuffer_fallback_check.isChecked()
            if self.framebuffer_fallback_check
            else True
        )
        remote_script = self._display_env_prefix() + r"""
set -e
if ! command -v xrandr >/dev/null 2>&1; then
    echo "xrandr not found. Install it with: sudo apt install x11-xserver-utils"
    exit 127
fi

output=__OUTPUT__
framebuffer_fallback=__FRAMEBUFFER_FALLBACK__
if [ -z "$output" ] || [ "$output" = "auto" ]; then
    output="$(xrandr --query | awk '$2 == "connected" { print $1; exit }')"
fi

if [ -z "$output" ]; then
    if [ "$framebuffer_fallback" = "1" ]; then
        echo "No connected display output found."
        echo "Restoring headless/VNC framebuffer to 640x480."
        xrandr --fb 640x480
        xrandr --query
        exit 0
    fi
    echo "No connected display output found."
    xrandr --query
    exit 1
fi

echo "Restoring automatic mode for: $output"
xrandr --output "$output" --auto
xrandr --query
"""
        remote_script = (
            remote_script
            .replace("__OUTPUT__", quote_for_bash(output))
            .replace("__FRAMEBUFFER_FALLBACK__", quote_for_bash("1" if framebuffer_fallback else "0"))
        )
        self._run_jetson_command("恢复 Jetson 显示自动模式", remote_script)

    def configure_ssh_key(self):
        remote = self.remote_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请填写 Jetson SSH，例如 jetson@192.168.55.1。")
            return

        self._save_settings()
        script = self._build_ssh_key_setup_script(remote)
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
            subprocess.Popen(command, cwd=str(APP_DIR), creationflags=creationflags)
        except Exception as exc:
            QMessageBox.critical(self, "无法打开配置窗口", str(exc))
            return

        self._append_log("已打开 SSH Key 配置窗口。按提示输入 Jetson 密码，完成后再点击“测试 SSH”。")

    def _build_ssh_key_setup_script(self, remote):
        remote_ps = quote_for_powershell(remote)
        return r"""
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Jetson SSH Key Setup'

try {
    $remote = __REMOTE__
    $sshDir = Join-Path $env:USERPROFILE '.ssh'
    $key = Join-Path $sshDir 'id_ed25519'
    $pub = "$key.pub"

    Write-Host ''
    Write-Host 'Jetson SSH Key Setup'
    Write-Host "Remote: $remote"
    Write-Host ''

    if (-not (Test-Path -LiteralPath $sshDir)) {
        New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
    }

    if (-not (Test-Path -LiteralPath $pub)) {
        if (Test-Path -LiteralPath $key) {
            Write-Host "Public key is missing. Rebuilding it from: $key"
            & ssh-keygen -y -f $key | Set-Content -LiteralPath $pub -Encoding ascii
        } else {
            Write-Host "Generating local SSH key: $key"
            & ssh-keygen -t ed25519 -N '' -f $key
        }
    } else {
        Write-Host "Using existing public key: $pub"
    }

    if (-not (Test-Path -LiteralPath $pub)) {
        throw "Public key was not created: $pub"
    }

    Write-Host ''
    Write-Host 'Next step needs the Jetson password.'
    Write-Host 'The password prompt may not show typed characters; that is normal.'
    Write-Host ''

    $remotePub = "/tmp/codex-ssh-key-$([guid]::NewGuid().ToString('N')).pub"
    $scpTarget = $remote + ':' + $remotePub

    Write-Host "Uploading public key to: $scpTarget"
    & scp -O -o StrictHostKeyChecking=accept-new $pub $scpTarget

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload public key to Jetson."
    }

    Write-Host ''
    Write-Host 'Installing public key into ~/.ssh/authorized_keys...'
    $installCommand = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; cat $remotePub >> ~/.ssh/authorized_keys; sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; rm -f $remotePub"
    & ssh -o StrictHostKeyChecking=accept-new $remote $installCommand

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install public key on Jetson."
    }

    Write-Host ''
    Write-Host 'Testing key login without password...'
    & ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new $remote "echo Jetson SSH key OK && uname -a"

    if ($LASTEXITCODE -ne 0) {
        throw "SSH key test failed."
    }

    Write-Host ''
    Write-Host 'Done. SSH key login is configured.'
} catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ''
Read-Host 'Press Enter to close this window'
""".replace("__REMOTE__", remote_ps)

    def upload_proxy_script(self):
        remote = self.remote_edit.text().strip()
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请填写 Jetson SSH，例如 jetson@192.168.55.1。")
            return
        if not JETSON_PROXY_SCRIPT.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(JETSON_PROXY_SCRIPT))
            return

        self._run_command(
            "上传代理脚本到 Jetson",
            ["scp", "-O", str(JETSON_PROXY_SCRIPT), "{}:~/jetson-proxy-session.sh".format(remote)],
            cwd=APP_DIR,
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

        source = "{}:{}".format(remote, remote_path)
        self._run_command(
            "从 Jetson 拉取项目",
            ["scp", "-O", "-r", source, "."],
            cwd=local_root,
        )

    def _python_launcher(self):
        if os.name == "nt":
            return ["py", "-3"]
        return [sys.executable]

    def _sync_command_base(self):
        remote = self.remote_edit.text().strip()
        remote_path = self.remote_path_edit.text().strip()
        command = self._python_launcher() + [
            str(SYNC_SCRIPT),
            "--remote",
            remote,
            "--remote-path",
            remote_path,
        ]
        return command

    def init_sync_state(self):
        if not SYNC_SCRIPT.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(SYNC_SCRIPT))
            return
        command = self._sync_command_base() + ["--init"]
        self._run_command("初始化同步状态", command, cwd=PROJECT_DIR)

    def sync_to_jetson(self):
        if not SYNC_SCRIPT.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(SYNC_SCRIPT))
            return

        command = self._sync_command_base()
        if self.full_sync_check.isChecked():
            command.append("--full")
        if self.dry_run_check.isChecked():
            command.append("--dry-run")
        if self.no_delete_check.isChecked():
            command.append("--no-delete")

        self._run_command("同步到 Jetson", command, cwd=PROJECT_DIR)

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
