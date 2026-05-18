# Jetson Tool Panel

Windows 上使用的 PyQt5 小工具，用来管理 Jetson、RK3588 等 Linux 边缘设备开发流程中的常用操作。

界面采用简约侧边栏工作台布局：左侧导航集中管理代理、同步、运行、诊断、文件、服务、模型部署和设备档案，右侧顶部显示 SSH、代理和显示状态，底部日志区始终可见。

## 功能

- 开放 Windows Clash Verge 局域网代理端口
- 复制 Jetson 代理命令
- 配置 SSH Key
- 测试 SSH 连接
- 上传 `jetson-proxy-session.sh` 到 Jetson
- 从 Jetson 拉取项目
- 同步本地项目改动到 Jetson
- 远程运行命令，支持前台和后台运行
- FinalShell 式 SSH 工作台，终端、远端文件、本地文件和传输进度同屏显示
- 查看远程进程，按 PID 或关键字结束进程
- 实时 tail 远程日志、journalctl 和 dmesg
- 检查 GitHub、DNS、pip、apt 和 Windows 代理端口连通性
- 检查 Jetson/RK3588 开发环境和依赖，并输出新设备初始化建议
- 检测摄像头、显示器、USB、磁盘、网卡、I2C/SPI 外设
- Xftp 式双栏文件传输，本地/远端目录浏览、上传、下载、新建目录和删除
- 查看、启动、停止、重启 systemd 服务并跟踪服务日志
- 生成 TensorRT engine 转换命令、TensorRT benchmark 命令和 RKNN 部署/运行模板
- 保存多设备 SSH 和路径档案
- 导出 Markdown 诊断报告
- 刷新 Jetson/RK3588 设备体检信息
- 自动刷新 CPU、内存、磁盘、温度、网络 IP 和负载
- 查询和设置 Jetson 显示分辨率
- 无显示器/VNC 场景下设置 X framebuffer 尺寸

## 目录结构

```text
jetson_tool_panel/
  app.py                       程序入口
  jetson_gui.py                兼容入口，转发到 app.py
  core/
    command_runner.py          后台命令线程和命令格式化
    ssh_workers.py             Paramiko SSH 终端和 SFTP 线程
    paths.py                   源码模式和 PyInstaller 模式路径
    settings.py                配置辅助函数
  services/
    ssh_service.py             SSH/SCP/同步命令拼装
    proxy_service.py           Windows Clash 防火墙命令拼装
    display_service.py         xrandr 显示命令拼装
    device_health_service.py   设备体检采集脚本和解析器
    remote_ops_service.py      运行、进程、日志、诊断、文件、服务、模型命令
    paramiko_service.py        SSH 地址解析、Paramiko 客户端和 SFTP 数据转换
  ui/
    main_window.py             主窗口、侧边栏、状态条和日志区
    pages/
      proxy_page.py            代理工作台
      transfer_page.py         项目传输
      runtime_page.py          远程运行控制
      terminal_page.py         SSH 工作台，集成终端和 SFTP 文件传输
      process_page.py          进程管理
      logs_page.py             实时日志
      network_page.py          网络诊断
      environment_page.py      环境检查
      peripheral_page.py       外设检测
      files_page.py            旧文件管理页构建器，保留兼容
      service_page.py          服务管理
      model_page.py            模型部署
      devices_page.py          设备档案
      report_page.py           诊断报告
      health_page.py           设备状态
      display_page.py          显示设置
      help_page.py             命令参考
  run.bat                      项目内启动脚本
  build-exe.bat                PyInstaller 打包脚本
  requirements.txt             Python 依赖
  requirements-build.txt       打包依赖
  README.md                    项目说明
  scripts/
    jetson-proxy-session.sh    上传到 Jetson 的临时代理脚本
    windows-clash-lan-temp.ps1 Windows 防火墙临时放行脚本
```

运行后会在项目目录生成本地配置文件：

```text
settings.ini
config/projects.json
config/task_history.json
```

`settings.ini` 保存窗口大小和少量 UI 状态；`config/projects.json` 保存设备、项目、命令、日志和模型配置；`config/task_history.json` 保存最近任务历史。这些文件只属于本机环境，已经被 `.gitignore` 忽略。

仓库提交了一个可参考模板：

```text
config/projects.example.json
```

上一级目录里默认放被管理的 YOLO/TensorRT 项目：

```text
YoloV8-TensorRT-Jetson_Nano/
```

## 运行

在当前目录可以继续使用根目录兼容入口：

```powershell
.\run-jetson-gui.bat
```

也可以进入项目目录运行：

```powershell
cd .\jetson_tool_panel
.\run.bat
```

如果缺少 PyQt5：

```powershell
py -3 -m pip install -r .\jetson_tool_panel\requirements.txt
```

运行时依赖包括 `PyQt5` 和 `paramiko>=3.4,<4`。SSH 工作台里的终端与 SFTP 文件传输使用 Paramiko；项目同步、运行控制、日志查看和服务管理仍走系统 `ssh/scp` 命令，便于复用现有脚本和日志。

## 打包 EXE

进入项目目录运行：

```powershell
cd .\jetson_tool_panel
.\build-exe.bat
```

构建完成后会生成：

```text
jetson_tool_panel/dist/JetsonToolPanel.exe
```

修改 UI 后，旧的 `dist/JetsonToolPanel.exe` 不会自动更新；需要重新运行 `build-exe.bat` 才能把新界面打进 EXE。

打包使用 PyInstaller。当前开发环境是 Python 3.7，因此构建依赖固定为 PyInstaller 5.x：

```text
pyinstaller>=5.13,<6
```

EXE 旁边会生成本机配置文件 `settings.ini`。如果需要管理上一级目录里的 `YoloV8-TensorRT-Jetson_Nano`，建议保持这个相对位置：

```text
jetson/
  YoloV8-TensorRT-Jetson_Nano/
  jetson_tool_panel/
    dist/
      JetsonToolPanel.exe
```

## 推荐使用顺序

1. 启动 Clash Verge，并确认端口，例如 `7897`。
2. 在 `代理` 页点击 `管理员窗口启用`，放行 Windows 防火墙。
3. 在 `代理` 工作台的 `Jetson SSH` 面板填写 Jetson SSH，例如 `jetson@192.168.1.13`。
4. 第一次使用先点击 `配置 SSH Key`。
5. 点击 `测试 SSH`，确认免密登录可用。
6. 点击 `上传代理脚本`，把代理脚本放到 Jetson 的 home 目录。
7. 在 Jetson 终端执行 GUI 复制的命令，例如：

```bash
source ./jetson-proxy-session.sh 192.168.1.11 7897
```

8. 在 `代理` 工作台或 `项目传输` 页使用 `同步到 Jetson`、`从 Jetson 拉取项目` 管理代码。

## 界面布局

- 左侧导航栏：按常用、诊断、运维、项目与设备分组；常用入口包含工作台、项目传输、环境检查、设备状态、SSH 工作台和运行控制。
- 顶部状态条：显示 SSH 连接、代理状态和显示状态，只作为提示，不改变命令行为。
- 工作台面板：默认 `代理` 页集中放置代理配置、Jetson SSH 和项目同步。
- 底部日志：所有命令输出统一显示，便于排查 SSH、SCP、PowerShell 和 xrandr 问题。

## 开发调试

- `工作台`：按当前设备和项目执行同步、构建、运行、停止、日志和诊断报告。
- `运行控制`：在远端目录执行任意命令；后台运行时输出写入 `run-control.log`。
- `SSH 工作台`：采用类似 FinalShell 的同屏布局，左侧是远端/本地文件列表和传输进度，右侧是持久 SSH shell；终端区域可直接键盘输入，连接成功后会尝试刷新远端文件列表。文件表支持右键上传、下载、本地预览、复制路径、打开本地位置和进入远端目录。首次未知 host key 会自动接受并记录提示。认证优先使用系统 SSH key/agent，失败时弹窗输入密码，密码只保存在当前会话内。
- `进程管理`：通过 `ps` 查看远程进程，支持 PID 结束和 `pkill -f` 关键字结束。
- `日志查看`：支持普通文件 `tail -F`、`journal:`、`journal:服务名` 和 `dmesg`。
- `网络诊断`：检查远端 IP、路由、DNS、GitHub、pip/apt 配置和 Windows 代理端口。
- `环境检查`：检查 OS、Python、构建工具、OpenCV、FFmpeg、Jetson CUDA/TensorRT、RK3588/RKNPU；初始化检查会汇总时区、apt/pip 源、代理和常用依赖建议。
- `外设检测`：检查 USB、摄像头、v4l2 格式、显示器、磁盘、网卡、I2C/SPI。

## 文件、服务和模型

- `文件传输`：集成在 `SSH 工作台` 左侧，支持双击进入目录、路径栏跳转、上传/下载多选文件或目录、新建远端目录、删除本地/远端路径和传输取消；传输时显示当前文件进度和整体进度。远端默认路径来自当前项目 `remote_root`，本地默认路径来自当前项目 `local_root`。
- `服务管理`：查看 systemd 状态，启动、停止、重启服务，实时查看服务日志。
- `模型部署`：每个项目可保存多个模型配置；Jetson 可调用 `trtexec` 转换 TensorRT engine 并运行 benchmark；RK3588 页面输出 RKNN 部署和运行模板。
- `项目配置`：保存当前项目的本地路径、远端路径、构建命令、运行命令、停止关键字和日志目标。
- `设备档案`：保存多个设备的名称、SSH 地址和代理配置，方便在 Jetson、RK3588 之间切换。
- `诊断报告`：汇总设备状态、网络、环境和外设检查输出，保存到本机 `reports/` 目录。

## 设备状态

`设备状态` 页通过当前 SSH 地址执行只读 Linux 命令，不在远端安装 agent。

当前采集内容：

- 设备摘要：设备类型、主机名、内核、架构、运行时间、设备详情
- 运行指标：CPU、内存、根目录磁盘、温度、网络 IP、负载
- 设备能力：Jetson 的 `tegrastats` 摘要、RK3588/RKNPU 检测提示

设备识别策略：

- Jetson：检测 `/etc/nv_tegra_release`、`tegrastats` 或 `/sys/devices/gpu.0`
- RK3588：检测 `/proc/device-tree/compatible`、`lscpu` 或 `uname` 中的 Rockchip/RK3588 信息
- 通用 Linux：无法归类时仍展示主机名、内核、架构、内存、磁盘和负载

温度从 `/sys/class/thermal/thermal_zone*/temp` 读取。某些系统缺少命令或传感器时，对应字段显示 `未知`，整体刷新不会因此中断。

## 显示分辨率

`显示设置` 页通过 SSH 调用 Jetson 上的 `xrandr`。

先点击：

```text
查询显示器
```

如果能看到类似：

```text
HDMI-0 connected
```

就可以选择 `HDMI-0` 并设置分辨率。

如果只看到：

```text
HDMI-0 disconnected
DP-0 disconnected
```

说明 Jetson 当前 X 会话没有检测到真实显示器。此时可以勾选：

```text
无 connected 显示器时设置 VNC/虚拟画布
```

工具会改用：

```bash
xrandr --fb 1920x1080
```

这适合 VNC、远程桌面或无头显示环境。

## 注意

- Windows 防火墙规则需要管理员权限。
- `测试 SSH` 使用非交互模式，要求已经配置 SSH Key。
- 内置 SSH 终端和 SFTP 文件传输使用密钥优先；密钥不可用时会弹窗输入密码，密码不会写入 `settings.ini` 或 `config/projects.json`。
- 内置 SSH 终端是基础 shell，不做完整 VT100/TUI 渲染；`vim`、`top`、`htop` 等全屏交互程序可尝试运行，但显示效果不保证。
- `配置 SSH Key` 会打开单独 PowerShell 窗口，按提示输入 Jetson 密码。
- `设备状态` 只执行只读命令；自动刷新默认关闭，可在页面中选择 5、10 或 30 秒间隔。
- 进程结束、删除远端路径、服务启动/停止/重启都会弹出确认。
- 服务管理涉及 `sudo -n systemctl`，如果远端没有配置免密 sudo，相关操作会在日志中显示失败。
- `显示设置` 只影响当前 Jetson 图形会话，重启或重新登录后可能恢复。
- 命令执行日志会按 Windows 命令行规则显示带空格的路径，便于复制和排查。
- 如果 Jetson 没有 `xrandr`，安装：

```bash
sudo apt install x11-xserver-utils
```

## 完整性与安全边界

- 当前界面里的按钮都有实际处理逻辑；不会保留“暂未启用”的空入口。
- 设备初始化检查只输出当前状态和建议命令，不会直接修改远端 apt、pip、时区或系统服务。
- 文件删除属于高风险操作：界面会二次确认，命令层也会拒绝系统根目录、相对路径和包含 `..` 的路径。
- 项目、设备、模型和远端路径收藏会保存到 `config/projects.json`；如果该文件损坏，工具会自动备份为 `.broken` 并生成可用默认配置。

## 开发验证

常用检查命令：

```powershell
py -3 -m py_compile .\app.py .\jetson_gui.py .\ui\main_window.py
py -3 -m compileall .\core .\services .\ui
py -3 -m unittest discover -s tests
```
