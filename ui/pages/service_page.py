from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_check_card, build_note, build_panel


def build_service_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.service_result_labels = {}
    window.service_status_text = None

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.service_name_edit = QLineEdit("your-service.service")
    grid.addWidget(QLabel("服务名"), 0, 0)
    grid.addWidget(window.service_name_edit, 0, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("状态", window.service_status, True),
        ("启动", window.service_start, False),
        ("停止", window.service_stop, False),
        ("重启", window.service_restart, False),
        ("实时日志", window.service_logs, True),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 1, 0, 1, 2)

    layout.addWidget(build_panel("systemd 服务管理", grid))

    result_grid = QGridLayout()
    result_grid.setHorizontalSpacing(10)
    result_grid.setVerticalSpacing(10)
    for index, title in enumerate(["状态", "加载", "进程"]):
        result_grid.addWidget(build_check_card(window.service_result_labels, title), 0, index)
    result_grid.setColumnStretch(0, 1)
    result_grid.setColumnStretch(1, 1)
    result_grid.setColumnStretch(2, 1)
    layout.addWidget(build_panel("服务状态摘要", result_grid))

    detail_layout = QVBoxLayout()
    window.service_status_text = QPlainTextEdit()
    window.service_status_text.setObjectName("ReferenceText")
    window.service_status_text.setReadOnly(True)
    window.service_status_text.setMaximumHeight(150)
    window.service_status_text.setPlainText("点击“状态”后显示 systemd 摘要。")
    detail_layout.addWidget(window.service_status_text)
    layout.addWidget(build_panel("状态详情", detail_layout), 1)

    layout.addWidget(build_note("启动、停止、重启会优先尝试 sudo -n systemctl；如果远端没有免密 sudo，会退回 systemctl --user 或在日志中显示失败。"))
    layout.addStretch(1)
    return page
