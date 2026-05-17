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
    window.model_profile_combo = QComboBox()
    window.model_name_edit = QLineEdit("Default Model")
    window.model_workdir_edit = QLineEdit(window.remote_path_edit.text())
    window._bind_line_edits(window.remote_path_edit, window.model_workdir_edit)
    window.model_source_edit = QLineEdit("model.onnx")
    window.model_output_edit = QLineEdit("model.engine")
    window.model_test_image_edit = QLineEdit("test.jpg")
    window.model_precision_combo = QComboBox()
    window.model_precision_combo.addItems(["fp16", "fp32", "int8"])

    grid.addWidget(QLabel("模型配置"), 0, 0)
    grid.addWidget(window.model_profile_combo, 0, 1)
    grid.addWidget(QLabel("模型名称"), 1, 0)
    grid.addWidget(window.model_name_edit, 1, 1)
    grid.addWidget(QLabel("远程目录"), 2, 0)
    grid.addWidget(window.model_workdir_edit, 2, 1)
    grid.addWidget(QLabel("输入模型"), 3, 0)
    grid.addWidget(window.model_source_edit, 3, 1)
    grid.addWidget(QLabel("输出文件"), 4, 0)
    grid.addWidget(window.model_output_edit, 4, 1)
    grid.addWidget(QLabel("测试图片"), 5, 0)
    grid.addWidget(window.model_test_image_edit, 5, 1)
    grid.addWidget(QLabel("精度"), 6, 0)
    grid.addWidget(window.model_precision_combo, 6, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("保存模型配置", window.save_model_profile, True),
        ("加载模型配置", window.load_model_profile, True),
        ("删除模型配置", window.delete_model_profile, False),
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
    grid.addLayout(buttons, 7, 0, 1, 2)

    layout.addWidget(build_panel("模型部署模板", grid))
    layout.addWidget(build_note("Jetson 使用 trtexec 生成 TensorRT engine；RK3588 页面给出 RKNN 部署命令模板，转换通常在装有 rknn-toolkit2 的 x86 主机执行。"))
    layout.addStretch(1)
    return page
