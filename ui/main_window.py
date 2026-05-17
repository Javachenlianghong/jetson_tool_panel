#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main window for Jetson Tool Panel."""

import base64
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSettings, QTimer, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from core.command_runner import CommandWorker, format_command
from core.config_store import ProjectConfigStore, slugify
from core.paths import DEFAULTS, PATHS
from core.settings import settings_bool
from core.task_history import TaskHistoryStore
from services import device_health_service, display_service, proxy_service, remote_ops_service, ssh_service
from ui.pages.display_page import build_display_page
from ui.pages.devices_page import build_devices_page
from ui.pages.health_page import build_health_page
from ui.pages.help_page import build_help_page
from ui.pages.logs_page import build_logs_page
from ui.pages.environment_page import build_environment_page
from ui.pages.files_page import build_files_page
from ui.pages.network_page import build_network_page
from ui.pages.model_page import build_model_page
from ui.pages.peripheral_page import build_peripheral_page
from ui.pages.process_page import build_process_page
from ui.pages.proxy_page import build_proxy_page
from ui.pages.project_page import build_project_page
from ui.pages.runtime_page import build_runtime_page
from ui.pages.service_page import build_service_page
from ui.pages.report_page import build_report_page
from ui.pages.transfer_page import build_transfer_page
from ui.pages.workbench_page import build_workbench_page


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
        self.config_store = ProjectConfigStore(PATHS.project_config_path, DEFAULTS, PATHS)
        self.config_store.migrate_from_qsettings(self.settings)
        self.task_history_store = TaskHistoryStore(PATHS.task_history_path)
        self.worker = None
        self.defaults = DEFAULTS
        self.paths = PATHS

        self.ip_combo = None
        self.active_device_combo = None
        self.active_project_combo = None
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
        self.health_labels = {}
        self.health_refresh_button = None
        self.health_auto_check = None
        self.health_interval_combo = None
        self.workbench_labels = {}
        self.task_history_text = None
        self.run_workdir_edit = None
        self.run_command_edit = None
        self.run_background_check = None
        self.process_filter_edit = None
        self.kill_pid_edit = None
        self.pkill_pattern_edit = None
        self.log_tail_target_combo = None
        self.log_tail_lines_spin = None
        self.network_windows_ip_edit = None
        self.network_proxy_port_edit = None
        self.video_device_edit = None
        self.remote_file_path_edit = None
        self.local_file_path_edit = None
        self.service_name_edit = None
        self.model_workdir_edit = None
        self.model_source_edit = None
        self.model_output_edit = None
        self.model_precision_combo = None
        self.device_profile_combo = None
        self.device_name_edit = None
        self.device_remote_edit = None
        self.device_remote_path_edit = None
        self.device_local_root_edit = None
        self.project_id_edit = None
        self.project_name_edit = None
        self.project_local_root_edit = None
        self.project_remote_root_edit = None
        self.project_build_command_edit = None
        self.project_run_command_edit = None
        self.project_stop_pattern_edit = None
        self.project_log_target_edit = None
        self.report_dir_edit = None
        self.log_edit = None
        self.stop_button = None
        self.command_buttons = []
        self.nav_buttons = []
        self.page_stack = None
        self.current_command_title = None
        self.current_command_output = []
        self.current_command_started = None
        self.workflow_queue = []
        self.status_labels = {}
        self.status_dots = {}
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.refresh_device_health)

        self.setWindowTitle("Jetson 工具面板")
        self.resize(1080, 760)
        self._build_ui()
        self._apply_style()
        self.refresh_ips()
        self._load_settings()
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._refresh_task_history()
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
        subtitle = QLabel("Windows Clash 代理、SSH 项目同步、显示设置与设备监控。")
        subtitle.setObjectName("Subtitle")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(8)
        selector_layout.addWidget(QLabel("设备"))
        self.active_device_combo = QComboBox()
        self.active_device_combo.currentIndexChanged.connect(self._active_device_changed)
        selector_layout.addWidget(self.active_device_combo, 1)
        selector_layout.addWidget(QLabel("项目"))
        self.active_project_combo = QComboBox()
        self.active_project_combo.currentIndexChanged.connect(self._active_project_changed)
        selector_layout.addWidget(self.active_project_combo, 1)
        header_text.addLayout(selector_layout)
        header_layout.addLayout(header_text, 1)
        header_layout.addWidget(self._build_status_strip(), 2)
        main_layout.addLayout(header_layout)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("PageStack")
        self.page_stack.addWidget(build_workbench_page(self))
        self.page_stack.addWidget(build_proxy_page(self))
        self.page_stack.addWidget(build_transfer_page(self))
        self.page_stack.addWidget(build_project_page(self))
        self.page_stack.addWidget(build_runtime_page(self))
        self.page_stack.addWidget(build_process_page(self))
        self.page_stack.addWidget(build_logs_page(self))
        self.page_stack.addWidget(build_network_page(self))
        self.page_stack.addWidget(build_environment_page(self))
        self.page_stack.addWidget(build_peripheral_page(self))
        self.page_stack.addWidget(build_files_page(self))
        self.page_stack.addWidget(build_service_page(self))
        self.page_stack.addWidget(build_model_page(self))
        self.page_stack.addWidget(build_devices_page(self))
        self.page_stack.addWidget(build_report_page(self))
        self.page_stack.addWidget(build_health_page(self))
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
        sidebar.setFixedWidth(156)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(6)

        brand = QLabel("Jetson")
        brand.setObjectName("SidebarBrand")
        product = QLabel("Tool Panel")
        product.setObjectName("SidebarProduct")
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addSpacing(14)

        style = self.style()
        nav_specs = [
            ("工作台", style.standardIcon(QStyle.SP_DesktopIcon)),
            ("代理", style.standardIcon(QStyle.SP_DriveNetIcon)),
            ("项目传输", style.standardIcon(QStyle.SP_DirIcon)),
            ("项目配置", style.standardIcon(QStyle.SP_FileDialogContentsView)),
            ("运行控制", style.standardIcon(QStyle.SP_MediaPlay)),
            ("进程管理", style.standardIcon(QStyle.SP_FileDialogDetailedView)),
            ("日志查看", style.standardIcon(QStyle.SP_FileIcon)),
            ("网络诊断", style.standardIcon(QStyle.SP_DriveNetIcon)),
            ("环境检查", style.standardIcon(QStyle.SP_DialogApplyButton)),
            ("外设检测", style.standardIcon(QStyle.SP_DriveHDIcon)),
            ("文件管理", style.standardIcon(QStyle.SP_DirOpenIcon)),
            ("服务管理", style.standardIcon(QStyle.SP_BrowserReload)),
            ("模型部署", style.standardIcon(QStyle.SP_ArrowForward)),
            ("设备档案", style.standardIcon(QStyle.SP_FileDialogListView)),
            ("诊断报告", style.standardIcon(QStyle.SP_FileDialogInfoView)),
            ("设备状态", style.standardIcon(QStyle.SP_ComputerIcon)),
            ("显示设置", style.standardIcon(QStyle.SP_ComputerIcon)),
            ("命令参考", style.standardIcon(QStyle.SP_FileDialogInfoView)),
        ]

        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        for index, (text, icon) in enumerate(nav_specs):
            button = self._build_nav_button(text, icon)
            button.clicked.connect(lambda checked=False, page=index: self._switch_page(page))
            self.nav_buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)

        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("SidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setWidget(nav_container)
        layout.addWidget(nav_scroll, 1)

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
        button.setMinimumHeight(32)
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
            QLabel#MetricValue {
                color: #172033;
                font-size: 13px;
                font-weight: 700;
            }
            QFrame#Panel {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 8px;
            }
            QWidget#MetricBox {
                background: #fbfcfe;
                border: 1px solid #e3e9f2;
                border-radius: 6px;
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

    def _combo_current_data(self, combo):
        if not combo or combo.currentIndex() < 0:
            return None
        return combo.itemData(combo.currentIndex())

    def _set_combo_by_data(self, combo, value):
        if not combo:
            return
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _refresh_config_selectors(self):
        if not self.active_device_combo or not self.active_project_combo:
            return

        active_device = self.config_store.active_device() or {}
        active_project = self.config_store.active_project() or {}

        self.active_device_combo.blockSignals(True)
        self.active_device_combo.clear()
        for device in self.config_store.devices():
            label = "{} ({})".format(device.get("name", device.get("id")), device.get("ssh", ""))
            self.active_device_combo.addItem(label, device.get("id"))
        self._set_combo_by_data(self.active_device_combo, active_device.get("id"))
        self.active_device_combo.blockSignals(False)

        self.active_project_combo.blockSignals(True)
        self.active_project_combo.clear()
        device_id = self._combo_current_data(self.active_device_combo) or active_device.get("id")
        projects = self.config_store.projects(device_id) or self.config_store.projects()
        for project in projects:
            self.active_project_combo.addItem(project.get("name", project.get("id")), project.get("id"))
        self._set_combo_by_data(self.active_project_combo, active_project.get("id"))
        self.active_project_combo.blockSignals(False)

    def _active_device_changed(self, *_args):
        device_id = self._combo_current_data(self.active_device_combo)
        if not device_id:
            return
        self.config_store.set_active_device(device_id)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()

    def _active_project_changed(self, *_args):
        project_id = self._combo_current_data(self.active_project_combo)
        if not project_id:
            return
        self.config_store.set_active_project(project_id)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()

    def _active_context(self):
        return self.config_store.current_context()

    def _apply_active_context_to_forms(self):
        context = self._active_context()
        device = context["device"]
        project = context["project"]

        if self.remote_edit:
            self.remote_edit.setText(device.get("ssh", self.defaults.remote))
        if self.port_spin:
            self.port_spin.setValue(int(device.get("proxy_port", self.defaults.proxy_port) or self.defaults.proxy_port))
        if self.ip_combo and device.get("proxy_host"):
            self._set_combo_text(self.ip_combo, device.get("proxy_host"))
        if self.network_windows_ip_edit:
            self.network_windows_ip_edit.setText(device.get("proxy_host", self.ip_combo.currentText()))
        if self.network_proxy_port_edit:
            self.network_proxy_port_edit.setText(str(device.get("proxy_port", self.port_spin.value())))

        if self.remote_path_edit:
            self.remote_path_edit.setText(project.get("remote_root", self.defaults.remote_path))
        if self.local_root_edit:
            self.local_root_edit.setText(project.get("local_root", str(self.paths.app_dir)))
        if self.run_workdir_edit:
            self.run_workdir_edit.setText(project.get("remote_root", self.defaults.remote_path))
        if self.run_command_edit:
            self.run_command_edit.setText(project.get("run_command", "python3 detect.py"))
        if self.pkill_pattern_edit:
            self.pkill_pattern_edit.setText(project.get("stop_pattern", "detect.py"))
        if self.log_tail_target_combo:
            self._set_combo_text(self.log_tail_target_combo, project.get("log_target", "run-control.log"))
        if self.model_workdir_edit:
            self.model_workdir_edit.setText(project.get("remote_root", self.defaults.remote_path))
        self._apply_first_model_profile(project)
        self._load_project_config_to_form(project)
        self._load_device_config_to_form(device, project)
        self._refresh_workbench()

    def _apply_first_model_profile(self, project):
        profiles = project.get("model_profiles", []) if isinstance(project, dict) else []
        profile = profiles[0] if profiles else {}
        if self.model_source_edit:
            self.model_source_edit.setText(profile.get("source", self.model_source_edit.text() or "model.onnx"))
        if self.model_output_edit:
            self.model_output_edit.setText(profile.get("output", self.model_output_edit.text() or "model.engine"))
        if self.model_precision_combo:
            self._set_combo_text(self.model_precision_combo, profile.get("precision", "fp16"))

    def _load_project_config_to_form(self, project):
        if not self.project_id_edit or not isinstance(project, dict):
            return
        self.project_id_edit.setText(project.get("id", ""))
        self.project_name_edit.setText(project.get("name", ""))
        self.project_local_root_edit.setText(project.get("local_root", ""))
        self.project_remote_root_edit.setText(project.get("remote_root", ""))
        self.project_build_command_edit.setText(project.get("build_command", ""))
        self.project_run_command_edit.setText(project.get("run_command", ""))
        self.project_stop_pattern_edit.setText(project.get("stop_pattern", ""))
        self.project_log_target_edit.setText(project.get("log_target", ""))

    def _load_device_config_to_form(self, device, project):
        if not self.device_name_edit or not isinstance(device, dict):
            return
        self.device_name_edit.setText(device.get("name", ""))
        self.device_remote_edit.setText(device.get("ssh", ""))
        self.device_remote_path_edit.setText(project.get("remote_root", "") if isinstance(project, dict) else "")
        self.device_local_root_edit.setText(project.get("local_root", "") if isinstance(project, dict) else "")

    def _refresh_workbench(self):
        if not self.workbench_labels:
            return
        context = self._active_context()
        device = context["device"]
        project = context["project"]
        values = {
            "device": device.get("name", "-"),
            "ssh": device.get("ssh", "-"),
            "project": project.get("name", "-"),
            "remote_root": project.get("remote_root", "-"),
            "local_root": project.get("local_root", "-"),
        }
        for key, label in self.workbench_labels.items():
            label.setText(values.get(key, "-"))

    def _persist_active_config_from_forms(self):
        if not self.remote_edit or not self.remote_path_edit:
            return
        context = self._active_context()
        device = context["device"]
        project = context["project"]
        device_id = device.get("id") or "device"
        project_id = project.get("id") or "project"

        self.config_store.upsert_device({
            "id": device_id,
            "name": device.get("name", device_id),
            "type": device.get("type", "linux"),
            "ssh": self.remote_edit.text().strip(),
            "proxy_host": self.ip_combo.currentText().strip() if self.ip_combo else device.get("proxy_host", ""),
            "proxy_port": self.port_spin.value() if self.port_spin else device.get("proxy_port", self.defaults.proxy_port),
        })

        project_payload = dict(project)
        project_payload.update({
            "id": project_id,
            "device_id": device_id,
            "name": project.get("name", project_id),
            "local_root": self.local_root_edit.text().strip(),
            "remote_root": self.remote_path_edit.text().strip(),
            "build_command": self.project_build_command_edit.text().strip() if self.project_build_command_edit else project.get("build_command", ""),
            "run_command": self.run_command_edit.text().strip() if self.run_command_edit else project.get("run_command", ""),
            "stop_pattern": self.pkill_pattern_edit.text().strip() if self.pkill_pattern_edit else project.get("stop_pattern", ""),
            "log_target": self.log_tail_target_combo.currentText().strip() if self.log_tail_target_combo else project.get("log_target", ""),
        })
        self.config_store.upsert_project(project_payload)
        self._refresh_workbench()

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
        self._set_combo_text(self.health_interval_combo, self.settings.value("health/interval", "5 秒"))
        self.health_auto_check.setChecked(settings_bool(self.settings.value("health/auto_refresh"), False))
        self.run_command_edit.setText(str(self.settings.value("runtime/command", self.run_command_edit.text())))
        self.run_workdir_edit.setText(str(self.settings.value("runtime/workdir", self.run_workdir_edit.text())))
        self.run_background_check.setChecked(settings_bool(self.settings.value("runtime/background"), False))
        self.process_filter_edit.setText(str(self.settings.value("process/filter", "")))
        self._set_combo_text(self.log_tail_target_combo, self.settings.value("logs/target", self.log_tail_target_combo.currentText()))
        self.log_tail_lines_spin.setValue(self._setting_int("logs/lines", 120))
        self.video_device_edit.setText(str(self.settings.value("peripheral/video_device", "/dev/video0")))
        self.remote_file_path_edit.setText(str(self.settings.value("files/remote_path", self.remote_file_path_edit.text())))
        self.local_file_path_edit.setText(str(self.settings.value("files/local_path", self.local_file_path_edit.text())))
        self.service_name_edit.setText(str(self.settings.value("service/name", self.service_name_edit.text())))
        self.model_workdir_edit.setText(str(self.settings.value("model/workdir", self.model_workdir_edit.text())))
        self.model_source_edit.setText(str(self.settings.value("model/source", self.model_source_edit.text())))
        self.model_output_edit.setText(str(self.settings.value("model/output", self.model_output_edit.text())))
        self._set_combo_text(self.model_precision_combo, self.settings.value("model/precision", "fp16"))
        self.report_dir_edit.setText(str(self.settings.value("report/dir", self.report_dir_edit.text())))
        self._refresh_device_profile_combo()
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
        self.settings.setValue("health/auto_refresh", self.health_auto_check.isChecked())
        self.settings.setValue("health/interval", self.health_interval_combo.currentText().strip())
        self.settings.setValue("runtime/command", self.run_command_edit.text().strip())
        self.settings.setValue("runtime/workdir", self.run_workdir_edit.text().strip())
        self.settings.setValue("runtime/background", self.run_background_check.isChecked())
        self.settings.setValue("process/filter", self.process_filter_edit.text().strip())
        self.settings.setValue("logs/target", self.log_tail_target_combo.currentText().strip())
        self.settings.setValue("logs/lines", self.log_tail_lines_spin.value())
        self.settings.setValue("peripheral/video_device", self.video_device_edit.text().strip())
        self.settings.setValue("files/remote_path", self.remote_file_path_edit.text().strip())
        self.settings.setValue("files/local_path", self.local_file_path_edit.text().strip())
        self.settings.setValue("service/name", self.service_name_edit.text().strip())
        self.settings.setValue("model/workdir", self.model_workdir_edit.text().strip())
        self.settings.setValue("model/source", self.model_source_edit.text().strip())
        self.settings.setValue("model/output", self.model_output_edit.text().strip())
        self.settings.setValue("model/precision", self.model_precision_combo.currentText().strip())
        self.settings.setValue("report/dir", self.report_dir_edit.text().strip())
        self._persist_active_config_from_forms()
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
        self.current_command_output = []
        self.current_command_started = datetime.now()

        self.worker = CommandWorker(command, cwd=cwd, parent=self)
        self.worker.output.connect(self._handle_command_output)
        self.worker.failed_to_start.connect(self._command_failed_to_start)
        self.worker.finished_ok.connect(self._command_finished)
        self.worker.start()

    def _handle_command_output(self, line):
        self.current_command_output.append(line)
        self._append_log(line)

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
            self.workflow_queue = []
        self._record_task_history(title, return_code)
        self._set_running(False)
        self.current_command_title = None
        if return_code == 0 and self.workflow_queue:
            self._run_next_workflow_command()

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
        elif title == "刷新设备状态":
            data = device_health_service.parse_health_output(self.current_command_output)
            self._update_health_page(data)
        elif title == "生成诊断报告":
            self._save_diagnostic_report()

    def _record_task_history(self, title, return_code):
        context = self._active_context()
        device = context["device"]
        project = context["project"]
        started = self.current_command_started or datetime.now()
        entry = {
            "title": title,
            "device": device.get("name", ""),
            "project": project.get("name", ""),
            "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "return_code": return_code,
            "tail": "\n".join(self.current_command_output[-12:]),
        }
        self.task_history_store.add(entry)
        self._refresh_task_history()

    def _refresh_task_history(self):
        if not self.task_history_text:
            return
        history = self.task_history_store.load()[:8]
        if not history:
            self.task_history_text.setText("暂无任务历史")
            return
        lines = []
        for item in history:
            lines.append(
                "{time} [{code}] {title} / {device} / {project}".format(
                    time=item.get("finished_at", ""),
                    code=item.get("return_code", ""),
                    title=item.get("title", ""),
                    device=item.get("device", ""),
                    project=item.get("project", ""),
                )
            )
        self.task_history_text.setText("\n".join(lines))

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

    def refresh_device_health(self):
        if self.worker and self.worker.isRunning():
            return
        remote = self._remote_or_warn()
        if not remote:
            return
        command = ssh_service.remote_ssh_command(remote, device_health_service.health_command())
        self._run_command("刷新设备状态", command, cwd=self.paths.app_dir)

    def _toggle_health_auto_refresh(self, checked):
        if checked:
            self.health_timer.start(self._health_interval_ms())
        else:
            self.health_timer.stop()
        self._save_settings()

    def _health_interval_changed(self, _text):
        if self.health_timer.isActive():
            self.health_timer.start(self._health_interval_ms())
        self._save_settings()

    def _health_interval_ms(self):
        text = self.health_interval_combo.currentText() if self.health_interval_combo else "5 秒"
        try:
            seconds = int(str(text).split()[0])
        except (TypeError, ValueError, IndexError):
            seconds = 5
        return max(seconds, 1) * 1000

    def _update_health_page(self, data):
        for key, label in self.health_labels.items():
            label.setText(data.get(key) or "未知")

    def _current_project(self):
        return self._active_context()["project"]

    def _current_device(self):
        return self._active_context()["device"]

    def _remote_command_for_project(self, title, remote_command):
        remote = self._current_device().get("ssh") or self.remote_edit.text().strip()
        return (
            title,
            ssh_service.remote_ssh_command(remote, remote_command),
            self.paths.app_dir,
        )

    def _project_sync_step(self):
        project = self._current_project()
        device = self._current_device()
        command = ssh_service.sync_command(
            self.paths.sync_script,
            device.get("ssh", self.remote_edit.text().strip()),
            project.get("remote_root", self.remote_path_edit.text().strip()),
            full=self.full_sync_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            no_delete=self.no_delete_check.isChecked(),
        )
        return ("同步到 Jetson", command, self.paths.project_dir)

    def _run_next_workflow_command(self):
        if not self.workflow_queue:
            return
        title, command, cwd = self.workflow_queue.pop(0)
        self._run_command(title, command, cwd=cwd)

    def _start_workflow(self, steps):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "命令正在运行", "请等待当前命令结束，或先点击“停止当前命令”。")
            return
        self.workflow_queue = list(steps)
        self._run_next_workflow_command()

    def workflow_sync(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        self._start_workflow([self._project_sync_step()])

    def workflow_build(self):
        project = self._current_project()
        command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            project.get("build_command", self.project_build_command_edit.text().strip() or "true"),
            background=False,
        )
        self._start_workflow([self._remote_command_for_project("项目构建", command)])

    def workflow_run(self):
        project = self._current_project()
        command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            project.get("run_command", self.run_command_edit.text().strip()),
            background=True,
        )
        self._start_workflow([self._remote_command_for_project("项目后台运行", command)])

    def workflow_stop(self):
        pattern = self._current_project().get("stop_pattern", self.pkill_pattern_edit.text().strip())
        if not pattern:
            QMessageBox.warning(self, "缺少停止关键字", "请先在项目配置里填写停止关键字。")
            return
        answer = QMessageBox.question(
            self,
            "确认停止项目进程",
            "确定结束远端命令行匹配“{}”的进程？".format(pattern),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_workflow([
            self._remote_command_for_project("停止项目进程", remote_ops_service.pkill_pattern_command(pattern))
        ])

    def workflow_logs(self):
        target = self._current_project().get("log_target", self.log_tail_target_combo.currentText())
        self._start_workflow([
            self._remote_command_for_project("实时查看项目日志", remote_ops_service.tail_log_command(target, 120))
        ])

    def workflow_sync_build_run(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        project = self._current_project()
        build_command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            project.get("build_command", self.project_build_command_edit.text().strip() or "true"),
            background=False,
        )
        run_command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            project.get("run_command", self.run_command_edit.text().strip()),
            background=True,
        )
        steps = [
            self._project_sync_step(),
            self._remote_command_for_project("项目构建", build_command),
            self._remote_command_for_project("项目后台运行", run_command),
        ]
        self._start_workflow(steps)

    def run_remote_program(self):
        command = self.run_command_edit.text().strip()
        if not command:
            QMessageBox.warning(self, "缺少启动命令", "请填写要在远端执行的命令。")
            return
        remote_script = remote_ops_service.run_program_command(
            self.run_workdir_edit.text().strip(),
            command,
            self.run_background_check.isChecked(),
        )
        self._run_jetson_command("运行远程程序", remote_script)

    def list_remote_processes(self):
        self._run_jetson_command(
            "刷新远程进程",
            remote_ops_service.process_list_command(self.process_filter_edit.text()),
        )

    def kill_remote_pid(self):
        pid = self.kill_pid_edit.text().strip()
        if not pid:
            QMessageBox.warning(self, "缺少 PID", "请填写要结束的远程进程 PID。")
            return
        answer = QMessageBox.question(
            self,
            "确认结束进程",
            "确定向远端 PID {} 发送 TERM 信号？".format(pid),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_jetson_command("结束远程进程", remote_ops_service.kill_pid_command(pid))

    def pkill_remote_pattern(self):
        pattern = self.pkill_pattern_edit.text().strip()
        if not pattern:
            QMessageBox.warning(self, "缺少关键字", "请填写要匹配的远程进程关键字。")
            return
        answer = QMessageBox.question(
            self,
            "确认按关键字结束进程",
            "确定结束远端命令行匹配“{}”的进程？".format(pattern),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_jetson_command("按关键字结束远程进程", remote_ops_service.pkill_pattern_command(pattern))

    def tail_remote_log(self):
        self._run_jetson_command(
            "实时查看远程日志",
            remote_ops_service.tail_log_command(
                self.log_tail_target_combo.currentText(),
                self.log_tail_lines_spin.value(),
            ),
        )

    def run_network_diagnostics(self):
        self._run_jetson_command(
            "网络连通性诊断",
            remote_ops_service.network_diagnostics_command(
                self.network_windows_ip_edit.text(),
                self.network_proxy_port_edit.text(),
            ),
        )

    def run_environment_check(self):
        self._run_jetson_command("开发环境检查", remote_ops_service.environment_check_command())

    def run_peripheral_check(self):
        self._run_jetson_command(
            "外设检测",
            remote_ops_service.peripheral_check_command(self.video_device_edit.text()),
        )

    def list_remote_files(self):
        self._run_jetson_command(
            "列出远程文件",
            remote_ops_service.file_list_command(self.remote_file_path_edit.text()),
        )

    def mkdir_remote_path(self):
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要创建的远端目录。")
            return
        self._run_jetson_command("新建远程目录", remote_ops_service.mkdir_command(remote_path))

    def remove_remote_path(self):
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要删除的远端路径。")
            return
        answer = QMessageBox.question(
            self,
            "确认删除远端路径",
            "确定递归删除远端路径？\n\n{}".format(remote_path),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_jetson_command("删除远端路径", remote_ops_service.remove_path_command(remote_path))

    def upload_single_file(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        local_path = self.local_file_path_edit.text().strip()
        if not local_path or not Path(local_path).is_file():
            local_path, _ = QFileDialog.getOpenFileName(self, "选择要上传的文件", str(self.paths.app_dir))
            if not local_path:
                return
            self.local_file_path_edit.setText(local_path)
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写上传目标远端路径。")
            return
        target = "{}:{}".format(remote, remote_path)
        self._run_command("上传单文件", ["scp", "-O", local_path, target], cwd=self.paths.app_dir)

    def download_single_file(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要下载的远端文件路径。")
            return
        local_path = self.local_file_path_edit.text().strip()
        if not local_path or not Path(local_path).exists():
            local_path = QFileDialog.getExistingDirectory(self, "选择本地保存目录", str(self.paths.app_dir))
            if not local_path:
                return
            self.local_file_path_edit.setText(local_path)
        source = "{}:{}".format(remote, remote_path)
        self._run_command("下载单文件", ["scp", "-O", source, local_path], cwd=self.paths.app_dir)

    def _service_action(self, action, confirm=False):
        service_name = self.service_name_edit.text().strip()
        if not service_name:
            QMessageBox.warning(self, "缺少服务名", "请填写 systemd 服务名。")
            return
        if confirm:
            answer = QMessageBox.question(
                self,
                "确认服务操作",
                "确定对远端服务执行 {}？\n\n{}".format(action, service_name),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self._run_jetson_command(
            "服务{}: {}".format(action, service_name),
            remote_ops_service.service_command(service_name, action),
        )

    def service_status(self):
        self._service_action("status")

    def service_start(self):
        self._service_action("start", confirm=True)

    def service_stop(self):
        self._service_action("stop", confirm=True)

    def service_restart(self):
        self._service_action("restart", confirm=True)

    def service_logs(self):
        self._service_action("logs")

    def _current_tensorrt_command(self):
        return remote_ops_service.tensorrt_command(
            self.model_workdir_edit.text(),
            self.model_source_edit.text(),
            self.model_output_edit.text(),
            self.model_precision_combo.currentText(),
        )

    def run_tensorrt_conversion(self):
        self._run_jetson_command("TensorRT 模型转换", self._current_tensorrt_command())

    def show_rknn_template(self):
        self._run_jetson_command(
            "显示 RKNN 部署模板",
            remote_ops_service.rknn_template_command(
                self.model_workdir_edit.text(),
                self.model_source_edit.text(),
                self.model_output_edit.text(),
            ),
        )

    def copy_model_command(self):
        command = self._current_tensorrt_command()
        QApplication.clipboard().setText(command)
        self._append_log("已复制 TensorRT 命令模板: " + command)

    def _device_profiles(self):
        raw = self.settings.value("devices/profiles", "{}")
        try:
            profiles = json.loads(str(raw))
        except (TypeError, ValueError):
            profiles = {}
        return profiles if isinstance(profiles, dict) else {}

    def _write_device_profiles(self, profiles):
        self.settings.setValue("devices/profiles", json.dumps(profiles, ensure_ascii=False, sort_keys=True))
        self.settings.sync()

    def _refresh_device_profile_combo(self):
        if not self.device_profile_combo:
            return
        current = self.device_profile_combo.currentText()
        self.device_profile_combo.clear()
        for device in self.config_store.devices():
            self.device_profile_combo.addItem(device.get("name", device.get("id")), device.get("id"))
        if current:
            index = self.device_profile_combo.findText(current)
            if index >= 0:
                self.device_profile_combo.setCurrentIndex(index)

    def fill_device_profile_from_current(self):
        self.device_remote_edit.setText(self.remote_edit.text().strip())
        self.device_remote_path_edit.setText(self.remote_path_edit.text().strip())
        self.device_local_root_edit.setText(self.local_root_edit.text().strip())
        name = self.remote_edit.text().strip().split("@")[-1] or "设备"
        self.device_name_edit.setText(name)

    def save_device_profile(self):
        name = self.device_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "缺少名称", "请填写设备档案名称。")
            return
        device_id = slugify(name, "device")
        self.config_store.upsert_device({
            "id": device_id,
            "name": name,
            "type": "linux",
            "ssh": self.device_remote_edit.text().strip(),
            "proxy_host": self.ip_combo.currentText().strip(),
            "proxy_port": self.port_spin.value(),
        })
        current_project = self._current_project()
        project_payload = dict(current_project)
        project_payload.update({
            "device_id": device_id,
            "local_root": self.device_local_root_edit.text().strip(),
            "remote_root": self.device_remote_path_edit.text().strip(),
        })
        self.config_store.upsert_project(project_payload)
        self._refresh_config_selectors()
        self._refresh_device_profile_combo()
        self._apply_active_context_to_forms()
        self._append_log("已保存设备档案: " + name)

    def load_device_profile(self):
        device_id = self._combo_current_data(self.device_profile_combo)
        device = self.config_store.get_device(device_id)
        if not device:
            QMessageBox.warning(self, "找不到档案", "请选择要加载的设备档案。")
            return
        self.config_store.set_active_device(device_id)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._append_log("已加载设备档案: " + device.get("name", device_id))

    def delete_device_profile(self):
        device_id = self._combo_current_data(self.device_profile_combo)
        device = self.config_store.get_device(device_id)
        if not device:
            return
        answer = QMessageBox.question(
            self,
            "确认删除档案",
            "确定删除设备档案及其关联项目？\n\n{}".format(device.get("name", device_id)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config_store.delete_device(device_id)
        self._refresh_config_selectors()
        self._refresh_device_profile_combo()
        self._apply_active_context_to_forms()
        self._append_log("已删除设备档案: " + device.get("name", device_id))

    def fill_project_config_from_current(self):
        context = self._active_context()
        project = context["project"]
        self.project_id_edit.setText(project.get("id", "project"))
        self.project_name_edit.setText(project.get("name", "Project"))
        self.project_local_root_edit.setText(self.local_root_edit.text().strip())
        self.project_remote_root_edit.setText(self.remote_path_edit.text().strip())
        self.project_build_command_edit.setText(project.get("build_command", "cmake --build build -j4"))
        self.project_run_command_edit.setText(self.run_command_edit.text().strip())
        self.project_stop_pattern_edit.setText(self.pkill_pattern_edit.text().strip())
        self.project_log_target_edit.setText(self.log_tail_target_combo.currentText().strip())

    def load_project_config_to_form(self):
        self._load_project_config_to_form(self._current_project())

    def save_project_config(self):
        name = self.project_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "缺少项目名称", "请填写项目名称。")
            return
        project_id = self.project_id_edit.text().strip() or slugify(name, "project")
        device_id = self._current_device().get("id") or self._combo_current_data(self.active_device_combo)
        self.config_store.upsert_project({
            "id": project_id,
            "device_id": device_id,
            "name": name,
            "local_root": self.project_local_root_edit.text().strip(),
            "remote_root": self.project_remote_root_edit.text().strip(),
            "build_command": self.project_build_command_edit.text().strip(),
            "run_command": self.project_run_command_edit.text().strip(),
            "stop_pattern": self.project_stop_pattern_edit.text().strip(),
            "log_target": self.project_log_target_edit.text().strip(),
            "model_profiles": self._current_project().get("model_profiles", []),
        })
        self._refresh_config_selectors()
        self._set_combo_by_data(self.active_project_combo, project_id)
        self.config_store.set_active_project(project_id)
        self._apply_active_context_to_forms()
        self._append_log("已保存项目配置: " + name)

    def delete_project_config(self):
        project = self._current_project()
        project_id = project.get("id")
        if not project_id:
            return
        answer = QMessageBox.question(
            self,
            "确认删除项目",
            "确定删除项目配置？\n\n{}".format(project.get("name", project_id)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config_store.delete_project(project_id)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._append_log("已删除项目配置: " + project.get("name", project_id))

    def choose_report_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择诊断报告保存目录", self.report_dir_edit.text())
        if path:
            self.report_dir_edit.setText(path)

    def generate_diagnostic_report(self):
        command = remote_ops_service.diagnostic_report_command(
            self.network_windows_ip_edit.text(),
            self.network_proxy_port_edit.text(),
            self.video_device_edit.text(),
        )
        self._run_jetson_command("生成诊断报告", command)

    def _save_diagnostic_report(self):
        report_dir = Path(self.report_dir_edit.text().strip() or (self.paths.tool_dir / "reports"))
        report_dir.mkdir(parents=True, exist_ok=True)
        safe_remote = self.remote_edit.text().strip().replace("@", "_").replace(":", "_").replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = report_dir / "diagnostic-{}-{}.md".format(safe_remote or "device", timestamp)
        body = "\n".join(self.current_command_output)
        header = [
            "# Jetson Tool Panel 诊断报告",
            "",
            "- Remote: {}".format(self.remote_edit.text().strip()),
            "- Windows IP: {}".format(self.ip_combo.currentText().strip()),
            "- Proxy Port: {}".format(self.port_spin.value()),
            "- Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "",
            "```text",
            body,
            "```",
            "",
        ]
        report_path.write_text("\n".join(header), encoding="utf-8")
        self._append_log("诊断报告已保存: " + str(report_path))

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
