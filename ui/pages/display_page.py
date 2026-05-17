from PyQt5.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_display_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)

    window.display_output_combo = QComboBox()
    window.display_output_combo.setEditable(True)
    window.display_output_combo.addItems(["auto", "HDMI-0", "HDMI-1", "DP-0", "DP-1", "eDP-1"])

    window.resolution_combo = QComboBox()
    window.resolution_combo.setEditable(True)
    window.resolution_combo.addItems([
        "1920x1080",
        "1280x720",
        "1366x768",
        "1600x900",
        "1024x768",
        "800x600",
        "2560x1440",
        "3840x2160",
    ])

    window.refresh_rate_spin = QSpinBox()
    window.refresh_rate_spin.setRange(0, 240)
    window.refresh_rate_spin.setValue(60)
    window.refresh_rate_spin.setSuffix(" Hz")
    window.refresh_rate_spin.setSpecialValueText("自动")

    window.display_env_edit = QLineEdit(":0")
    window.xauthority_edit = QLineEdit("$HOME/.Xauthority")
    window.framebuffer_fallback_check = QCheckBox("无 connected 显示器时设置 VNC/虚拟画布")
    window.framebuffer_fallback_check.setChecked(True)

    grid.addWidget(QLabel("使用 SSH"), 0, 0)
    grid.addWidget(QLabel("项目传输页里的 Jetson SSH 地址"), 0, 1, 1, 2)
    grid.addWidget(QLabel("显示输出口"), 1, 0)
    grid.addWidget(window.display_output_combo, 1, 1, 1, 2)
    grid.addWidget(QLabel("分辨率"), 2, 0)
    grid.addWidget(window.resolution_combo, 2, 1, 1, 2)
    grid.addWidget(QLabel("刷新率"), 3, 0)
    grid.addWidget(window.refresh_rate_spin, 3, 1, 1, 2)
    grid.addWidget(QLabel("DISPLAY"), 4, 0)
    grid.addWidget(window.display_env_edit, 4, 1, 1, 2)
    grid.addWidget(QLabel("XAUTHORITY"), 5, 0)
    grid.addWidget(window.xauthority_edit, 5, 1, 1, 2)
    grid.addWidget(QLabel("无头/VNC"), 6, 0)
    grid.addWidget(window.framebuffer_fallback_check, 6, 1, 1, 2)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    query_button = QPushButton("查询显示器")
    query_button.clicked.connect(window.query_jetson_displays)
    set_button = QPushButton("设置分辨率")
    set_button.clicked.connect(window.set_jetson_resolution)
    auto_button = QPushButton("恢复自动")
    auto_button.clicked.connect(window.auto_jetson_display)

    for button in (query_button, set_button, auto_button):
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)

    grid.addLayout(buttons, 7, 0, 1, 3)
    layout.addWidget(build_panel("Jetson 显示分辨率", grid))
    layout.addWidget(build_note(
        "说明：此功能通过 SSH 在 Jetson 的当前图形会话里执行 xrandr。"
        "设置通常只对当前桌面会话生效；如果 Jetson 没有启动桌面、使用 Wayland，"
        "或没有安装 xrandr，命令会失败并在日志中显示原因。"
    ))
    layout.addStretch(1)
    return page
