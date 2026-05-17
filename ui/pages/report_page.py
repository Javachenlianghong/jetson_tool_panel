from PyQt5.QtWidgets import QGridLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_report_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.report_dir_edit = QLineEdit(str(window.paths.tool_dir / "reports"))
    browse_button = QPushButton("浏览")
    browse_button.clicked.connect(window.choose_report_dir)
    report_button = QPushButton("生成诊断报告")
    report_button.setObjectName("PrimaryButton")
    report_button.clicked.connect(window.generate_diagnostic_report)
    window.command_buttons.append(report_button)

    grid.addWidget(QLabel("保存目录"), 0, 0)
    grid.addWidget(window.report_dir_edit, 0, 1)
    grid.addWidget(browse_button, 0, 2)
    grid.addWidget(report_button, 1, 1)
    grid.setColumnStretch(1, 1)

    layout.addWidget(build_panel("诊断报告导出", grid))
    layout.addWidget(build_note("报告会通过 SSH 汇总设备状态、网络、环境和外设检查输出，保存为本地 Markdown 文件。"))
    layout.addStretch(1)
    return page
