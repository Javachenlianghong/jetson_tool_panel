from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_project_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)

    window.project_id_edit = QLineEdit()
    window.project_name_edit = QLineEdit()
    window.project_local_root_edit = QLineEdit()
    window.project_remote_root_edit = QLineEdit()
    window.project_build_command_edit = QLineEdit()
    window.project_run_command_edit = QLineEdit()
    window.project_stop_pattern_edit = QLineEdit()
    window.project_log_target_edit = QLineEdit()

    fields = [
        ("项目 ID", window.project_id_edit),
        ("项目名称", window.project_name_edit),
        ("本地路径", window.project_local_root_edit),
        ("远端路径", window.project_remote_root_edit),
        ("构建命令", window.project_build_command_edit),
        ("运行命令", window.project_run_command_edit),
        ("停止关键字", window.project_stop_pattern_edit),
        ("日志目标", window.project_log_target_edit),
    ]
    for row, (label, editor) in enumerate(fields):
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(editor, row, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("保存项目", window.save_project_config, True),
        ("加载当前项目", window.load_project_config_to_form, True),
        ("删除项目", window.delete_project_config, False),
        ("从当前页面填充", window.fill_project_config_from_current, False),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, len(fields), 0, 1, 2)

    layout.addWidget(build_panel("项目配置", grid))
    layout.addWidget(build_note("项目绑定到顶部当前设备。保存后会写入 config/projects.json，并同步刷新顶部项目选择器。"))
    layout.addStretch(1)
    return page
