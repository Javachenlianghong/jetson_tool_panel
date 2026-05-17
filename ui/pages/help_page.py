from PyQt5.QtWidgets import QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget

from ui.pages.common import build_panel


def build_help_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    text = QPlainTextEdit()
    text.setObjectName("ReferenceText")
    text.setReadOnly(True)
    text.setPlainText(
        "常用命令参考\n\n"
        "1. Windows 开放 Clash 代理端口\n"
        "   管理员 PowerShell:\n"
        "   .\\windows-clash-lan-temp.ps1\n\n"
        "2. Jetson 当前终端启用代理\n"
        "   source ./jetson-proxy-session.sh <Windows_IP> 7897\n\n"
        "3. Jetson 当前终端关闭代理\n"
        "   proxyoff\n\n"
        "4. 从 Windows 上传代理脚本到 Jetson\n"
        "   scp -O .\\jetson-proxy-session.sh jetson@192.168.55.1:~/jetson-proxy-session.sh\n\n"
        "5. 配置 SSH Key\n"
        "   先生成 Windows 本机公钥，再输入 Jetson 密码写入 ~/.ssh/authorized_keys\n\n"
        "6. 查询 Jetson 显示器\n"
        "   DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority xrandr --query\n\n"
        "7. 设置 Jetson 分辨率\n"
        "   DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority xrandr --output HDMI-0 --mode 1920x1080 --rate 60\n\n"
        "8. 从 Jetson 拉取项目到 Windows\n"
        "   scp -O -r jetson@192.168.55.1:/home/jetson/YoloV8-TensorRT-Jetson_Nano .\n\n"
        "9. 同步 Windows 项目改动到 Jetson\n"
        "   py -3 .\\YoloV8-TensorRT-Jetson_Nano\\sync-to-jetson.py\n\n"
        "10. 查看远程进程\n"
        "   ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | head -n 80\n\n"
        "11. 实时查看文件日志\n"
        "   tail -n 120 -F /path/to/app.log\n\n"
        "12. 查看 systemd 服务日志\n"
        "   journalctl -u your-service.service -n 200 -f\n\n"
        "13. 检查摄像头\n"
        "   v4l2-ctl --list-devices\n"
        "   v4l2-ctl --list-formats-ext -d /dev/video0\n\n"
        "14. Jetson TensorRT 转换模板\n"
        "   trtexec --onnx=model.onnx --saveEngine=model.engine --fp16\n\n"
        "15. RK3588 RKNPU 检测\n"
        "   ls -l /dev/rknpu*\n"
        "   dmesg | grep -i rknpu\n\n"
        "16. 项目级配置文件\n"
        "   config/projects.json\n\n"
        "17. 一键工作流建议\n"
        "   同步 -> 构建 -> 后台运行 -> 查看日志\n"
    )
    text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    ref_layout = QVBoxLayout()
    ref_layout.addWidget(text)
    layout.addWidget(build_panel("命令参考", ref_layout), 1)
    return page
