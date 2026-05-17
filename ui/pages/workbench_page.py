from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

from ui.pages.common import build_note, build_panel


def build_workbench_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.workbench_labels = {}

    summary_grid = QGridLayout()
    summary_grid.setHorizontalSpacing(12)
    summary_grid.setVerticalSpacing(10)
    _add_field(window, summary_grid, "设备", "device", 0, 0)
    _add_field(window, summary_grid, "SSH", "ssh", 0, 2)
    _add_field(window, summary_grid, "项目", "project", 1, 0)
    _add_field(window, summary_grid, "远端路径", "remote_root", 1, 2)
    _add_field(window, summary_grid, "本地路径", "local_root", 2, 0, col_span=3)
    summary_grid.setColumnStretch(1, 1)
    summary_grid.setColumnStretch(3, 1)
    layout.addWidget(build_panel("当前工作上下文", summary_grid))

    action_layout = QHBoxLayout()
    for text, handler, primary in [
        ("同步", window.workflow_sync, True),
        ("构建", window.workflow_build, True),
        ("运行", window.workflow_run, True),
        ("停止", window.workflow_stop, False),
        ("日志", window.workflow_logs, False),
        ("一键同步构建运行", window.workflow_sync_build_run, True),
        ("诊断报告", window.generate_diagnostic_report, False),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        window.command_buttons.append(button)
        action_layout.addWidget(button)
    action_layout.addStretch(1)
    layout.addWidget(build_panel("开发工作流", action_layout))

    history_layout = QVBoxLayout()
    window.task_history_text = QLabel("暂无任务历史")
    window.task_history_text.setObjectName("MutedText")
    window.task_history_text.setWordWrap(True)
    window.task_history_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    history_layout.addWidget(window.task_history_text)
    layout.addWidget(build_panel("最近任务", history_layout))

    layout.addWidget(build_note("工作台命令使用顶部选中的设备和项目配置。长时间运行的日志 tail 可用底部“停止当前命令”结束。"))
    layout.addStretch(1)
    return page


def _add_field(window, layout, title, key, row, column, col_span=1):
    title_label = QLabel(title)
    title_label.setObjectName("MutedText")
    value_label = QLabel("-")
    value_label.setObjectName("PanelLead")
    value_label.setWordWrap(True)
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    window.workbench_labels[key] = value_label
    layout.addWidget(title_label, row, column)
    layout.addWidget(value_label, row, column + 1, 1, col_span)
