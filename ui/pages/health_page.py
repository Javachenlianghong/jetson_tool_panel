from PyQt5.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

from ui.pages.common import build_note, build_panel


def build_health_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.health_labels = {}

    control_layout = QHBoxLayout()
    refresh_button = QPushButton("刷新状态")
    refresh_button.setObjectName("PrimaryButton")
    refresh_button.clicked.connect(window.refresh_device_health)
    window.command_buttons.append(refresh_button)
    window.health_refresh_button = refresh_button

    auto_check = QCheckBox("自动刷新")
    auto_check.toggled.connect(window._toggle_health_auto_refresh)
    window.health_auto_check = auto_check

    interval_combo = QComboBox()
    interval_combo.addItems(["5 秒", "10 秒", "30 秒"])
    interval_combo.currentTextChanged.connect(window._health_interval_changed)
    window.health_interval_combo = interval_combo

    control_layout.addWidget(refresh_button)
    control_layout.addSpacing(8)
    control_layout.addWidget(auto_check)
    control_layout.addWidget(QLabel("间隔"))
    control_layout.addWidget(interval_combo)
    control_layout.addStretch(1)
    layout.addWidget(build_panel("设备状态刷新", control_layout))

    summary_grid = QGridLayout()
    summary_grid.setHorizontalSpacing(12)
    summary_grid.setVerticalSpacing(10)
    _add_field(window, summary_grid, "设备类型", "device_type", 0, 0)
    _add_field(window, summary_grid, "主机名", "hostname", 0, 2)
    _add_field(window, summary_grid, "内核", "kernel", 1, 0)
    _add_field(window, summary_grid, "架构", "arch", 1, 2)
    _add_field(window, summary_grid, "运行时间", "uptime", 2, 0)
    _add_field(window, summary_grid, "设备详情", "device_detail", 2, 2)
    summary_grid.setColumnStretch(1, 1)
    summary_grid.setColumnStretch(3, 1)
    layout.addWidget(build_panel("设备摘要", summary_grid))

    metric_grid = QGridLayout()
    metric_grid.setHorizontalSpacing(12)
    metric_grid.setVerticalSpacing(12)
    metric_grid.addWidget(_metric_card(window, "CPU", "cpu"), 0, 0)
    metric_grid.addWidget(_metric_card(window, "内存", "memory"), 0, 1)
    metric_grid.addWidget(_metric_card(window, "磁盘 /", "disk"), 0, 2)
    metric_grid.addWidget(_metric_card(window, "温度", "temperature"), 1, 0)
    metric_grid.addWidget(_metric_card(window, "网络 IP", "network"), 1, 1)
    metric_grid.addWidget(_metric_card(window, "负载", "load"), 1, 2)
    metric_grid.setColumnStretch(0, 1)
    metric_grid.setColumnStretch(1, 1)
    metric_grid.setColumnStretch(2, 1)
    layout.addWidget(build_panel("运行指标", metric_grid))

    detail_grid = QGridLayout()
    detail_grid.setHorizontalSpacing(12)
    detail_grid.setVerticalSpacing(10)
    _add_field(window, detail_grid, "加速器", "accelerator", 0, 0)
    _add_field(window, detail_grid, "tegrastats", "tegrastats", 1, 0, col_span=3)
    detail_grid.setColumnStretch(1, 1)
    layout.addWidget(build_panel("设备能力", detail_grid))

    layout.addWidget(build_note("设备状态采集只通过 SSH 执行只读命令；缺少某些系统工具时，对应字段会显示“未知”。"))
    layout.addStretch(1)
    return page


def _add_field(window, layout, title, key, row, column, col_span=1):
    title_label = QLabel(title)
    title_label.setObjectName("MutedText")
    value_label = QLabel("未知")
    value_label.setObjectName("PanelLead")
    value_label.setWordWrap(True)
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    window.health_labels[key] = value_label
    layout.addWidget(title_label, row, column)
    layout.addWidget(value_label, row, column + 1, 1, col_span)


def _metric_card(window, title, key):
    box = QWidget()
    box.setObjectName("MetricBox")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("MutedText")
    value_label = QLabel("未知")
    value_label.setObjectName("MetricValue")
    value_label.setWordWrap(True)
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    window.health_labels[key] = value_label
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    return box
