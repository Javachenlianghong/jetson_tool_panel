# Jetson Tool Panel

Windows 上使用的 PyQt5 小工具，用来管理 Jetson 开发流程中的常用操作。

## 功能

- 开放 Windows Clash Verge 局域网代理端口
- 复制 Jetson 代理命令
- 配置 SSH Key
- 测试 SSH 连接
- 上传 `jetson-proxy-session.sh` 到 Jetson
- 从 Jetson 拉取项目
- 同步本地项目改动到 Jetson
- 查询和设置 Jetson 显示分辨率
- 无显示器/VNC 场景下设置 X framebuffer 尺寸

## 目录结构

```text
jetson_tool_panel/
  jetson_gui.py                PyQt5 主程序
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

它保存窗口大小、Windows IP、代理端口、Jetson SSH、远程路径、分辨率等常用设置。该文件只属于本机环境，已经被 `.gitignore` 忽略。

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
3. 在 `项目传输` 页填写 Jetson SSH，例如 `jetson@192.168.1.13`。
4. 第一次使用先点击 `配置 SSH Key`。
5. 点击 `测试 SSH`，确认免密登录可用。
6. 点击 `上传代理脚本`，把代理脚本放到 Jetson 的 home 目录。
7. 在 Jetson 终端执行 GUI 复制的命令，例如：

```bash
source ./jetson-proxy-session.sh 192.168.1.11 7897
```

8. 使用 `同步到 Jetson` 或 `从 Jetson 拉取项目` 管理代码。

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
- `显示设置` 只影响当前 Jetson 图形会话，重启或重新登录后可能恢复。
- 命令执行日志会按 Windows 命令行规则显示带空格的路径，便于复制和排查。
- 如果 Jetson 没有 `xrandr`，安装：

```bash
sudo apt install x11-xserver-utils
```
