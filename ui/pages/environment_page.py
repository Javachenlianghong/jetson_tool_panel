from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_environment_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    buttons = QHBoxLayout()
    check_button = QPushButton("检查开发环境")
    check_button.setObjectName("PrimaryButton")
    check_button.clicked.connect(window.run_environment_check)
    init_button = QPushButton("初始化检查")
    init_button.clicked.connect(window.run_device_init_advice)
    window.command_buttons.append(check_button)
    window.command_buttons.append(init_button)
    buttons.addWidget(check_button)
    buttons.addWidget(init_button)
    buttons.addStretch(1)

    layout.addWidget(build_panel("Jetson / RK3588 环境检查", buttons))
    layout.addWidget(build_note(
        "检查 OS、内核、Python、构建工具、OpenCV、FFmpeg、Jetson CUDA/TensorRT、RK3588/RKNPU 和常见 Python 包；初始化检查只输出建议命令，不会直接修改远端系统。"
    ))
    layout.addStretch(1)
    return page
