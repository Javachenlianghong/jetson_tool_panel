from PyQt5.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_model_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.model_workdir_edit = QLineEdit(window.remote_path_edit.text())
    window._bind_line_edits(window.remote_path_edit, window.model_workdir_edit)
    window.model_source_edit = QLineEdit("model.onnx")
    window.model_output_edit = QLineEdit("model.engine")
    window.model_precision_combo = QComboBox()
    window.model_precision_combo.addItems(["fp16", "fp32", "int8"])

    grid.addWidget(QLabel("远程目录"), 0, 0)
    grid.addWidget(window.model_workdir_edit, 0, 1)
    grid.addWidget(QLabel("输入模型"), 1, 0)
    grid.addWidget(window.model_source_edit, 1, 1)
    grid.addWidget(QLabel("输出文件"), 2, 0)
    grid.addWidget(window.model_output_edit, 2, 1)
    grid.addWidget(QLabel("精度"), 3, 0)
    grid.addWidget(window.model_precision_combo, 3, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("运行 TensorRT 转换", window.run_tensorrt_conversion, True),
        ("显示 RKNN 模板", window.show_rknn_template, False),
        ("复制当前命令", window.copy_model_command, False),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 4, 0, 1, 2)

    layout.addWidget(build_panel("模型部署模板", grid))
    layout.addWidget(build_note("Jetson 使用 trtexec 生成 TensorRT engine；RK3588 页面给出 RKNN 部署命令模板，转换通常在装有 rknn-toolkit2 的 x86 主机执行。"))
    layout.addStretch(1)
    return page
