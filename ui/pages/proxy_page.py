from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.pages.common import build_note, build_panel


def build_proxy_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    proxy_grid = QGridLayout()
    proxy_grid.setHorizontalSpacing(10)
    proxy_grid.setVerticalSpacing(10)

    window.ip_combo = QComboBox()
    window.ip_combo.setEditable(True)
    window.ip_combo.currentTextChanged.connect(window._sync_default_cidr)

    refresh_ip_button = QPushButton("刷新 IP")
    refresh_ip_button.clicked.connect(window.refresh_ips)

    window.port_spin = QSpinBox()
    window.port_spin.setRange(1, 65535)
    window.port_spin.setValue(window.defaults.proxy_port)

    window.remote_address_edit = QLineEdit("192.168.1.0/24")
    window.clash_program_edit = QLineEdit(window.defaults.clash_program)

    browse_button = QPushButton("浏览")
    browse_button.clicked.connect(window.choose_clash_program)

    proxy_grid.addWidget(QLabel("Windows IP"), 0, 0)
    proxy_grid.addWidget(window.ip_combo, 0, 1)
    proxy_grid.addWidget(QLabel("端口"), 0, 2)
    proxy_grid.addWidget(window.port_spin, 0, 3)
    proxy_grid.addWidget(refresh_ip_button, 0, 4)
    proxy_grid.addWidget(QLabel("允许访问网段"), 1, 0)
    proxy_grid.addWidget(window.remote_address_edit, 1, 1, 1, 4)
    proxy_grid.addWidget(QLabel("Clash Verge 程序"), 2, 0)
    proxy_grid.addWidget(window.clash_program_edit, 2, 1, 1, 3)
    proxy_grid.addWidget(browse_button, 2, 4)
    proxy_grid.setColumnStretch(1, 1)
    proxy_grid.setColumnStretch(3, 1)

    proxy_buttons = QHBoxLayout()
    enable_button = QPushButton("管理员窗口启用")
    enable_button.setObjectName("PrimaryButton")
    enable_button.clicked.connect(window.enable_firewall_rule_elevated)
    direct_enable_button = QPushButton("直接启用")
    direct_enable_button.clicked.connect(window.enable_firewall_rule)
    stop_rule_button = QPushButton("关闭防火墙规则")
    stop_rule_button.clicked.connect(window.remove_firewall_rule)
    copy_button = QPushButton("复制 Jetson 代理命令")
    copy_button.clicked.connect(window.copy_proxy_command)

    for button in (enable_button, direct_enable_button, stop_rule_button, copy_button):
        window.command_buttons.append(button)
        proxy_buttons.addWidget(button)
    proxy_buttons.addStretch(1)
    proxy_grid.addLayout(proxy_buttons, 3, 0, 1, 5)

    layout.addWidget(build_panel("代理配置（Windows Clash）", proxy_grid))

    ssh_grid = QGridLayout()
    ssh_grid.setHorizontalSpacing(10)
    ssh_grid.setVerticalSpacing(10)

    ssh_grid.addWidget(QLabel("远端 SSH"), 0, 0)
    ssh_hint = QLabel("在窗口顶部统一填写，所有 SSH、同步、诊断和显示命令都会使用同一个地址。")
    ssh_hint.setObjectName("MutedText")
    ssh_hint.setWordWrap(True)
    ssh_grid.addWidget(ssh_hint, 0, 1, 1, 2)
    ssh_grid.setColumnStretch(1, 1)

    ssh_buttons = QHBoxLayout()
    ssh_button = QPushButton("测试 SSH")
    ssh_button.setObjectName("PrimaryButton")
    ssh_button.clicked.connect(window.test_ssh)
    setup_key_button = QPushButton("配置 SSH Key")
    setup_key_button.clicked.connect(window.configure_ssh_key)
    upload_proxy_button = QPushButton("上传代理脚本")
    upload_proxy_button.clicked.connect(window.upload_proxy_script)
    for button in (ssh_button, setup_key_button, upload_proxy_button):
        window.command_buttons.append(button)
        ssh_buttons.addWidget(button)
    ssh_buttons.addStretch(1)
    ssh_grid.addLayout(ssh_buttons, 1, 0, 1, 3)

    layout.addWidget(build_panel("SSH 操作", ssh_grid))

    sync_grid = QGridLayout()
    sync_grid.setHorizontalSpacing(10)
    sync_grid.setVerticalSpacing(10)

    window.remote_path_edit = QLineEdit(window.defaults.remote_path)
    window.local_root_edit = QLineEdit(str(window.paths.app_dir))

    choose_local_button = QPushButton("浏览")
    choose_local_button.clicked.connect(window.choose_local_root)

    sync_grid.addWidget(QLabel("本地项目根目录"), 0, 0)
    sync_grid.addWidget(window.local_root_edit, 0, 1)
    sync_grid.addWidget(choose_local_button, 0, 2)
    sync_grid.addWidget(QLabel("Jetson 项目路径"), 1, 0)
    sync_grid.addWidget(window.remote_path_edit, 1, 1, 1, 2)

    option_layout = QHBoxLayout()
    window.full_sync_check = QCheckBox("完整同步")
    window.dry_run_check = QCheckBox("只预览")
    window.no_delete_check = QCheckBox("不删除远端文件")
    option_layout.addWidget(window.full_sync_check)
    option_layout.addWidget(window.dry_run_check)
    option_layout.addWidget(window.no_delete_check)
    option_layout.addStretch(1)
    sync_grid.addLayout(option_layout, 2, 0, 1, 3)

    sync_buttons = QHBoxLayout()
    sync_button = QPushButton("同步到 Jetson")
    sync_button.setObjectName("PrimaryButton")
    sync_button.clicked.connect(window.sync_to_jetson)
    pull_button = QPushButton("从 Jetson 拉取项目")
    pull_button.clicked.connect(window.pull_from_jetson)
    init_button = QPushButton("初始化同步状态")
    init_button.clicked.connect(window.init_sync_state)
    for button in (sync_button, pull_button, init_button):
        window.command_buttons.append(button)
        sync_buttons.addWidget(button)
    sync_buttons.addStretch(1)
    sync_grid.addLayout(sync_buttons, 3, 0, 1, 3)
    sync_grid.setColumnStretch(1, 1)

    layout.addWidget(build_panel("项目同步", sync_grid))
    layout.addWidget(build_note("常用配置会自动保存；防火墙脚本需要管理员权限，建议优先使用“管理员窗口启用”。"))
    layout.addStretch(1)
    return page
