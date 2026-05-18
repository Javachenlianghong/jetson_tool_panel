from PyQt5.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

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
    window.model_choose_source_button = QPushButton("选择")
    window.model_choose_source_button.clicked.connect(window.choose_model_source_file)
    window.model_status_label = QLabel("未检测")
    window.model_status_label.setObjectName("MutedText")

    source_row = QHBoxLayout()
    source_row.setContentsMargins(0, 0, 0, 0)
    source_row.setSpacing(6)
    source_row.addWidget(window.model_source_edit, 1)
    source_row.addWidget(window.model_choose_source_button)

    grid.addWidget(QLabel("模型配置"), 0, 0)
    grid.addWidget(window.model_profile_combo, 0, 1)
    grid.addWidget(QLabel("模型名称"), 1, 0)
    grid.addWidget(window.model_name_edit, 1, 1)
    grid.addWidget(QLabel("远程目录"), 2, 0)
    grid.addWidget(window.model_workdir_edit, 2, 1)
    grid.addWidget(QLabel("输入模型"), 3, 0)
    grid.addLayout(source_row, 3, 1)
    grid.addWidget(QLabel("输出文件"), 4, 0)
    grid.addWidget(window.model_output_edit, 4, 1)
    grid.addWidget(QLabel("测试图片"), 5, 0)
    grid.addWidget(window.model_test_image_edit, 5, 1)
    grid.addWidget(QLabel("精度"), 6, 0)
    grid.addWidget(window.model_precision_combo, 6, 1)
    grid.addWidget(QLabel("状态"), 7, 0)
    grid.addWidget(window.model_status_label, 7, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("检测 TensorRT", window.detect_model_environment, True),
        ("生成输出名", window.suggest_model_output_name, False),
        ("验证路径", window.validate_model_paths, True),
        ("保存模型配置", window.save_model_profile, True),
        ("加载模型配置", window.load_model_profile, True),
        ("删除模型配置", window.delete_model_profile, False),
        ("运行 TensorRT 转换", window.run_tensorrt_conversion, True),
        ("转换并 Benchmark", window.run_tensorrt_conversion_then_benchmark, True),
        ("运行 Benchmark", window.run_model_benchmark, True),
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
    grid.addLayout(buttons, 8, 0, 1, 2)

    layout.addWidget(build_panel("模型部署模板", grid))
    result_layout = QVBoxLayout()
    window.model_result_text = QPlainTextEdit()
    window.model_result_text.setReadOnly(True)
    window.model_result_text.setMinimumHeight(150)
    window.model_result_text.setPlainText("检测 TensorRT 或运行转换后，这里会显示解析后的结果、性能指标和建议。")
    result_layout.addWidget(window.model_result_text)
    layout.addWidget(build_panel("模型部署结果", result_layout))
    layout.addWidget(build_note("Jetson 使用 trtexec 生成 TensorRT engine；RK3588 页面给出 RKNN 部署命令模板，转换通常在装有 rknn-toolkit2 的 x86 主机执行。"))
    layout.addStretch(1)
    return page
