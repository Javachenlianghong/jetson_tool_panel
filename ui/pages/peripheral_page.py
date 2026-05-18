from PyQt5.QtWidgets import QGridLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_check_card, build_note, build_panel


def build_peripheral_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.peripheral_result_labels = {}

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.video_device_edit = QLineEdit("/dev/video0")
    check_button = QPushButton("检测外设")
    check_button.setObjectName("PrimaryButton")
    check_button.clicked.connect(window.run_peripheral_check)
    window.command_buttons.append(check_button)
    grid.addWidget(QLabel("摄像头设备"), 0, 0)
    grid.addWidget(window.video_device_edit, 0, 1)
    grid.addWidget(check_button, 1, 1)
    grid.setColumnStretch(1, 1)

    layout.addWidget(build_panel("摄像头、显示与外设检测", grid))

    result_grid = QGridLayout()
    result_grid.setHorizontalSpacing(10)
    result_grid.setVerticalSpacing(10)
    for index, title in enumerate(["USB", "摄像头", "显示", "磁盘", "网卡", "I2C / SPI"]):
        result_grid.addWidget(build_check_card(window.peripheral_result_labels, title), index // 3, index % 3)
    result_grid.setColumnStretch(0, 1)
    result_grid.setColumnStretch(1, 1)
    result_grid.setColumnStretch(2, 1)
    layout.addWidget(build_panel("检测结果", result_grid))

    layout.addWidget(build_note("会检查 USB、/dev/video*、v4l2 格式、xrandr 显示器、磁盘、网卡、I2C/SPI 设备节点。"))
    layout.addStretch(1)
    return page
