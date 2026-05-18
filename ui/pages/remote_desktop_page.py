from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.vnc_client import VncDisplayWidget
from ui.pages.common import build_note, build_panel


def build_remote_desktop_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.remote_desktop_display_edit = QLineEdit(":0")
    window.remote_desktop_xauthority_edit = QLineEdit("/home/jetson/.Xauthority")
    window.remote_desktop_port_spin = QSpinBox()
    window.remote_desktop_port_spin.setRange(5900, 5999)
    window.remote_desktop_port_spin.setValue(5900)
    window.remote_desktop_status_label = QLabel("未连接")
    window.remote_desktop_status_label.setObjectName("MutedText")

    grid.addWidget(QLabel("DISPLAY"), 0, 0)
    grid.addWidget(window.remote_desktop_display_edit, 0, 1)
    grid.addWidget(QLabel("XAUTHORITY"), 1, 0)
    grid.addWidget(window.remote_desktop_xauthority_edit, 1, 1)
    grid.addWidget(QLabel("VNC 端口"), 2, 0)
    grid.addWidget(window.remote_desktop_port_spin, 2, 1)
    grid.addWidget(QLabel("状态"), 3, 0)
    grid.addWidget(window.remote_desktop_status_label, 3, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("安装 x11vnc", window.install_remote_desktop_service, False),
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
    grid.addLayout(buttons, 4, 0, 1, 2)
    layout.addWidget(build_panel("Jetson 远程桌面", grid))

    window.remote_desktop_view = VncDisplayWidget()
    layout.addWidget(build_panel("桌面画面", _single_widget_layout(window.remote_desktop_view)), 1)
    layout.addWidget(build_note("此页通过 SSH 连接 Jetson 本机 x11vnc，只监听 127.0.0.1:5900，不需要额外打开 VNC/NoMachine 客户端。Jetson 必须已经登录图形桌面。"))
    return page


def _single_widget_layout(widget):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget)
    return layout
