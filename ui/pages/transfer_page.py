from PyQt5.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_transfer_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    settings_grid = QGridLayout()
    settings_grid.setHorizontalSpacing(10)
    settings_grid.setVerticalSpacing(10)

    transfer_remote_path_edit = QLineEdit(window.remote_path_edit.text())
    transfer_local_root_edit = QLineEdit(window.local_root_edit.text())
    window._bind_line_edits(window.remote_path_edit, transfer_remote_path_edit)
    window._bind_line_edits(window.local_root_edit, transfer_local_root_edit)

    choose_local_button = QPushButton("浏览")
    choose_local_button.clicked.connect(window.choose_local_root)

    ssh_hint = QLabel("远端 SSH 地址在窗口顶部统一填写。")
    ssh_hint.setObjectName("MutedText")
    settings_grid.addWidget(QLabel("远端 SSH"), 0, 0)
    settings_grid.addWidget(ssh_hint, 0, 1, 1, 2)
    settings_grid.addWidget(QLabel("Jetson 项目路径"), 1, 0)
    settings_grid.addWidget(transfer_remote_path_edit, 1, 1, 1, 2)
    settings_grid.addWidget(QLabel("Windows 保存目录"), 2, 0)
    settings_grid.addWidget(transfer_local_root_edit, 2, 1)
    settings_grid.addWidget(choose_local_button, 2, 2)
    settings_grid.setColumnStretch(1, 1)
    layout.addWidget(build_panel("Jetson SSH 与项目路径", settings_grid))

    option_layout = QHBoxLayout()
    transfer_full_sync_check = QCheckBox("完整同步")
    transfer_dry_run_check = QCheckBox("只预览")
    transfer_no_delete_check = QCheckBox("不删除远端文件")
    transfer_full_sync_check.setChecked(window.full_sync_check.isChecked())
    transfer_dry_run_check.setChecked(window.dry_run_check.isChecked())
    transfer_no_delete_check.setChecked(window.no_delete_check.isChecked())
    window._bind_checkboxes(window.full_sync_check, transfer_full_sync_check)
    window._bind_checkboxes(window.dry_run_check, transfer_dry_run_check)
    window._bind_checkboxes(window.no_delete_check, transfer_no_delete_check)
    option_layout.addWidget(transfer_full_sync_check)
    option_layout.addWidget(transfer_dry_run_check)
    option_layout.addWidget(transfer_no_delete_check)
    option_layout.addStretch(1)
    layout.addWidget(build_panel("同步选项", option_layout))

    buttons_grid = QGridLayout()
    buttons_grid.setHorizontalSpacing(10)
    buttons_grid.setVerticalSpacing(10)

    ssh_button = QPushButton("测试 SSH")
    ssh_button.setObjectName("PrimaryButton")
    ssh_button.clicked.connect(window.test_ssh)
    setup_key_button = QPushButton("配置 SSH Key")
    setup_key_button.clicked.connect(window.configure_ssh_key)
    upload_proxy_button = QPushButton("上传代理脚本")
    upload_proxy_button.clicked.connect(window.upload_proxy_script)
    sync_button = QPushButton("同步到 Jetson")
    sync_button.setObjectName("PrimaryButton")
    sync_button.clicked.connect(window.sync_to_jetson)
    pull_button = QPushButton("从 Jetson 拉取项目")
    pull_button.clicked.connect(window.pull_from_jetson)
    init_button = QPushButton("初始化同步状态")
    init_button.clicked.connect(window.init_sync_state)

    transfer_buttons = [
        ssh_button,
        setup_key_button,
        upload_proxy_button,
        sync_button,
        pull_button,
        init_button,
    ]
    for index, button in enumerate(transfer_buttons):
        window.command_buttons.append(button)
        buttons_grid.addWidget(button, index // 3, index % 3)
    buttons_grid.setColumnStretch(0, 1)
    buttons_grid.setColumnStretch(1, 1)
    buttons_grid.setColumnStretch(2, 1)
    layout.addWidget(build_panel("快速操作", buttons_grid))
    layout.addWidget(build_note("远端 SSH 地址只在窗口顶部填写；此页只维护项目路径和同步选项。"))
    layout.addStretch(1)
    return page
