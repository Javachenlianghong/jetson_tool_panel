from PyQt5.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.vnc_client import VncDisplayWidget
from ui.pages.common import build_note


def build_remote_desktop_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    grid = QGridLayout()
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(8)
    window.remote_desktop_display_edit = QLineEdit(":0")
    window.remote_desktop_display_edit.setMaximumWidth(92)
    window.remote_desktop_xauthority_edit = QLineEdit("/home/jetson/.Xauthority")
    window.remote_desktop_port_spin = QSpinBox()
    window.remote_desktop_port_spin.setRange(5900, 5999)
    window.remote_desktop_port_spin.setValue(5900)
    window.remote_desktop_port_spin.setMaximumWidth(92)
    window.remote_desktop_performance_combo = QComboBox()
    window.remote_desktop_performance_combo.addItems(["平衡 (75%)", "高清 (85%)", "流畅 (50%)", "清晰 (100%)"])
    window.remote_desktop_performance_combo.setMaximumWidth(130)
    window.remote_desktop_status_label = QLabel("未连接")
    window.remote_desktop_status_label.setObjectName("MutedText")

    grid.addWidget(QLabel("DISPLAY"), 0, 0)
    grid.addWidget(window.remote_desktop_display_edit, 0, 1)
    grid.addWidget(QLabel("XAUTHORITY"), 0, 2)
    grid.addWidget(window.remote_desktop_xauthority_edit, 0, 3)
    grid.addWidget(QLabel("VNC 端口"), 0, 4)
    grid.addWidget(window.remote_desktop_port_spin, 0, 5)
    grid.addWidget(QLabel("性能模式"), 1, 0)
    grid.addWidget(window.remote_desktop_performance_combo, 1, 1)
    grid.addWidget(QLabel("状态"), 1, 2)
    grid.addWidget(window.remote_desktop_status_label, 1, 3, 1, 3)
    grid.setColumnStretch(3, 1)

    buttons = QHBoxLayout()
    buttons.setSpacing(6)
    for text, handler, primary in [
        ("安装 x11vnc", window.install_remote_desktop_service, False),
        ("终端安装 x11vnc", window.install_remote_desktop_service_in_terminal, False),
        ("启动并连接", window.start_and_connect_remote_desktop, True),
        ("仅连接", window.connect_remote_desktop, True),
        ("查询服务", window.query_remote_desktop_service, False),
        ("断开", window.disconnect_remote_desktop, False),
        ("停止服务", window.stop_remote_desktop_service, False),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 2, 0, 1, 6)
    controls_panel = QFrame()
    controls_panel.setObjectName("Panel")
    controls_layout = QVBoxLayout(controls_panel)
    controls_layout.setContentsMargins(12, 10, 12, 10)
    controls_layout.setSpacing(8)
    controls_title = QLabel("Jetson 远程桌面")
    controls_title.setObjectName("PanelTitle")
    controls_layout.addWidget(controls_title)
    controls_layout.addLayout(grid)
    layout.addWidget(controls_panel, 0)

    window.remote_desktop_view = VncDisplayWidget()
    desktop_panel = QFrame()
    desktop_panel.setObjectName("Panel")
    desktop_layout = QVBoxLayout(desktop_panel)
    desktop_layout.setContentsMargins(8, 8, 8, 8)
    desktop_layout.setSpacing(8)
    desktop_header = QHBoxLayout()
    desktop_title = QLabel("桌面画面")
    desktop_title.setObjectName("PanelTitle")
    desktop_hint = QLabel("SSH 隧道: Jetson 127.0.0.1:5900")
    desktop_hint.setObjectName("MutedText")
    desktop_header.addWidget(desktop_title)
    desktop_header.addStretch(1)
    desktop_header.addWidget(desktop_hint)
    desktop_layout.addLayout(desktop_header)
    desktop_layout.addWidget(window.remote_desktop_view, 1)
    layout.addWidget(desktop_panel, 1)
    layout.addWidget(build_note("此页通过 SSH 连接 Jetson 本机 x11vnc，只监听 127.0.0.1:5900，不需要额外打开 VNC/NoMachine 客户端。Jetson 必须已经登录图形桌面。"), 0)
    return page
