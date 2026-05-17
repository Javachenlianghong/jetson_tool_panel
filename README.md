# Jetson Tool Panel

Windows 上使用的 PyQt5 小工具，用来管理 Jetson、RK3588 等 Linux 边缘设备开发流程中的常用操作。

界面采用简约侧边栏工作台布局：左侧导航切换 `代理`、`项目传输`、`设备状态`、`显示设置`、`命令参考`，右侧顶部显示 SSH、代理和显示状态，底部日志区始终可见。

## 功能

- 开放 Windows Clash Verge 局域网代理端口
- 复制 Jetson 代理命令
- 配置 SSH Key
- 测试 SSH 连接
- 上传 `jetson-proxy-session.sh` 到 Jetson
- 从 Jetson 拉取项目
- 同步本地项目改动到 Jetson
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
    paths.py                   源码模式和 PyInstaller 模式路径
    settings.py                配置辅助函数
  services/
    ssh_service.py             SSH/SCP/同步命令拼装
    proxy_service.py           Windows Clash 防火墙命令拼装
    display_service.py         xrandr 显示命令拼装
    device_health_service.py   设备体检采集脚本和解析器
  ui/
    main_window.py             主窗口、侧边栏、状态条和日志区
    pages/
      proxy_page.py            代理工作台
      transfer_page.py         项目传输
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
```

它保存窗口大小、Windows IP、代理端口、SSH 地址、远程路径、分辨率、设备状态自动刷新设置等常用配置。该文件只属于本机环境，已经被 `.gitignore` 忽略。

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

- 左侧导航栏：固定入口，快速切换代理、项目传输、设备状态、显示设置和命令参考。
- 顶部状态条：显示 SSH 连接、代理状态和显示状态，只作为提示，不改变命令行为。
- 工作台面板：默认 `代理` 页集中放置代理配置、Jetson SSH 和项目同步。
- 底部日志：所有命令输出统一显示，便于排查 SSH、SCP、PowerShell 和 xrandr 问题。

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
- `配置 SSH Key` 会打开单独 PowerShell 窗口，按提示输入 Jetson 密码。
- `设备状态` 只执行只读命令；自动刷新默认关闭，可在页面中选择 5、10 或 30 秒间隔。
- `显示设置` 只影响当前 Jetson 图形会话，重启或重新登录后可能恢复。
- 命令执行日志会按 Windows 命令行规则显示带空格的路径，便于复制和排查。
- 如果 Jetson 没有 `xrandr`，安装：

```bash
sudo apt install x11-xserver-utils
```

## 后续功能池

- 开发流水线：远程 CMake/make 构建、远程启动/停止程序、查看远程程序日志、一键清理 build/cache/logs。
- 设备初始化：新设备向导、SSH Key、代理脚本、apt/pip 源、时区、时间同步。
- 依赖检查：Jetson 的 CUDA/TensorRT/OpenCV/Python/cmake，RK3588 的 rknn-toolkit/rknpu/OpenCV/ffmpeg。
- 文件管理：远程目录浏览、常用路径收藏、上传/下载单文件、同步前差异预览。
- 运行监控：远程进程列表、服务状态检查、实时日志 tail、GitHub/pip/apt/Windows 代理连通性测试。
- 模型部署：ONNX/engine/rknn 文件管理、TensorRT engine 转换模板、RKNN 转换/部署模板、推理参数保存和快速运行。
