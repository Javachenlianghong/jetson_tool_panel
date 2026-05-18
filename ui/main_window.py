#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main window for Jetson Tool Panel."""

import os
import socket
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
from core.config_store import ProjectConfigStore
from core.paths import DEFAULTS, PATHS
from core.resource_monitor import ResourceMonitorWorker
from core.settings import settings_bool
from core.sync_preview import parse_sync_preview_output
from core.task_history import TaskHistoryStore
from core.terminal_filter import PlainTerminalBuffer
from services import device_health_service, proxy_service, remote_ops_service, ssh_service
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
from ui.controllers.model_controller import ModelControllerMixin
from ui.controllers.proxy_sync_controller import ProxySyncControllerMixin
from ui.controllers.report_display_controller import ReportDisplayControllerMixin
from ui.controllers.sftp_controller import SftpControllerMixin
from ui.controllers.terminal_controller import TerminalControllerMixin
from ui.controllers.workflow_controller import WorkflowControllerMixin


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


class JetsonControlPanel(
    ModelControllerMixin,
    TerminalControllerMixin,
    SftpControllerMixin,
    WorkflowControllerMixin,
    ReportDisplayControllerMixin,
    ProxySyncControllerMixin,
    QMainWindow,
):
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
        self.sync_preview_table = None
        self.sync_preview_summary_label = None
        self.last_sync_preview = None
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
        self.terminal_quick_command_combo = None
        self.terminal_buffer = PlainTerminalBuffer()
        self.terminal_worker = None
        self.terminal_password = None
        self.health_refresh_button = None
        self.health_auto_check = None
        self.health_interval_combo = None
        self.workbench_labels = {}
        self.task_history_text = None
        self.task_center_table = None
        self.task_center_summary_label = None
        self.run_workdir_edit = None
        self.run_command_edit = None
        self.run_background_check = None
        self.runtime_result_text = None
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
        self.model_status_label = None
        self.model_result_text = None
        self.model_scan_worker = None
        self.pending_model_scan_password = None
        self.device_profile_combo = None
        self.device_name_edit = None
        self.device_remote_edit = None
        self.device_remote_path_edit = None
        self.device_local_root_edit = None
        self.device_overview_table = None
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
        self.monitor_history_label = None
        self.monitor_history = []
        self.resource_monitor_worker = None
        self.resource_monitor_remote = None
        self.resource_monitor_last_status = "未连接"
        self.resource_monitor_reconnects = 0
        self.resource_monitor_auto_reconnect = True
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
        self._refresh_task_center()
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

        self.monitor_history_label = QLabel("趋势 --")
        self.monitor_history_label.setObjectName("MonitorStatus")
        self.monitor_history_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.monitor_history_label)
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
        self.resource_monitor_reconnects = 0
        sample = dict(metrics)
        sample["time"] = datetime.now()
        self.monitor_history.append(sample)
        cutoff = datetime.now().timestamp() - 300
        self.monitor_history = [
            item for item in self.monitor_history[-180:]
            if item.get("time", datetime.now()).timestamp() >= cutoff
        ]
        for key in ("cpu", "memory", "gpu", "temperature"):
            label = self.monitor_labels.get(key)
            if label is not None:
                label.setText(str(metrics.get(key) or "未知"))
        raw = str(metrics.get("raw") or "")
        for label in self.monitor_labels.values():
            label.setToolTip(raw)
        if self.monitor_status_label is not None:
            status = "监控中: {}".format(self.resource_monitor_remote or self._normalize_remote_text(self.remote_edit.text()))
            self.resource_monitor_last_status = status
            self.monitor_status_label.setText(status)
            self.monitor_status_label.setToolTip(raw)
        if self.monitor_history_label is not None:
            self.monitor_history_label.setText(self._monitor_history_summary())
        self._refresh_task_center()

    def _set_resource_monitor_status(self, status):
        self.resource_monitor_last_status = str(status or "未知")
        if self.monitor_status_label is not None:
            self.monitor_status_label.setText(self.resource_monitor_last_status)
        if (
            self.resource_monitor_auto_reconnect
            and self.resource_monitor_remote
            and "监控已停止" in self.resource_monitor_last_status
            and self.resource_monitor_reconnects < 3
        ):
            self.resource_monitor_reconnects += 1
            delay_ms = 3000 * self.resource_monitor_reconnects
            if self.monitor_status_label is not None:
                self.monitor_status_label.setText("监控已停止，{} 秒后重连".format(delay_ms // 1000))
            QTimer.singleShot(delay_ms, self._restart_resource_monitor)
        self._refresh_task_center()

    def _monitor_history_summary(self):
        if not self.monitor_history:
            return "趋势 --"
        latest = self.monitor_history[-1]
        temps = []
        for item in self.monitor_history:
            text = str(item.get("temperature") or "")
            numbers = []
            current = ""
            for char in text:
                if char.isdigit() or char == ".":
                    current += char
                elif current:
                    numbers.append(current)
                    current = ""
            if current:
                numbers.append(current)
            for number in numbers:
                try:
                    temps.append(float(number))
                except ValueError:
                    pass
        temp_text = "最高温 {:.1f}C".format(max(temps)) if temps else "最高温未知"
        return "趋势 {} 样本，CPU {}，{}".format(
            len(self.monitor_history),
            latest.get("cpu", "未知"),
            temp_text,
        )

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
        self._refresh_task_center()

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
        if hasattr(self, "refresh_device_overview"):
            self.refresh_device_overview()

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
        self._refresh_task_center()

    def _elapsed_text(self, started):
        if not started:
            return "-"
        seconds = max(0, int((datetime.now() - started).total_seconds()))
        minutes, second = divmod(seconds, 60)
        hour, minute = divmod(minutes, 60)
        if hour:
            return "{}:{:02d}:{:02d}".format(hour, minute, second)
        return "{:02d}:{:02d}".format(minute, second)

    def _command_task_row(self, channel):
        state = self.command_controller.state(channel)
        label = "短命令" if channel == "short" else "长命令"
        if not state:
            return [label, "空闲", "-", "-", "可启动"]
        status = "超时停止中" if state.timed_out else "运行中"
        detail = "cwd: {}".format(state.cwd or self.paths.app_dir)
        return [label, status, state.title, self._elapsed_text(state.started_at), detail]

    def _worker_row(self, label, worker, title, detail):
        if worker and worker.isRunning():
            return [label, "运行中", title, "-", detail]
        return [label, "空闲", "-", "-", detail or "可启动"]

    def _refresh_task_center(self):
        table = self.task_center_table
        if table is None:
            return
        sftp_title = "-"
        sftp_detail = "可启动"
        if self.sftp_worker and self.sftp_worker.isRunning():
            sftp_title = getattr(self.sftp_worker, "action", "SFTP")
            sftp_detail = str(getattr(self.sftp_worker, "payload", {}) or {})
        model_title = "模型文件扫描" if self.model_scan_worker and self.model_scan_worker.isRunning() else "-"
        model_detail = self.model_workdir_edit.text().strip() if self.model_workdir_edit else "可启动"
        terminal_title = self.terminal_status_label.text() if self.terminal_status_label else "-"
        monitor_running = self.resource_monitor_worker and self.resource_monitor_worker.isRunning()
        rows = [
            self._command_task_row("short"),
            self._command_task_row("long"),
            self._worker_row("SFTP", self.sftp_worker, sftp_title, sftp_detail),
            self._worker_row("模型扫描", self.model_scan_worker, model_title, model_detail),
            self._worker_row(
                "SSH 终端",
                self.terminal_worker,
                terminal_title,
                self._normalize_remote_text(self.remote_edit.text()) if self.remote_edit else "",
            ),
            [
                "资源监控",
                "运行中" if monitor_running else "停止",
                self.resource_monitor_remote or "-",
                "-",
                self.resource_monitor_last_status,
            ],
        ]
        table.setRowCount(0)
        running = 0
        for row_index, row in enumerate(rows):
            if row[1] in ("运行中", "超时停止中"):
                running += 1
            table.insertRow(row_index)
            for column, value in enumerate(row):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        if self.task_center_summary_label:
            self.task_center_summary_label.setText("运行中任务: {} / {}".format(running, len(rows)))

    def stop_short_command(self):
        if self.command_controller.stop("short"):
            self._append_log("已请求停止短命令。")
        self._sync_command_running_state()

    def stop_long_command(self):
        if self.command_controller.stop("long"):
            self._append_log("已请求停止长命令。")
        self._sync_command_running_state()

    def cancel_sftp_task(self):
        if self.sftp_worker and self.sftp_worker.isRunning():
            self.sftp_cancel_transfer()
        self._refresh_task_center()

    def cancel_model_scan_task(self):
        if self.model_scan_worker and self.model_scan_worker.isRunning():
            self.model_scan_worker.cancel()
            self._append_log("已请求取消模型扫描。")
        self._refresh_task_center()

    def reconnect_resource_monitor(self):
        self._append_log("正在重连资源监控。")
        self._restart_resource_monitor()

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
        self._refresh_task_center()

    def _command_timed_out(self, channel):
        self._append_log("命令超时，正在强制停止: {}".format(self.command_controller.title(channel)))
        self._refresh_task_center()

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
            self._show_command_diagnostics(title)
            self.workflow_queue = []
        self._record_task_history(title, return_code)
        self._sync_command_running_state()
        self.current_command_title = None
        self.current_command_timeout_seconds = None
        self.command_timed_out = False
        if channel == "short" and return_code == 0 and self.workflow_queue:
            self._run_next_workflow_command()
        self._refresh_task_center()

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
        elif title in ("运行远程程序", "项目后台运行"):
            self._update_runtime_result(title, remote_ops_service.parse_runtime_output(self.current_command_output))
        elif title == "预览同步变更":
            self._update_sync_preview(parse_sync_preview_output(self.current_command_output))
        if hasattr(self, "handle_model_command_success"):
            self.handle_model_command_success(title)

    def _update_runtime_result(self, title, result):
        if self.runtime_result_text is None:
            return
        lines = [title, "", result.get("summary", "")]
        metrics = result.get("metrics") or {}
        if metrics:
            lines.append("")
            lines.append("指标")
            for key, value in metrics.items():
                lines.append("- {}: {}".format(key, value))
        hints = result.get("hints") or []
        if hints:
            lines.append("")
            lines.append("建议")
            lines.extend("- " + hint for hint in hints)
        details = result.get("details") or ""
        if details:
            lines.append("")
            lines.append("日志尾部")
            lines.extend(details.splitlines()[-30:])
        self.runtime_result_text.setPlainText("\n".join(lines))

    def _show_command_diagnostics(self, title):
        hints = remote_ops_service.diagnose_command_output(self.current_command_output)
        if not hints:
            return
        self._append_log("诊断建议:")
        for hint in hints:
            self._append_log("- " + hint)
        if title in ("运行远程程序", "项目后台运行", "TensorRT 模型转换", "TensorRT Benchmark"):
            self._update_runtime_result(title, {
                "summary": "命令失败，已生成诊断建议。",
                "metrics": {},
                "hints": hints,
                "details": "\n".join(self.current_command_output),
            })

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
        self._refresh_task_center()

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
