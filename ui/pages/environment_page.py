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
    window.command_buttons.append(check_button)
    buttons.addWidget(check_button)
    buttons.addStretch(1)

    layout.addWidget(build_panel("Jetson / RK3588 环境检查", buttons))
    layout.addWidget(build_note(
        "检查 OS、内核、Python、构建工具、OpenCV、FFmpeg、Jetson CUDA/TensorRT、RK3588/RKNPU 和常见 Python 包。"
    ))
    layout.addStretch(1)
    return page
