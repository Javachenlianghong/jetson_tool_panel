#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main window for Jetson Tool Panel."""

import base64
import hashlib
import os
import posixpath
import shutil
import socket
import subprocess
import sys
import time
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
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.command_controller import CommandController
from core.command_runner import format_command
from core.model_workers import RemoteModelScanWorker
from core.config_store import ProjectConfigStore, slugify
from core.paths import DEFAULTS, PATHS
from core.resource_monitor import ResourceMonitorWorker
from core.settings import settings_bool
from core.task_history import TaskHistoryStore
from core.ssh_workers import SftpWorker, SshTerminalWorker
from core.terminal_filter import PlainTerminalBuffer
from services import device_health_service, display_service, paramiko_service, proxy_service, remote_ops_service, ssh_service
from ui.pages.display_page import build_display_page
from ui.pages.devices_page import build_devices_page
from ui.pages.health_page import build_health_page
from ui.pages.help_page import build_help_page
from ui.pages.logs_page import build_logs_page
from ui.pages.environment_page import build_environment_page
from ui.pages.network_page import build_network_page
from ui.pages.model_page import build_model_page
from ui.pages.peripheral_page import build_peripheral_page
from ui.pages.process_page import build_process_page
from ui.pages.proxy_page import build_proxy_page
from ui.pages.project_page import build_project_page
from ui.pages.runtime_page import build_runtime_page
from ui.pages.service_page import build_service_page
from ui.pages.terminal_page import build_terminal_page
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
        self.command_controller = CommandController(self)
        self.command_controller.output.connect(self._handle_command_output)
        self.command_controller.timed_out.connect(self._command_timed_out)
        self.command_controller.failed_to_start.connect(self._command_failed_to_start)
        self.command_controller.finished.connect(self._command_finished)
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
        self.environment_summary_label = {}
        self.environment_result_labels = {}
        self.environment_updated_label = None
        self.environment_init_text = None
        self.network_result_labels = {}
        self.network_checks_text = None
        self.peripheral_result_labels = {}
        self.process_summary_label = None
        self.process_table = None
        self.files_summary_label = None
        self.files_table = None
        self.local_files_table = None
        self.remote_files_table = None
        self.transfer_progress_bar = None
        self.sftp_worker = None
        self.sftp_password = None
        self.pending_sftp_retry = None
        self.pending_sftp_refresh = None
        self.service_result_labels = {}
        self.service_status_text = None
        self.terminal_status_label = None
        self.terminal_output_edit = None
        self.terminal_export_display_check = None
        self.terminal_buffer = PlainTerminalBuffer()
        self.terminal_worker = None
        self.terminal_password = None
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
        self.remote_path_bookmark_combo = None
        self.local_file_path_edit = None
        self.service_name_edit = None
        self.model_workdir_edit = None
        self.model_profile_combo = None
        self.model_name_edit = None
        self.model_source_edit = None
        self.model_choose_source_button = None
        self.model_output_edit = None
        self.model_test_image_edit = None
        self.model_precision_combo = None
        self.model_scan_worker = None
        self.pending_model_scan_password = None
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
        self.nav_page_keys = []
        self.page_key_to_index = {}
        self.navigation_groups = []
        self.page_stack = None
        self.log_splitter = None
        self.current_command_title = None
        self.current_command_output = []
        self.current_command_started = None
        self.current_command_timeout_seconds = None
        self.command_timed_out = False
        self.workflow_queue = []
        self.status_labels = {}
        self.status_dots = {}
        self.monitor_labels = {}
        self.monitor_status_label = None
        self.resource_monitor_worker = None
        self.resource_monitor_remote = None
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
        self._restart_resource_monitor()

    def _build_ui(self):
        self.navigation_groups = self._navigation_groups()
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
        selector_layout.addWidget(QLabel("远端 SSH"))
        self.remote_edit = QLineEdit(self.defaults.remote)
        self.remote_edit.setPlaceholderText("jetson@192.168.55.1 或 192.168.55.1")
        self.remote_edit.editingFinished.connect(self._top_remote_editing_finished)
        selector_layout.addWidget(self.remote_edit, 2)
        connect_button = QPushButton("连接")
        connect_button.setObjectName("PrimaryButton")
        connect_button.clicked.connect(self.test_ssh)
        self.command_buttons.append(connect_button)
        selector_layout.addWidget(connect_button)
        header_text.addLayout(selector_layout)
        header_layout.addLayout(header_text, 1)
        header_layout.addWidget(self._build_status_strip())
        main_layout.addLayout(header_layout)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("PageStack")
        for key, _text, _icon, builder in self._flatten_navigation_groups():
            self.page_key_to_index[key] = self.page_stack.count()
            self.page_stack.addWidget(builder(self))

        self.log_splitter = QSplitter(Qt.Vertical)
        self.log_splitter.setObjectName("MainLogSplitter")
        self.log_splitter.setChildrenCollapsible(False)
        self.log_splitter.setHandleWidth(8)
        self.log_splitter.addWidget(self.page_stack)

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

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        log_font = QFont("Consolas")
        log_font.setStyleHint(QFont.Monospace)
        log_font.setPointSize(10)
        self.log_edit.setFont(log_font)
        self.log_edit.setMinimumHeight(80)

        log_panel = QWidget()
        log_panel.setObjectName("LogPanel")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(8)
        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_edit)
        log_panel.setMinimumHeight(110)

        self.log_splitter.addWidget(log_panel)
        self.log_splitter.setStretchFactor(0, 1)
        self.log_splitter.setStretchFactor(1, 0)
        self.log_splitter.setSizes([560, 160])
        main_layout.addWidget(self.log_splitter, 1)
        main_layout.addWidget(self._build_resource_monitor_bar())

        root_layout.addWidget(main, 1)
        self.setCentralWidget(central)

    def _navigation_groups(self):
        style = self.style()
        return [
            (
                "常用",
                [
                    ("workbench", "工作台", style.standardIcon(QStyle.SP_DesktopIcon), build_workbench_page),
                    ("proxy", "代理设置", style.standardIcon(QStyle.SP_DriveNetIcon), build_proxy_page),
                    ("health", "设备状态", style.standardIcon(QStyle.SP_ComputerIcon), build_health_page),
                    ("terminal", "SSH 工作台", style.standardIcon(QStyle.SP_ComputerIcon), build_terminal_page),
                    ("runtime", "运行控制", style.standardIcon(QStyle.SP_MediaPlay), build_runtime_page),
                    ("logs", "日志查看", style.standardIcon(QStyle.SP_FileIcon), build_logs_page),
                    ("process", "进程管理", style.standardIcon(QStyle.SP_FileDialogDetailedView), build_process_page),
                ],
            ),
            (
                "项目",
                [
                    ("transfer", "项目传输", style.standardIcon(QStyle.SP_DirIcon), build_transfer_page),
                    ("project", "项目配置", style.standardIcon(QStyle.SP_FileDialogContentsView), build_project_page),
                    ("service", "服务管理", style.standardIcon(QStyle.SP_BrowserReload), build_service_page),
                    ("model", "模型部署", style.standardIcon(QStyle.SP_ArrowForward), build_model_page),
                ],
            ),
            (
                "诊断",
                [
                    ("network", "网络诊断", style.standardIcon(QStyle.SP_DriveNetIcon), build_network_page),
                    ("environment", "环境检查", style.standardIcon(QStyle.SP_DialogApplyButton), build_environment_page),
                    ("peripheral", "外设检测", style.standardIcon(QStyle.SP_DriveHDIcon), build_peripheral_page),
                    ("display", "显示设置", style.standardIcon(QStyle.SP_ComputerIcon), build_display_page),
                    ("report", "诊断报告", style.standardIcon(QStyle.SP_FileDialogInfoView), build_report_page),
                ],
            ),
            (
                "配置",
                [
                    ("devices", "设备档案", style.standardIcon(QStyle.SP_FileDialogListView), build_devices_page),
                    ("help", "命令参考", style.standardIcon(QStyle.SP_FileDialogInfoView), build_help_page),
                ],
            ),
        ]

    def _flatten_navigation_groups(self):
        for _group_title, items in self.navigation_groups:
            for item in items:
                yield item

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(168)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 14, 10, 12)
        layout.setSpacing(6)

        brand = QLabel("Jetson")
        brand.setObjectName("SidebarBrand")
        product = QLabel("Tool Panel")
        product.setObjectName("SidebarProduct")
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addSpacing(14)

        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(3)
        page_index = 0
        for group_title, items in self.navigation_groups:
            group_label = QLabel(group_title)
            group_label.setObjectName("NavGroupLabel")
            nav_layout.addWidget(group_label)
            for key, text, icon, _builder in items:
                button = self._build_nav_button(text, icon)
                button.clicked.connect(lambda checked=False, page=page_index: self._switch_page(page))
                button.setProperty("page_key", key)
                self.nav_buttons.append(button)
                self.nav_page_keys.append(key)
                nav_layout.addWidget(button)
                page_index += 1
            nav_layout.addSpacing(6)
        nav_layout.addStretch(1)

        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("SidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setWidget(nav_container)
        layout.addWidget(nav_scroll, 1)

        style = self.style()
        settings_button = self._build_nav_button("数据位置", style.standardIcon(QStyle.SP_FileDialogDetailedView))
        settings_button.setCheckable(False)
        settings_button.clicked.connect(self._show_settings_info)
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
        card.setFixedWidth(176)
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

    def _build_resource_monitor_bar(self):
        bar = QFrame()
        bar.setObjectName("MonitorBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(14)

        title = QLabel("资源监控")
        title.setObjectName("MonitorTitle")
        layout.addWidget(title)

        self.monitor_labels = {}
        for key, name in (
            ("cpu", "CPU"),
            ("memory", "内存"),
            ("gpu", "GPU"),
            ("temperature", "温度"),
        ):
            label = QLabel("--")
            label.setObjectName("MonitorValue")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.monitor_labels[key] = label

            group = QHBoxLayout()
            group.setSpacing(5)
            name_label = QLabel(name)
            name_label.setObjectName("MonitorName")
            group.addWidget(name_label)
            group.addWidget(label)
            layout.addLayout(group)

        layout.addStretch(1)
        self.monitor_status_label = QLabel("未连接")
        self.monitor_status_label.setObjectName("MonitorStatus")
        self.monitor_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.monitor_status_label)
        return bar

    def _switch_page(self, index):
        if not self.page_stack:
            return
        if index < 0 or index >= self.page_stack.count():
            index = 0
        self.page_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        self.settings.setValue("window/current_page", index)
        if 0 <= index < len(self.nav_page_keys):
            self.settings.setValue("window/current_page_key", self.nav_page_keys[index])

    def _switch_page_by_key(self, key, fallback_index=0):
        index = self.page_key_to_index.get(str(key), fallback_index)
        self._switch_page(index)

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

    def _update_resource_monitor(self, metrics):
        if not metrics:
            return
        for key in ("cpu", "memory", "gpu", "temperature"):
            label = self.monitor_labels.get(key)
            if label is not None:
                label.setText(str(metrics.get(key) or "未知"))
        raw = str(metrics.get("raw") or "")
        for label in self.monitor_labels.values():
            label.setToolTip(raw)
        if self.monitor_status_label is not None:
            self.monitor_status_label.setText(
                "监控中: {}".format(self.resource_monitor_remote or self._normalize_remote_text(self.remote_edit.text()))
            )
            self.monitor_status_label.setToolTip(raw)

    def _set_resource_monitor_status(self, status):
        if self.monitor_status_label is not None:
            self.monitor_status_label.setText(str(status or "未知"))

    def _stop_resource_monitor(self):
        worker = self.resource_monitor_worker
        self.resource_monitor_worker = None
        if worker and worker.isRunning():
            worker.stop()
            worker.wait(2000)

    def _restart_resource_monitor(self):
        remote = self._normalize_remote_text(self.remote_edit.text()) if self.remote_edit is not None else ""
        if remote and self.remote_edit is not None and remote != self.remote_edit.text().strip():
            self.remote_edit.setText(remote)
        self._stop_resource_monitor()
        self.resource_monitor_remote = remote
        for label in self.monitor_labels.values():
            label.setText("--")
            label.setToolTip("")
        if not remote:
            self._set_resource_monitor_status("未配置 SSH")
            return
        self._set_resource_monitor_status("监控连接中: {}".format(remote))
        worker = ResourceMonitorWorker(remote, parent=self)
        worker.metrics.connect(self._update_resource_monitor)
        worker.status.connect(self._set_resource_monitor_status)
        self.resource_monitor_worker = worker
        worker.start()

    def _show_about(self):
        QMessageBox.information(
            self,
            "关于",
            "Jetson 工具面板\n\n用于管理 Windows 代理、Jetson SSH、项目同步与显示分辨率。",
        )

    def _show_settings_info(self):
        QMessageBox.information(
            self,
            "设置与数据位置",
            "\n".join([
                "常用配置会自动保存。",
                "",
                "基础设置: {}".format(self.paths.config_path),
                "项目配置: {}".format(self.paths.project_config_path),
                "任务历史: {}".format(self.paths.task_history_path),
                "工具目录: {}".format(self.paths.tool_dir),
                "工作目录: {}".format(self.paths.app_dir),
            ]),
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
            QScrollArea#PageScroll, QWidget#PageScrollContent {
                background: transparent;
                border: none;
            }
            QWidget#LogPanel {
                background: transparent;
            }
            QSplitter#MainLogSplitter::handle {
                background: #dbe3ef;
                border-radius: 3px;
            }
            QSplitter#MainLogSplitter::handle:hover {
                background: #b8c7dc;
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
            QLabel#NavGroupLabel {
                color: #98a2b3;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 8px 3px 8px;
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
            QFrame#MonitorBar {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 8px;
            }
            QLabel#MonitorTitle {
                color: #172033;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#MonitorName {
                color: #667085;
                font-size: 12px;
            }
            QLabel#MonitorValue {
                color: #172033;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#MonitorStatus {
                color: #475569;
                font-size: 12px;
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
            QWidget#MetricBox[state="ok"], QFrame#MetricBox[state="ok"] {
                background: #f0fdf4;
                border-color: #bbf7d0;
            }
            QWidget#MetricBox[state="warning"], QFrame#MetricBox[state="warning"] {
                background: #fffbeb;
                border-color: #fde68a;
            }
            QWidget#MetricBox[state="error"], QFrame#MetricBox[state="error"] {
                background: #fef2f2;
                border-color: #fecaca;
            }
            QWidget#MetricBox[state="unknown"], QFrame#MetricBox[state="unknown"] {
                background: #f8fafc;
                border-color: #cbd5e1;
            }
            QFrame#EnvResultCard {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 8px;
            }
            QFrame#EnvResultCard[state="ok"] {
                border-color: #86efac;
            }
            QFrame#EnvResultCard[state="warning"] {
                border-color: #facc15;
            }
            QFrame#EnvResultCard[state="error"] {
                border-color: #fca5a5;
            }
            QFrame#EnvResultCard[state="unknown"] {
                border-color: #cbd5e1;
            }
            QFrame#ResultCard {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 8px;
            }
            QFrame#ResultCard[state="ok"] {
                border-color: #86efac;
            }
            QFrame#ResultCard[state="warning"] {
                border-color: #facc15;
            }
            QFrame#ResultCard[state="error"] {
                border-color: #fca5a5;
            }
            QFrame#ResultCard[state="unknown"] {
                border-color: #cbd5e1;
            }
            QLabel#EnvBadge {
                background: #eef2f7;
                border-radius: 10px;
                color: #475569;
                font-size: 11px;
                font-weight: 700;
                padding: 3px 8px;
            }
            QLabel#EnvBadge[state="ok"] {
                background: #dcfce7;
                color: #166534;
            }
            QLabel#EnvBadge[state="warning"] {
                background: #fef3c7;
                color: #92400e;
            }
            QLabel#EnvBadge[state="error"] {
                background: #fee2e2;
                color: #991b1b;
            }
            QLabel#EnvBadge[state="unknown"] {
                background: #e2e8f0;
                color: #475569;
            }
            QLabel#EnvBadge[state="pending"] {
                background: #e0ecff;
                color: #1d4ed8;
            }
            QLabel#StatusBadge {
                background: #eef2f7;
                border-radius: 10px;
                color: #475569;
                font-size: 11px;
                font-weight: 700;
                padding: 3px 8px;
            }
            QLabel#StatusBadge[state="ok"] {
                background: #dcfce7;
                color: #166534;
            }
            QLabel#StatusBadge[state="warning"] {
                background: #fef3c7;
                color: #92400e;
            }
            QLabel#StatusBadge[state="error"] {
                background: #fee2e2;
                color: #991b1b;
            }
            QLabel#StatusBadge[state="unknown"] {
                background: #e2e8f0;
                color: #475569;
            }
            QLabel#StatusBadge[state="pending"] {
                background: #e0ecff;
                color: #1d4ed8;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #dde3ec;
                border-radius: 6px;
                gridline-color: #e5ebf3;
                alternate-background-color: #f8fbff;
                color: #172033;
            }
            QHeaderView::section {
                background: #f4f7fb;
                border: none;
                border-bottom: 1px solid #dde3ec;
                color: #465568;
                font-weight: 700;
                padding: 6px;
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
            QPlainTextEdit#TerminalOutput {
                background: #0f172a;
                border-color: #1e293b;
                color: #e5e7eb;
                selection-background-color: #2563eb;
            }
            QSplitter::handle {
                background: #dbe3ef;
                border-radius: 3px;
            }
            QSplitter::handle:hover {
                background: #b8c7dc;
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
                padding: 7px 9px;
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
        current = self.ip_combo.currentText().strip() if self.ip_combo is not None else ""
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

    def _normalize_remote_text(self, text):
        remote = str(text or "").strip()
        if remote and "@" not in remote:
            remote = "jetson@{}".format(remote)
        return remote

    def _top_remote_editing_finished(self):
        if self.remote_edit is None:
            return
        remote = self._normalize_remote_text(self.remote_edit.text())
        if remote != self.remote_edit.text().strip():
            self.remote_edit.setText(remote)
        if not remote:
            return

        device = self._current_device()
        if device.get("id"):
            payload = dict(device)
            payload["ssh"] = remote
            self.config_store.upsert_device(payload)
            self._refresh_config_selectors()
        if self.device_remote_edit is not None:
            self.device_remote_edit.setText(remote)
        self._refresh_workbench()
        self._restart_resource_monitor()

    def _combo_current_data(self, combo):
        if combo is None or combo.currentIndex() < 0:
            return None
        return combo.itemData(combo.currentIndex())

    def _set_combo_by_data(self, combo, value):
        if combo is None:
            return
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _refresh_config_selectors(self):
        if self.active_device_combo is None or self.active_project_combo is None:
            return

        active_device = self.config_store.active_device() or {}
        active_project = self.config_store.active_project() or {}

        self.active_device_combo.blockSignals(True)
        self.active_device_combo.clear()
        for device in self.config_store.devices():
            label = device.get("name", device.get("id"))
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
        self._restart_resource_monitor()

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
        if self.ip_combo is not None and device.get("proxy_host"):
            self._set_combo_text(self.ip_combo, device.get("proxy_host"))
        if self.network_windows_ip_edit:
            self.network_windows_ip_edit.setText(device.get("proxy_host", self.ip_combo.currentText()))
        if self.network_proxy_port_edit:
            self.network_proxy_port_edit.setText(str(device.get("proxy_port", self.port_spin.value())))

        if self.remote_path_edit:
            self.remote_path_edit.setText(project.get("remote_root", self.defaults.remote_path))
        if self.local_root_edit:
            self.local_root_edit.setText(project.get("local_root", str(self.paths.app_dir)))
        if self.remote_file_path_edit:
            self.remote_file_path_edit.setText(project.get("remote_root", self.defaults.remote_path))
        if self.local_file_path_edit:
            self.local_file_path_edit.setText(project.get("local_root", str(self.paths.app_dir)))
        if self.run_workdir_edit:
            self.run_workdir_edit.setText(project.get("remote_root", self.defaults.remote_path))
        if self.run_command_edit:
            self.run_command_edit.setText(project.get("run_command", "python3 detect.py"))
        if self.pkill_pattern_edit:
            self.pkill_pattern_edit.setText(project.get("stop_pattern", "detect.py"))
        if self.log_tail_target_combo is not None:
            self._set_combo_text(self.log_tail_target_combo, project.get("log_target", "run-control.log"))
        if self.model_workdir_edit:
            self.model_workdir_edit.setText(project.get("remote_root", self.defaults.remote_path))
        self._apply_first_model_profile(project)
        self._load_project_config_to_form(project)
        self._load_device_config_to_form(device, project)
        self._refresh_workbench()
        self._refresh_remote_path_bookmarks()
        if self.local_files_table is not None:
            self.refresh_local_files(warn=False)

    def _apply_first_model_profile(self, project):
        profiles = project.get("model_profiles", []) if isinstance(project, dict) else []
        profile = profiles[0] if profiles else {}
        if self.model_profile_combo is not None:
            current = self.model_profile_combo.currentData()
            self.model_profile_combo.blockSignals(True)
            self.model_profile_combo.clear()
            for item in profiles:
                self.model_profile_combo.addItem(item.get("name", item.get("id", "")), item.get("id"))
            self.model_profile_combo.blockSignals(False)
            if current:
                self._set_combo_by_data(self.model_profile_combo, current)
            elif profile.get("id"):
                self._set_combo_by_data(self.model_profile_combo, profile.get("id"))
        if self.model_name_edit:
            self.model_name_edit.setText(profile.get("name", self.model_name_edit.text() or "Default Model"))
        if self.model_source_edit:
            self.model_source_edit.setText(profile.get("source", self.model_source_edit.text() or "model.onnx"))
        if self.model_output_edit:
            self.model_output_edit.setText(profile.get("output", self.model_output_edit.text() or "model.engine"))
        if self.model_test_image_edit:
            self.model_test_image_edit.setText(profile.get("test_image", self.model_test_image_edit.text() or "test.jpg"))
        if self.model_precision_combo is not None:
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

    def _remote_path_bookmarks(self):
        project = self._current_project()
        bookmarks = project.get("file_bookmarks", []) if isinstance(project, dict) else []
        if not isinstance(bookmarks, list):
            bookmarks = []

        defaults = [
            project.get("remote_root", "") if isinstance(project, dict) else "",
            "/home/jetson",
            "/tmp",
        ]
        seen = set()
        result = []
        for path in bookmarks + defaults:
            path = str(path or "").strip()
            if path and path not in seen:
                seen.add(path)
                result.append(path)
        return result

    def _refresh_remote_path_bookmarks(self):
        if self.remote_path_bookmark_combo is None:
            return
        current = self.remote_path_bookmark_combo.currentText()
        self.remote_path_bookmark_combo.blockSignals(True)
        self.remote_path_bookmark_combo.clear()
        for path in self._remote_path_bookmarks():
            self.remote_path_bookmark_combo.addItem(path)
        self.remote_path_bookmark_combo.blockSignals(False)
        if current:
            self._set_combo_text(self.remote_path_bookmark_combo, current)

    def _persist_active_config_from_forms(self):
        if self.remote_edit is None or self.remote_path_edit is None:
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
            "ssh": self._normalize_remote_text(self.remote_edit.text()),
            "proxy_host": self.ip_combo.currentText().strip() if self.ip_combo is not None else device.get("proxy_host", ""),
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
            "log_target": self.log_tail_target_combo.currentText().strip() if self.log_tail_target_combo is not None else project.get("log_target", ""),
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
        self.terminal_export_display_check.setChecked(
            settings_bool(self.settings.value("terminal/export_display", False), False)
        )
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
        saved_page_key = self.settings.value("window/current_page_key")
        if saved_page_key:
            self._switch_page_by_key(saved_page_key, self._setting_int("window/current_page", 0))
        else:
            self._switch_page(0)
        if self.log_splitter is not None:
            sizes_text = str(self.settings.value("window/log_splitter_sizes", ""))
            try:
                sizes = [int(part) for part in sizes_text.split(",") if part.strip()]
            except ValueError:
                sizes = []
            if len(sizes) == 2 and min(sizes) > 0:
                self.log_splitter.setSizes(sizes)

    def _save_settings(self):
        self.settings.setValue("window/geometry", self.saveGeometry())
        current_page = self.page_stack.currentIndex() if self.page_stack else 0
        self.settings.setValue("window/current_page", current_page)
        if 0 <= current_page < len(self.nav_page_keys):
            self.settings.setValue("window/current_page_key", self.nav_page_keys[current_page])
        if self.log_splitter is not None:
            self.settings.setValue(
                "window/log_splitter_sizes",
                ",".join(str(size) for size in self.log_splitter.sizes()),
            )

        self.settings.setValue("proxy/windows_ip", self.ip_combo.currentText().strip())
        self.settings.setValue("proxy/port", self.port_spin.value())
        self.settings.setValue("proxy/remote_address", self.remote_address_edit.text().strip())
        self.settings.setValue("proxy/clash_program", self.clash_program_edit.text().strip())

        self.settings.setValue("ssh/remote", self._normalize_remote_text(self.remote_edit.text()))
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
        self.settings.setValue("terminal/export_display", self.terminal_export_display_check.isChecked())
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

    def _sync_command_running_state(self):
        short_running = self.command_controller.is_running("short")
        for button in self.command_buttons:
            button.setEnabled(not short_running)
        self.stop_button.setEnabled(self.command_controller.is_running())

    def _run_command(
        self,
        title,
        command,
        cwd=None,
        timeout_seconds=None,
        channel="short",
        done_marker=None,
        stop_on_done_marker=False,
    ):
        if self.command_controller.is_running(channel):
            if channel == "long":
                message = "长时间命令正在运行，请先点击“停止当前命令”。"
            else:
                message = "命令正在运行，请等待当前命令结束，或先点击“停止当前命令”。"
            QMessageBox.warning(self, "命令正在运行", message)
            return

        self._save_settings()
        self._append_log("")
        self._append_log("开始: {} [{}]".format(title, channel))
        self._append_log("+ " + format_command(command))
        self._sync_command_running_state()
        self.current_command_title = title
        self.current_command_output = []
        self.current_command_started = datetime.now()
        self.current_command_timeout_seconds = timeout_seconds
        self.command_timed_out = False

        started = self.command_controller.start(
            channel,
            title,
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            done_marker=done_marker,
            stop_on_done_marker=stop_on_done_marker,
        )
        if not started:
            self._append_log("命令未启动：通道正在运行。")
        self._sync_command_running_state()

    def _handle_command_output(self, channel, line):
        self._append_log(line)

    def _command_timed_out(self, channel):
        self._append_log("命令超时，正在强制停止: {}".format(self.command_controller.title(channel)))

    def _command_failed_to_start(self, channel, error):
        self._append_log("无法启动命令: " + error)
        self._sync_command_running_state()

    def _command_finished(self, channel, return_code, timed_out):
        title = self.command_controller.title(channel) or self.current_command_title or ""
        self.current_command_title = title
        self.current_command_output = self.command_controller.output_lines(channel)
        self.current_command_started = self.command_controller.started_at(channel) or datetime.now()
        if return_code == 0:
            self._append_log("命令完成。")
            self._handle_command_success(title)
        else:
            if timed_out:
                self._append_log("命令已因超时停止，退出码: {}".format(return_code))
            else:
                self._append_log("命令失败，退出码: {}".format(return_code))
            if title == "开发环境检查":
                for section_title in self.environment_result_labels:
                    self._set_environment_result_card(section_title, "error", "失败", "检查失败，请查看底部日志")
                for summary_title in self.environment_summary_label:
                    self._set_environment_summary_card(summary_title, "error", "失败", "检查失败，请查看底部日志")
            elif title == "设备初始化检查" and self.environment_init_text:
                self.environment_init_text.setPlainText("初始化检查失败，请查看底部日志。")
            elif title == "网络连通性诊断":
                self._mark_check_cards_failed(self.network_result_labels, "诊断失败，请查看底部日志")
                if self.network_checks_text:
                    self.network_checks_text.setPlainText("诊断失败，请查看底部日志。")
            elif title == "外设检测":
                self._mark_check_cards_failed(self.peripheral_result_labels, "检测失败，请查看底部日志")
            elif title == "刷新远程进程" and self.process_summary_label:
                self.process_summary_label.setText("刷新进程失败，请查看底部日志。")
            elif title == "列出远程文件" and self.files_summary_label:
                self.files_summary_label.setText("列出远程文件失败，请查看底部日志。")
            elif title.startswith("服务") and self.service_status_text:
                self.service_status_text.setPlainText("服务操作失败，请查看底部日志。")
            self.workflow_queue = []
        self._record_task_history(title, return_code)
        self._sync_command_running_state()
        self.current_command_title = None
        self.current_command_timeout_seconds = None
        self.command_timed_out = False
        if channel == "short" and return_code == 0 and self.workflow_queue:
            self._run_next_workflow_command()

    def _handle_command_success(self, title):
        if title == "测试 SSH":
            self._update_status("ssh", "已连接", self._normalize_remote_text(self.remote_edit.text()))
            self._restart_resource_monitor()
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
        elif title == "开发环境检查":
            data = remote_ops_service.parse_environment_check_output(self.current_command_output)
            self._update_environment_page(data)
        elif title == "设备初始化检查":
            self._update_environment_init_page()
        elif title == "生成诊断报告":
            self._save_diagnostic_report()
        elif title == "网络连通性诊断":
            data = remote_ops_service.parse_network_diagnostics_output(self.current_command_output)
            self._update_network_page(data)
        elif title == "外设检测":
            data = remote_ops_service.parse_peripheral_check_output(self.current_command_output)
            self._update_peripheral_page(data)
        elif title == "刷新远程进程":
            rows = remote_ops_service.parse_process_list_output(self.current_command_output)
            self._update_process_table(rows)
        elif title == "列出远程文件":
            data = remote_ops_service.parse_file_list_output(self.current_command_output)
            self._update_files_table(data)
        elif title.startswith("服务status:"):
            data = remote_ops_service.parse_service_status_output(self.current_command_output)
            self._update_service_status_page(data)
        elif title.startswith("服务start:") or title.startswith("服务stop:") or title.startswith("服务restart:"):
            self._note_service_operation_complete(title)

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
        if self.command_controller.stop():
            self._append_log("已请求停止当前命令。")
            self._sync_command_running_state()

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
        remote = self._normalize_remote_text(self.remote_edit.text())
        if remote and remote != self.remote_edit.text().strip():
            self.remote_edit.setText(remote)
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请在窗口顶部填写远端 SSH，例如 jetson@192.168.55.1。")
            return
        self._top_remote_editing_finished()
        self._run_command(
            "测试 SSH",
            ssh_service.test_ssh_command(remote),
            cwd=self.paths.app_dir,
            timeout_seconds=15,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def _remote_or_warn(self):
        remote = self._normalize_remote_text(self.remote_edit.text()) if self.remote_edit is not None else ""
        if remote and self.remote_edit is not None and remote != self.remote_edit.text().strip():
            self.remote_edit.setText(remote)
        if not remote:
            QMessageBox.warning(self, "缺少 SSH 地址", "请先在窗口顶部填写远端 SSH。")
            return None
        return remote

    def _run_jetson_command(self, title, remote_command, long_running=False):
        remote = self._remote_or_warn()
        if not remote:
            return
        use_done_marker = not long_running
        self._run_command(
            title,
            ssh_service.remote_ssh_command(remote, remote_command, done_marker=use_done_marker),
            cwd=self.paths.app_dir,
            channel="long" if long_running else "short",
            done_marker=ssh_service.DONE_MARKER if use_done_marker else None,
            stop_on_done_marker=use_done_marker,
        )

    def _prompt_ssh_password(self, title):
        remote = self._normalize_remote_text(self.remote_edit.text())
        password, ok = QInputDialog.getText(self, title, "请输入 {} 的 SSH 密码（不会保存）".format(remote), QLineEdit.Password)
        if not ok:
            return None
        return password

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

    def terminal_disconnect(self):
        if self.terminal_worker and self.terminal_worker.isRunning():
            self.terminal_worker.stop()
            self.terminal_worker.wait(2000)
        if self.terminal_status_label:
            self.terminal_status_label.setText("已断开")

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

    def _terminal_disconnected(self):
        if self.terminal_status_label and self.terminal_status_label.text().startswith("已连接"):
            self.terminal_status_label.setText("已断开")

    def refresh_device_health(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        command = ssh_service.remote_ssh_command(remote, device_health_service.health_command(), done_marker=True)
        self._run_command(
            "刷新设备状态",
            command,
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

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
        text = self.health_interval_combo.currentText() if self.health_interval_combo is not None else "5 秒"
        try:
            seconds = int(str(text).split()[0])
        except (TypeError, ValueError, IndexError):
            seconds = 5
        return max(seconds, 1) * 1000

    def _update_health_page(self, data):
        for key, label in self.health_labels.items():
            label.setText(data.get(key) or "未知")

    def _refresh_widget_style(self, widget):
        if not widget:
            return
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_environment_card_state(self, widget, state):
        if not widget:
            return
        widget.setProperty("state", state)
        self._refresh_widget_style(widget)

    def _set_environment_summary_card(self, title, state, value, detail):
        widgets = self.environment_summary_label.get(title) if self.environment_summary_label else None
        if not widgets:
            return
        widgets["value"].setText(value)
        widgets["detail"].setText(detail)
        self._set_environment_card_state(widgets.get("card"), state)

    def _set_environment_result_card(self, title, state, status_text, detail, tooltip=""):
        widgets = self.environment_result_labels.get(title) if self.environment_result_labels else None
        if not widgets:
            return
        widgets["status"].setText(status_text)
        widgets["detail"].setText(detail)
        widgets["detail"].setToolTip(tooltip or detail)
        self._set_environment_card_state(widgets.get("card"), state)
        self._set_environment_card_state(widgets.get("status"), state)

    def _combined_environment_status(self, statuses):
        if not statuses:
            return "unknown"
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        if "ok" in statuses:
            return "ok"
        return "unknown"

    def _prepare_environment_cards(self, message):
        for title in self.environment_result_labels:
            self._set_environment_result_card(title, "pending", "检查中", message)
        for title in self.environment_summary_label:
            self._set_environment_summary_card(title, "pending", "检查中", message)

    def _update_environment_page(self, data):
        items = data.get("items", [])
        by_title = {item.get("title"): item for item in items}
        status_text = remote_ops_service.ENVIRONMENT_STATUS_TEXT

        for item in items:
            title = item.get("title", "")
            self._set_environment_result_card(
                title,
                item.get("status", "unknown"),
                item.get("status_text", status_text.get(item.get("status"), "未检测")),
                item.get("summary", "无输出"),
                item.get("details", ""),
            )

        summary = data.get("summary", {})
        overview_state = "ok"
        if summary.get("error"):
            overview_state = "error"
        elif summary.get("warning"):
            overview_state = "warning"
        elif summary.get("ok"):
            overview_state = "ok"
        else:
            overview_state = "unknown"
        overview_value = "正常 {} / 注意 {} / 异常 {} / 未检测 {}".format(
            summary.get("ok", 0),
            summary.get("warning", 0),
            summary.get("error", 0),
            summary.get("unknown", 0),
        )
        self._set_environment_summary_card(
            "总览",
            overview_state,
            "已完成",
            "{}\n{}".format(overview_value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )

        system_titles = ("OS", "Kernel", "CPU")
        system_status = self._combined_environment_status([
            by_title.get(title, {}).get("status", "unknown") for title in system_titles
        ])
        self._set_environment_summary_card(
            "系统",
            system_status,
            status_text.get(system_status, "未检测"),
            "\n".join(by_title.get(title, {}).get("summary", "无输出").splitlines()[0] for title in system_titles),
        )

        tool_titles = ("Python", "Build tools", "OpenCV Python", "FFmpeg", "Common libraries")
        tool_status = self._combined_environment_status([
            by_title.get(title, {}).get("status", "unknown") for title in tool_titles
        ])
        self._set_environment_summary_card(
            "开发工具",
            tool_status,
            status_text.get(tool_status, "未检测"),
            "Python: {}\n构建/库: {}".format(
                status_text.get(by_title.get("Python", {}).get("status", "unknown"), "未检测"),
                status_text.get(tool_status, "未检测"),
            ),
        )

        accel_titles = ("Jetson", "RK3588 / Rockchip")
        accel_status = self._combined_environment_status([
            by_title.get(title, {}).get("status", "unknown") for title in accel_titles
        ])
        accel_detail = []
        for title in accel_titles:
            item = by_title.get(title, {})
            accel_detail.append("{}: {}".format(title, status_text.get(item.get("status", "unknown"), "未检测")))
        self._set_environment_summary_card(
            "加速能力",
            accel_status,
            status_text.get(accel_status, "未检测"),
            "\n".join(accel_detail),
        )

    def _update_environment_init_page(self):
        if not self.environment_init_text:
            return
        summary = remote_ops_service.parse_device_init_advice_output(self.current_command_output)
        self.environment_init_text.setPlainText(summary)

    def _set_check_card(self, registry, title, state, status_text, detail, tooltip=""):
        widgets = registry.get(title) if registry else None
        if not widgets:
            return
        widgets["status"].setText(status_text)
        widgets["detail"].setText(detail)
        widgets["detail"].setToolTip(tooltip or detail)
        self._set_environment_card_state(widgets.get("card"), state)
        self._set_environment_card_state(widgets.get("status"), state)

    def _prepare_check_cards(self, registry, message):
        for title in registry:
            self._set_check_card(registry, title, "pending", "检查中", message)

    def _mark_check_cards_failed(self, registry, message):
        for title in registry:
            self._set_check_card(registry, title, "error", "失败", message)

    def _update_network_page(self, data):
        status_text = remote_ops_service.CHECK_STATUS_TEXT
        for group in data.get("groups", []):
            self._set_check_card(
                self.network_result_labels,
                group.get("title", ""),
                group.get("status", "unknown"),
                status_text.get(group.get("status", "unknown"), "未检测"),
                group.get("summary", "无输出"),
            )
        if self.network_checks_text:
            checks = data.get("checks", [])
            if checks:
                lines = [
                    "[{}] {}".format(status_text.get(item.get("status"), item.get("status")), item.get("name", ""))
                    for item in checks
                ]
                self.network_checks_text.setPlainText("\n".join(lines))
            else:
                self.network_checks_text.setPlainText("未解析到逐项检查结果，完整输出见底部日志。")

    def _update_peripheral_page(self, data):
        for item in data.get("items", []):
            self._set_check_card(
                self.peripheral_result_labels,
                item.get("title", ""),
                item.get("status", "unknown"),
                item.get("status_text", "未检测"),
                item.get("summary", "无输出"),
                item.get("details", ""),
            )

    def _update_process_table(self, rows):
        if self.process_summary_label:
            self.process_summary_label.setText("共解析到 {} 个进程。".format(len(rows)))
        if self.process_table is None:
            return
        self.process_table.setRowCount(0)
        for row_index, row in enumerate(rows[:120]):
            self.process_table.insertRow(row_index)
            values = [row.get("pid", ""), row.get("cpu", ""), row.get("mem", ""), row.get("elapsed", ""), row.get("command", "")]
            for column, value in enumerate(values):
                self.process_table.setItem(row_index, column, QTableWidgetItem(value))
        self.process_table.resizeColumnsToContents()
        self.process_table.horizontalHeader().setStretchLastSection(True)

    def _update_files_table(self, data):
        rows = data.get("rows", [])
        path = data.get("path") or self.remote_file_path_edit.text().strip()
        if self.files_summary_label:
            self.files_summary_label.setText("{}: {} 项".format(path or "远端路径", len(rows)))
        if self.files_table is None:
            return
        self.files_table.setRowCount(0)
        for row_index, row in enumerate(rows[:300]):
            self.files_table.insertRow(row_index)
            values = [row.get("mode", ""), row.get("size", ""), row.get("modified", ""), row.get("name", "")]
            for column, value in enumerate(values):
                self.files_table.setItem(row_index, column, QTableWidgetItem(value))
        self.files_table.resizeColumnsToContents()
        self.files_table.horizontalHeader().setStretchLastSection(True)

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

    def _update_service_status_page(self, data):
        status = data.get("status", "unknown")
        status_text = data.get("status_text", "未检测")
        self._set_check_card(
            self.service_result_labels,
            "状态",
            status,
            status_text,
            data.get("active", "Active: 未检测"),
            data.get("details", ""),
        )

        loaded = data.get("loaded", "Loaded: 未检测")
        loaded_state = "ok" if "loaded" in loaded.lower() and "not-found" not in loaded.lower() else "unknown"
        self._set_check_card(
            self.service_result_labels,
            "加载",
            loaded_state,
            remote_ops_service.CHECK_STATUS_TEXT.get(loaded_state, "未检测"),
            loaded,
            data.get("details", ""),
        )

        pid = data.get("pid", "Main PID: 未检测")
        pid_state = "ok" if "未检测" not in pid and "n/a" not in pid.lower() else "unknown"
        self._set_check_card(
            self.service_result_labels,
            "进程",
            pid_state,
            remote_ops_service.CHECK_STATUS_TEXT.get(pid_state, "未检测"),
            pid,
            data.get("details", ""),
        )
        if self.service_status_text:
            detail = "\n".join([
                data.get("summary", ""),
                data.get("loaded", ""),
                data.get("active", ""),
                data.get("pid", ""),
            ]).strip()
            self.service_status_text.setPlainText(detail or data.get("details", ""))

    def _note_service_operation_complete(self, title):
        if self.service_status_text:
            self.service_status_text.setPlainText("{} 已完成。\n建议点击“状态”刷新当前服务状态。".format(title))

    def _current_project(self):
        return self._active_context()["project"]

    def _current_device(self):
        return self._active_context()["device"]

    def _remote_command_for_project(self, title, remote_command):
        remote = self._normalize_remote_text(self.remote_edit.text()) or self._current_device().get("ssh")
        return (
            title,
            ssh_service.remote_ssh_command(remote, remote_command, done_marker=True),
            self.paths.app_dir,
            {"done_marker": ssh_service.DONE_MARKER, "stop_on_done_marker": True},
        )

    def _project_sync_step(self):
        project = self._current_project()
        command = ssh_service.sync_command(
            self.paths.sync_script,
            self._normalize_remote_text(self.remote_edit.text()),
            project.get("remote_root", self.remote_path_edit.text().strip()),
            full=self.full_sync_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            no_delete=self.no_delete_check.isChecked(),
        )
        return ("同步到 Jetson", command, self.paths.project_dir)

    def _run_next_workflow_command(self):
        if not self.workflow_queue:
            return
        step = self.workflow_queue.pop(0)
        title, command, cwd = step[:3]
        options = step[3] if len(step) > 3 else {}
        self._run_command(title, command, cwd=cwd, **options)

    def _start_workflow(self, steps):
        if self.command_controller.is_running("short"):
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
        build_command_text = str(project.get("build_command") or self.project_build_command_edit.text()).strip()
        if not build_command_text:
            QMessageBox.warning(self, "缺少构建命令", "请先在项目配置里填写构建命令。")
            return
        command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            build_command_text,
            background=False,
        )
        self._start_workflow([self._remote_command_for_project("项目构建", command)])

    def workflow_run(self):
        project = self._current_project()
        run_command_text = str(project.get("run_command") or self.run_command_edit.text()).strip()
        if not run_command_text:
            QMessageBox.warning(self, "缺少启动命令", "请先在项目配置或运行控制页填写启动命令。")
            return
        command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            run_command_text,
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
        remote = self._normalize_remote_text(self.remote_edit.text()) or self._current_device().get("ssh")
        self._start_workflow([
            (
                "实时查看项目日志",
                ssh_service.remote_ssh_command(remote, remote_ops_service.tail_log_command(target, 120)),
                self.paths.app_dir,
                {"channel": "long"},
            )
        ])

    def workflow_sync_build_run(self):
        if not self.paths.sync_script.exists():
            QMessageBox.critical(self, "找不到脚本", "找不到 {}".format(self.paths.sync_script))
            return
        project = self._current_project()
        build_command_text = str(project.get("build_command") or self.project_build_command_edit.text()).strip()
        run_command_text = str(project.get("run_command") or self.run_command_edit.text()).strip()
        if not build_command_text:
            QMessageBox.warning(self, "缺少构建命令", "请先在项目配置里填写构建命令。")
            return
        if not run_command_text:
            QMessageBox.warning(self, "缺少启动命令", "请先在项目配置或运行控制页填写启动命令。")
            return
        build_command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            build_command_text,
            background=False,
        )
        run_command = remote_ops_service.run_program_command(
            project.get("remote_root", self.remote_path_edit.text().strip()),
            run_command_text,
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
        self._run_jetson_command(
            "运行远程程序",
            remote_script,
            long_running=not self.run_background_check.isChecked(),
        )

    def list_remote_processes(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.process_summary_label:
            self.process_summary_label.setText("正在刷新远端进程...")
        self._run_command(
            "刷新远程进程",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.process_list_command(self.process_filter_edit.text()),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
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
            long_running=True,
        )

    def run_network_diagnostics(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._prepare_check_cards(self.network_result_labels, "正在诊断远端网络")
        if self.network_checks_text:
            self.network_checks_text.setPlainText("正在执行网络诊断...")
        self._run_command(
            "网络连通性诊断",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.network_diagnostics_command(
                    self.network_windows_ip_edit.text(),
                    self.network_proxy_port_edit.text(),
                ),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def run_environment_check(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._prepare_environment_cards("正在检查远端开发环境")
        self._run_command(
            "开发环境检查",
            ssh_service.remote_ssh_command(remote, remote_ops_service.environment_check_command(), done_marker=True),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def run_device_init_advice(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.environment_init_text:
            self.environment_init_text.setPlainText("正在检查远端初始化状态...")
        self._run_command(
            "设备初始化检查",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.device_init_advice_command(
                    self.network_windows_ip_edit.text() if self.network_windows_ip_edit else self.ip_combo.currentText(),
                    self.network_proxy_port_edit.text() if self.network_proxy_port_edit else self.port_spin.value(),
                ),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def run_peripheral_check(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        self._prepare_check_cards(self.peripheral_result_labels, "正在检测远端外设")
        self._run_command(
            "外设检测",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.peripheral_check_command(self.video_device_edit.text()),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def list_remote_files(self):
        remote = self._remote_or_warn()
        if not remote:
            return
        if self.files_summary_label:
            self.files_summary_label.setText("正在列出远端路径...")
        self._run_command(
            "列出远程文件",
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.file_list_command(self.remote_file_path_edit.text()),
                done_marker=True,
            ),
            cwd=self.paths.app_dir,
            done_marker=ssh_service.DONE_MARKER,
            stop_on_done_marker=True,
        )

    def apply_remote_path_bookmark(self):
        if self.remote_path_bookmark_combo is None or self.remote_file_path_edit is None:
            return
        path = self.remote_path_bookmark_combo.currentText().strip()
        if path:
            self.remote_file_path_edit.setText(path)

    def save_remote_path_bookmark(self):
        if not self.remote_file_path_edit:
            return
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请先填写要收藏的远端路径。")
            return
        reason = remote_ops_service.remote_path_refusal_reason(remote_path)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", "拒绝收藏该路径。\n\n{}\n{}".format(remote_path, reason))
            return
        project = self._current_project()
        if not project.get("id"):
            QMessageBox.warning(self, "缺少项目", "请先选择或保存一个项目。")
            return
        bookmarks = self._remote_path_bookmarks()
        if remote_path not in bookmarks:
            bookmarks.insert(0, remote_path)
        project_payload = dict(project)
        project_payload["file_bookmarks"] = bookmarks[:20]
        self.config_store.upsert_project(project_payload)
        self._refresh_remote_path_bookmarks()
        self._set_combo_text(self.remote_path_bookmark_combo, remote_path)
        self._append_log("已保存远端路径收藏: " + remote_path)

    def delete_remote_path_bookmark(self):
        if self.remote_path_bookmark_combo is None:
            return
        remote_path = self.remote_path_bookmark_combo.currentText().strip()
        if not remote_path:
            return
        project = self._current_project()
        explicit = [str(path).strip() for path in project.get("file_bookmarks", []) if str(path).strip()]
        if remote_path not in explicit:
            QMessageBox.information(self, "默认路径", "该路径来自项目默认值，不需要删除。")
            return
        bookmarks = [
            path for path in explicit
            if path != remote_path
        ]
        project_payload = dict(project)
        project_payload["file_bookmarks"] = bookmarks
        self.config_store.upsert_project(project_payload)
        self._refresh_remote_path_bookmarks()
        self._append_log("已删除远端路径收藏: " + remote_path)

    def mkdir_remote_path(self):
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要创建的远端目录。")
            return
        reason = remote_ops_service.remote_path_refusal_reason(remote_path)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", "拒绝创建该路径。\n\n{}\n{}".format(remote_path, reason))
            return
        self._run_jetson_command("新建远程目录", remote_ops_service.mkdir_command(remote_path))

    def remove_remote_path(self):
        remote_path = self.remote_file_path_edit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, "缺少远端路径", "请填写要删除的远端路径。")
            return
        reason = remote_ops_service.remote_path_refusal_reason(remote_path, destructive=True)
        if reason:
            QMessageBox.warning(self, "远端路径不安全", "拒绝删除该路径。\n\n{}\n{}".format(remote_path, reason))
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
        remote = self._remote_or_warn()
        if not remote:
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
        if action == "status":
            self._prepare_check_cards(self.service_result_labels, "正在查询服务状态")
            if self.service_status_text:
                self.service_status_text.setPlainText("正在查询服务状态...")
        elif action in ("start", "stop", "restart") and self.service_status_text:
            self.service_status_text.setPlainText("正在执行服务操作: {}".format(action))
        self._run_command(
            "服务{}: {}".format(action, service_name),
            ssh_service.remote_ssh_command(
                remote,
                remote_ops_service.service_command(service_name, action),
                done_marker=action != "logs",
            ),
            cwd=self.paths.app_dir,
            channel="long" if action == "logs" else "short",
            done_marker=ssh_service.DONE_MARKER if action != "logs" else None,
            stop_on_done_marker=action != "logs",
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

    def _set_model_scan_running(self, running):
        if self.model_choose_source_button is not None:
            self.model_choose_source_button.setText("取消" if running else "选择")
            self.model_choose_source_button.setEnabled(True)

    def _start_model_scan(self, password=None):
        remote = self._remote_or_warn()
        if not remote:
            return
        workdir = self.model_workdir_edit.text().strip() if self.model_workdir_edit else ""
        workdir = workdir or "."
        self.pending_model_scan_password = None
        self.model_scan_worker = RemoteModelScanWorker(
            remote,
            workdir,
            password=password if password is not None else (self.sftp_password or self.terminal_password),
            timeout_seconds=20,
            parent=self,
        )
        self.model_scan_worker.message.connect(self._model_scan_message)
        self.model_scan_worker.candidates_ready.connect(self._model_scan_candidates_ready)
        self.model_scan_worker.auth_failed.connect(self._model_scan_auth_failed)
        self.model_scan_worker.failed.connect(self._model_scan_failed)
        self.model_scan_worker.finished.connect(self._model_scan_finished)
        self._set_model_scan_running(True)
        self._append_log("开始扫描远端模型文件: " + workdir)
        self.model_scan_worker.start()

    def choose_model_source_file(self):
        if self.model_scan_worker and self.model_scan_worker.isRunning():
            self.model_scan_worker.cancel()
            self._append_log("已请求取消模型文件扫描。")
            return
        self._start_model_scan()

    def _model_scan_message(self, message):
        self._append_log(message)

    def _model_scan_auth_failed(self, error):
        worker = self.model_scan_worker
        if worker and worker.password:
            QMessageBox.warning(self, "选择模型失败", error)
            return
        password = self._prompt_ssh_password("SFTP 认证")
        if password is None:
            self._append_log("模型文件扫描认证已取消。")
            return
        self.sftp_password = password
        self.pending_model_scan_password = password

    def _model_scan_failed(self, error):
        QMessageBox.warning(self, "选择模型失败", str(error))

    def _model_scan_candidates_ready(self, candidates):
        if not candidates:
            QMessageBox.information(
                self,
                "未找到模型文件",
                "在远程目录 {} 下未找到 .onnx、.engine、.rknn、.pt、.pth 或 .tflite 文件。".format(
                    self.model_workdir_edit.text().strip() or "."
                ),
            )
            return
        selected, ok = QInputDialog.getItem(
            self,
            "选择输入模型",
            "远端模型文件",
            candidates,
            0,
            False,
        )
        if ok and selected:
            self.model_source_edit.setText(selected)
            self._append_log("已选择输入模型: " + selected)

    def _model_scan_finished(self):
        self.model_scan_worker = None
        if self.pending_model_scan_password is not None:
            password = self.pending_model_scan_password
            self.pending_model_scan_password = None
            self._start_model_scan(password=password)
            return
        self._set_model_scan_running(False)

    def run_tensorrt_conversion(self):
        self._run_jetson_command("TensorRT 模型转换", self._current_tensorrt_command())

    def run_model_benchmark(self):
        output = self.model_output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "缺少模型输出文件", "请先填写 engine 或 rknn 输出文件。")
            return
        if output.lower().endswith(".rknn"):
            command = remote_ops_service.rknn_benchmark_template_command(
                self.model_workdir_edit.text(),
                output,
                self.model_test_image_edit.text(),
            )
            self._run_jetson_command("RKNN 运行模板", command)
            return
        command = remote_ops_service.tensorrt_benchmark_command(
            self.model_workdir_edit.text(),
            output,
        )
        self._run_jetson_command("TensorRT Benchmark", command)

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

    def _current_model_profile_id(self):
        return self._combo_current_data(self.model_profile_combo)

    def _model_profile_from_form(self):
        name = self.model_name_edit.text().strip() if self.model_name_edit else "Model"
        profile_id = self._current_model_profile_id() or slugify(name, "model")
        return {
            "id": profile_id,
            "name": name,
            "source": self.model_source_edit.text().strip(),
            "output": self.model_output_edit.text().strip(),
            "precision": self.model_precision_combo.currentText().strip(),
            "test_image": self.model_test_image_edit.text().strip(),
        }

    def save_model_profile(self):
        project = self._current_project()
        if not project.get("id"):
            QMessageBox.warning(self, "缺少项目", "请先选择或保存一个项目。")
            return
        profile = self._model_profile_from_form()
        if not profile["name"]:
            QMessageBox.warning(self, "缺少模型名称", "请填写模型名称。")
            return
        profile_id = self.config_store.upsert_model_profile(project["id"], profile)
        self._refresh_config_selectors()
        self._apply_active_context_to_forms()
        self._set_combo_by_data(self.model_profile_combo, profile_id)
        self._append_log("已保存模型配置: " + profile["name"])

    def load_model_profile(self):
        project = self._current_project()
        profile_id = self._current_model_profile_id()
        profile = None
        for item in project.get("model_profiles", []):
            if item.get("id") == profile_id:
                profile = item
                break
        if not profile:
            QMessageBox.warning(self, "找不到模型配置", "请选择要加载的模型配置。")
            return
        self.model_name_edit.setText(profile.get("name", ""))
        self.model_source_edit.setText(profile.get("source", ""))
        self.model_output_edit.setText(profile.get("output", ""))
        self.model_test_image_edit.setText(profile.get("test_image", ""))
        self._set_combo_text(self.model_precision_combo, profile.get("precision", "fp16"))

    def delete_model_profile(self):
        project = self._current_project()
        profile_id = self._current_model_profile_id()
        if not project.get("id") or not profile_id:
            return
        answer = QMessageBox.question(
            self,
            "确认删除模型配置",
            "确定删除当前模型配置？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config_store.delete_model_profile(project["id"], profile_id)
        self._apply_active_context_to_forms()
        self._append_log("已删除模型配置。")

    def _refresh_device_profile_combo(self):
        if self.device_profile_combo is None:
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
        self.device_remote_edit.setText(self._normalize_remote_text(self.remote_edit.text()))
        self.device_remote_path_edit.setText(self.remote_path_edit.text().strip())
        self.device_local_root_edit.setText(self.local_root_edit.text().strip())
        name = self._normalize_remote_text(self.remote_edit.text()).split("@")[-1] or "设备"
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
        remote = self._normalize_remote_text(self.remote_edit.text())
        safe_remote = remote.replace("@", "_").replace(":", "_").replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = report_dir / "diagnostic-{}-{}.md".format(safe_remote or "device", timestamp)
        body = "\n".join(self.current_command_output)
        header = [
            "# Jetson Tool Panel 诊断报告",
            "",
            "- Remote: {}".format(remote),
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
        output = self.display_output_combo.currentText().strip() if self.display_output_combo is not None else "auto"
        mode = self.resolution_combo.currentText().strip() if self.resolution_combo is not None else "1920x1080"
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
        output = self.display_output_combo.currentText().strip() if self.display_output_combo is not None else "auto"
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

    def closeEvent(self, event):
        if self.command_controller.is_running():
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
            self.command_controller.stop()
        if self.sftp_worker and self.sftp_worker.isRunning():
            answer = QMessageBox.question(
                self,
                "SFTP 仍在运行",
                "当前文件传输仍在运行，是否取消并退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.sftp_worker.cancel()
            self.sftp_worker.wait(3000)
        if self.terminal_worker and self.terminal_worker.isRunning():
            self.terminal_worker.stop()
            self.terminal_worker.wait(2000)
        if self.model_scan_worker and self.model_scan_worker.isRunning():
            self.model_scan_worker.cancel()
            self.model_scan_worker.wait(2000)
        self._stop_resource_monitor()
        self._save_settings()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = JetsonControlPanel()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
