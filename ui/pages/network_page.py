from PyQt5.QtWidgets import QGridLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_check_card, build_note, build_panel


def build_network_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.network_result_labels = {}
    window.network_checks_text = None

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.network_windows_ip_edit = QLineEdit(window.ip_combo.currentText())
    window.network_proxy_port_edit = QLineEdit(str(window.port_spin.value()))
    window._bind_line_edits(window.ip_combo.lineEdit(), window.network_windows_ip_edit)
    window.port_spin.valueChanged.connect(lambda value: window.network_proxy_port_edit.setText(str(value)))

    button = QPushButton("开始网络诊断")
    button.setObjectName("PrimaryButton")
    button.clicked.connect(window.run_network_diagnostics)
    window.command_buttons.append(button)

    grid.addWidget(QLabel("Windows IP"), 0, 0)
    grid.addWidget(window.network_windows_ip_edit, 0, 1)
    grid.addWidget(QLabel("代理端口"), 1, 0)
    grid.addWidget(window.network_proxy_port_edit, 1, 1)
    grid.addWidget(button, 2, 1)
    grid.setColumnStretch(1, 1)

    layout.addWidget(build_panel("网络连通性诊断", grid))

    result_grid = QGridLayout()
    result_grid.setHorizontalSpacing(10)
    result_grid.setVerticalSpacing(10)
    for index, title in enumerate(["远端地址", "公网连通", "DNS / GitHub", "Windows 代理", "pip / apt"]):
        result_grid.addWidget(build_check_card(window.network_result_labels, title), index // 3, index % 3)
    result_grid.setColumnStretch(0, 1)
    result_grid.setColumnStretch(1, 1)
    result_grid.setColumnStretch(2, 1)
    layout.addWidget(build_panel("诊断结果", result_grid))

    checks_layout = QVBoxLayout()
    window.network_checks_text = QPlainTextEdit()
    window.network_checks_text.setObjectName("ReferenceText")
    window.network_checks_text.setReadOnly(True)
    window.network_checks_text.setMaximumHeight(110)
    window.network_checks_text.setPlainText("点击“开始网络诊断”后显示逐项连通性检查。")
    checks_layout.addWidget(window.network_checks_text)
    layout.addWidget(build_panel("逐项检查", checks_layout))

    layout.addWidget(build_note("会检查远端 IP、路由、DNS、GitHub、pip/apt 配置，以及远端是否能访问 Windows 代理端口。"))
    layout.addStretch(1)
    return page
