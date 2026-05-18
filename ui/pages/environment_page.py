from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.pages.common import build_note, build_panel


ENVIRONMENT_SECTIONS = [
    "OS",
    "Kernel",
    "CPU",
    "Python",
    "Build tools",
    "OpenCV Python",
    "FFmpeg",
    "Jetson",
    "RK3588 / Rockchip",
    "Common libraries",
]


def build_environment_page(window):
    page = QScrollArea()
    page.setObjectName("PageScroll")
    page.setWidgetResizable(True)
    page.setFrameShape(QFrame.NoFrame)
    content = QWidget()
    content.setObjectName("PageScrollContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.environment_summary_label = None
    window.environment_updated_label = None
    window.environment_result_labels = {}
    window.environment_init_text = None

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

    summary_layout = QHBoxLayout()
    summary_layout.setSpacing(10)
    for title, value, detail in [
        ("总览", "未运行", "点击“检查开发环境”后汇总状态"),
        ("系统", "未运行", "OS / Kernel / CPU"),
        ("开发工具", "未运行", "Python / CMake / GCC / Git"),
        ("加速能力", "未运行", "Jetson CUDA/TensorRT 或 RK3588/RKNPU"),
    ]:
        summary_layout.addWidget(_build_summary_card(window, title, value, detail), 1)
    layout.addWidget(build_panel("检查结果总览", summary_layout))

    result_grid = QGridLayout()
    result_grid.setHorizontalSpacing(10)
    result_grid.setVerticalSpacing(10)
    for index, section in enumerate(ENVIRONMENT_SECTIONS):
        result_grid.addWidget(_build_result_card(window, section), index // 2, index % 2)
    result_grid.setColumnStretch(0, 1)
    result_grid.setColumnStretch(1, 1)
    layout.addWidget(build_panel("分项状态", result_grid), 1)

    init_layout = QVBoxLayout()
    window.environment_init_text = QPlainTextEdit()
    window.environment_init_text.setObjectName("ReferenceText")
    window.environment_init_text.setReadOnly(True)
    window.environment_init_text.setMaximumHeight(120)
    window.environment_init_text.setPlainText("点击“初始化检查”后显示代理、工具缺失和建议命令摘要。")
    init_layout.addWidget(window.environment_init_text)
    layout.addWidget(build_panel("初始化建议摘要", init_layout))

    layout.addWidget(build_note(
        "检查 OS、内核、Python、构建工具、OpenCV、FFmpeg、Jetson CUDA/TensorRT、RK3588/RKNPU 和常见 Python 包；初始化检查只输出建议命令，不会直接修改远端系统。"
    ))
    page.setWidget(content)
    return page


def _build_summary_card(window, title, value, detail):
    card = QFrame()
    card.setObjectName("MetricBox")
    card.setProperty("state", "pending")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(12, 10, 12, 10)
    card_layout.setSpacing(5)

    title_label = QLabel(title)
    title_label.setObjectName("MutedText")
    value_label = QLabel(value)
    value_label.setObjectName("MetricValue")
    detail_label = QLabel(detail)
    detail_label.setObjectName("MutedText")
    detail_label.setWordWrap(True)
    detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    card_layout.addWidget(title_label)
    card_layout.addWidget(value_label)
    card_layout.addWidget(detail_label)

    if not window.environment_summary_label:
        window.environment_summary_label = {}
    window.environment_summary_label[title] = {
        "card": card,
        "value": value_label,
        "detail": detail_label,
    }
    return card


def _build_result_card(window, title):
    card = QFrame()
    card.setObjectName("EnvResultCard")
    card.setProperty("state", "pending")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)

    header = QHBoxLayout()
    title_label = QLabel(title)
    title_label.setObjectName("PanelLead")
    status_label = QLabel("未运行")
    status_label.setObjectName("EnvBadge")
    status_label.setProperty("state", "pending")
    header.addWidget(title_label)
    header.addStretch(1)
    header.addWidget(status_label)

    detail_label = QLabel("等待检查")
    detail_label.setObjectName("MutedText")
    detail_label.setWordWrap(True)
    detail_label.setMinimumHeight(44)
    detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

    layout.addLayout(header)
    layout.addWidget(detail_label)

    window.environment_result_labels[title] = {
        "card": card,
        "status": status_label,
        "detail": detail_label,
    }
    return card
