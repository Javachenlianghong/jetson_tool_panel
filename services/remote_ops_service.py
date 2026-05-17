"""Generic remote development commands for Linux edge devices."""

from core.command_runner import quote_for_bash


PROTECTED_REMOTE_PATHS = {
    "",
    "/",
    ".",
    "..",
    "~",
    "$HOME",
    "${HOME}",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/home",
    "/lib",
    "/lib64",
    "/media",
    "/mnt",
    "/opt",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/sys",
    "/tmp",
    "/usr",
    "/var",
}


def clean_remote_path(remote_path):
    return str(remote_path or "").strip()


def remote_path_refusal_reason(remote_path, destructive=False):
    path = clean_remote_path(remote_path)
    normalized = path.rstrip("/") or "/"
    if not path:
        return "Remote path is empty."
    if "\x00" in path or "\n" in path or "\r" in path:
        return "Remote path contains unsupported control characters."
    if any(part == ".." for part in path.split("/")):
        return "Remote path must not contain '..' segments."
    if path in PROTECTED_REMOTE_PATHS or normalized in PROTECTED_REMOTE_PATHS:
        return "Remote path points to a protected system location."
    if destructive and not path.startswith("/"):
        return "Destructive file operations require an absolute remote path."
    return ""


def _refuse_remote_path_command(action, remote_path, reason):
    return (
        "echo {}; echo {}; exit 2"
    ).format(
        quote_for_bash("Refuse to {} unsafe path: {}".format(action, clean_remote_path(remote_path))),
        quote_for_bash("Reason: {}".format(reason)),
    )


def _remote_path_guard(action, destructive=False):
    absolute_guard = ""
    if destructive:
        absolute_guard = r"""
case "$path" in
    /*) ;;
    *) echo "Refuse to __ACTION__ unsafe path: $path"; echo "Reason: destructive file operations require an absolute remote path."; exit 2 ;;
esac
"""
    return (r"""
protected=' / . .. ~ $HOME ${HOME} /bin /boot /dev /etc /home /lib /lib64 /media /mnt /opt /proc /root /run /sbin /sys /tmp /usr /var '
normalized="${path%/}"
[ -n "$normalized" ] || normalized="/"
case "$path" in
    *'/../'*|*'/..'|'../'*|'..') echo "Refuse to __ACTION__ unsafe path: $path"; echo "Reason: remote path must not contain '..' segments."; exit 2 ;;
esac
case " $protected " in
    *" $path "*|*" $normalized "*) echo "Refuse to __ACTION__ unsafe path: $path"; echo "Reason: protected system location."; exit 2 ;;
esac
""".replace("__ACTION__", action) + absolute_guard.replace("__ACTION__", action))


def run_program_command(workdir, command, background=False):
    workdir = workdir.strip() or "."
    command = command.strip()
    if background:
        return (
            "set -e; cd {workdir}; "
            "nohup sh -lc {command} > run-control.log 2>&1 & "
            "echo Started PID=$!; echo Log: $(pwd)/run-control.log"
        ).format(
            workdir=quote_for_bash(workdir),
            command=quote_for_bash(command),
        )
    return "set -e; cd {}; sh -lc {}".format(
        quote_for_bash(workdir),
        quote_for_bash(command),
    )


def process_list_command(pattern=""):
    pattern = pattern.strip()
    return r"""
pattern=__PATTERN__
echo "PID   PPID  CPU  MEM  ELAPSED   COMMAND"
if [ -n "$pattern" ]; then
    ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | awk 'NR==1 || index(tolower($0), tolower(pat))' pat="$pattern" | head -n 120
else
    ps -eo pid,ppid,pcpu,pmem,etime,cmd --sort=-pcpu | head -n 120
fi
""".replace("__PATTERN__", quote_for_bash(pattern))


def kill_pid_command(pid):
    return r"""
pid=__PID__
case "$pid" in
    ''|*[!0-9]*) echo "Invalid PID: $pid"; exit 2 ;;
esac
kill -TERM "$pid"
echo "Sent TERM to PID $pid"
""".replace("__PID__", quote_for_bash(str(pid).strip()))


def pkill_pattern_command(pattern):
    return r"""
pattern=__PATTERN__
if [ -z "$pattern" ]; then
    echo "Pattern is empty."
    exit 2
fi
pkill -TERM -f "$pattern"
echo "Sent TERM to processes matching: $pattern"
""".replace("__PATTERN__", quote_for_bash(pattern.strip()))


def tail_log_command(target, lines=100):
    target = target.strip()
    try:
        lines = max(1, int(lines))
    except (TypeError, ValueError):
        lines = 100

    return r"""
target=__TARGET__
lines=__LINES__
if [ -z "$target" ]; then
    echo "Log target is empty."
    exit 2
fi

case "$target" in
    journal:*)
        unit="${target#journal:}"
        if [ -z "$unit" ]; then
            journalctl -n "$lines" -f
        else
            journalctl -u "$unit" -n "$lines" -f
        fi
        ;;
    dmesg)
        dmesg -w
        ;;
    *)
        tail -n "$lines" -F "$target"
        ;;
esac
""".replace("__TARGET__", quote_for_bash(target)).replace("__LINES__", quote_for_bash(str(lines)))


def network_diagnostics_command(windows_ip, port):
    return r"""
windows_ip=__WINDOWS_IP__
proxy_port=__PROXY_PORT__

run_check() {
    name="$1"
    shift
    echo
    echo "== $name =="
    if "$@"; then
        echo "[OK] $name"
    else
        echo "[FAIL] $name"
    fi
}

echo "Remote network diagnostics"
date 2>/dev/null || true
echo "Windows proxy: ${windows_ip}:${proxy_port}"
echo
echo "== IP addresses =="
ip -o -4 addr show 2>/dev/null || ifconfig 2>/dev/null || true
echo
echo "== Routes =="
ip route 2>/dev/null || route -n 2>/dev/null || true

run_check "Ping public IP 8.8.8.8" ping -c 2 -W 2 8.8.8.8
run_check "DNS github.com" getent hosts github.com
run_check "Ping github.com" ping -c 2 -W 2 github.com

if command -v curl >/dev/null 2>&1; then
    run_check "HTTPS github.com" curl -I -L --max-time 10 https://github.com
    run_check "Windows proxy port" curl -I --max-time 6 "http://${windows_ip}:${proxy_port}"
else
    echo
    echo "curl not found; skipping HTTP checks."
fi

echo
echo "== pip config =="
python3 -m pip config list 2>/dev/null || pip3 config list 2>/dev/null || echo "pip config unavailable"
echo
echo "== apt sources =="
grep -Rhs '^[^#]' /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null | head -n 40 || true
""".replace("__WINDOWS_IP__", quote_for_bash(windows_ip.strip())).replace(
        "__PROXY_PORT__", quote_for_bash(str(port))
    )


def environment_check_command():
    return r"""
section() {
    echo
    echo "== $1 =="
}

try_cmd() {
    title="$1"
    shift
    section "$title"
    "$@" 2>&1 || echo "不可用"
}

echo "Environment check"
date 2>/dev/null || true
try_cmd "OS" sh -lc 'cat /etc/os-release 2>/dev/null || lsb_release -a 2>/dev/null || uname -a'
try_cmd "Kernel" uname -a
try_cmd "CPU" sh -lc 'lscpu 2>/dev/null || cat /proc/cpuinfo | head -n 40'
try_cmd "Python" sh -lc 'python3 --version; python3 -m pip --version 2>/dev/null || true'
try_cmd "Build tools" sh -lc 'cmake --version 2>/dev/null | head -n 1; gcc --version 2>/dev/null | head -n 1; g++ --version 2>/dev/null | head -n 1; git --version 2>/dev/null'
try_cmd "OpenCV Python" python3 -c 'import cv2; print(cv2.__version__)'
try_cmd "FFmpeg" sh -lc 'ffmpeg -version 2>/dev/null | head -n 1'

section "Jetson"
cat /etc/nv_tegra_release 2>/dev/null || echo "nv_tegra_release 不存在"
command -v tegrastats >/dev/null 2>&1 && echo "tegrastats: $(command -v tegrastats)" || echo "tegrastats 不存在"
nvcc --version 2>/dev/null || echo "nvcc 不存在"
python3 - <<'PY' 2>/dev/null || echo "TensorRT Python 不可用"
import tensorrt as trt
print(trt.__version__)
PY
dpkg -l 2>/dev/null | grep -E 'nvinfer|cuda|cudnn' | head -n 30 || true

section "RK3588 / Rockchip"
tr '\0' '\n' < /proc/device-tree/compatible 2>/dev/null || echo "compatible 不可读"
ls -l /dev/rknpu* 2>/dev/null || echo "RKNPU 设备节点不存在"
dmesg 2>/dev/null | grep -i -E 'rknpu|rk3588|rockchip' | tail -n 20 || true
python3 - <<'PY' 2>/dev/null || echo "rknn Python 包不可用"
import rknn
print(rknn.__file__)
PY

section "Common libraries"
python3 - <<'PY'
mods = ["numpy", "onnx", "torch", "ultralytics"]
for name in mods:
    try:
        mod = __import__(name)
        print(f"{name}: {getattr(mod, '__version__', 'installed')}")
    except Exception as exc:
        print(f"{name}: 不可用 ({exc})")
PY
"""


def peripheral_check_command(video_device="/dev/video0"):
    return r"""
video_device=__VIDEO_DEVICE__
section() {
    echo
    echo "== $1 =="
}

echo "Peripheral check"
date 2>/dev/null || true
section "USB"
lsusb 2>/dev/null || echo "lsusb 不可用"
section "Video devices"
ls -l /dev/video* 2>/dev/null || echo "未发现 /dev/video*"
if command -v v4l2-ctl >/dev/null 2>&1; then
    v4l2-ctl --list-devices 2>/dev/null || true
    echo
    echo "Formats for ${video_device}:"
    v4l2-ctl --list-formats-ext -d "$video_device" 2>/dev/null || true
else
    echo "v4l2-ctl 不可用"
fi
section "Display"
if command -v xrandr >/dev/null 2>&1; then
    DISPLAY="${DISPLAY:-:0}" xrandr --query 2>/dev/null || xrandr --query 2>/dev/null || true
else
    echo "xrandr 不可用"
fi
section "Storage"
lsblk 2>/dev/null || df -h
section "Network interfaces"
ip link 2>/dev/null || ifconfig -a 2>/dev/null || true
section "I2C / SPI"
ls -l /dev/i2c* /dev/spidev* 2>/dev/null || echo "未发现 I2C/SPI 设备节点"
""".replace("__VIDEO_DEVICE__", quote_for_bash(video_device.strip() or "/dev/video0"))


def file_list_command(remote_path):
    return r"""
path=__PATH__
if [ -z "$path" ]; then
    path="$HOME"
fi
echo "Listing: $path"
if [ -d "$path" ]; then
    ls -lah "$path"
else
    ls -lah "$path"
fi
""".replace("__PATH__", quote_for_bash(remote_path.strip()))


def mkdir_command(remote_path):
    path = clean_remote_path(remote_path)
    reason = remote_path_refusal_reason(path)
    if reason:
        return _refuse_remote_path_command("create", path, reason)
    return r"""
path=__PATH__
__GUARD__
mkdir -p -- "$path"
echo "Created: $path"
""".replace("__PATH__", quote_for_bash(path)).replace("__GUARD__", _remote_path_guard("create"))


def remove_path_command(remote_path):
    path = clean_remote_path(remote_path)
    reason = remote_path_refusal_reason(path, destructive=True)
    if reason:
        return _refuse_remote_path_command("remove", path, reason)
    return r"""
path=__PATH__
__GUARD__
rm -rf -- "$path"
echo "Removed: $path"
""".replace("__PATH__", quote_for_bash(path)).replace("__GUARD__", _remote_path_guard("remove", destructive=True))


def service_command(service_name, action):
    service_name = service_name.strip()
    action = action.strip()
    if action == "logs":
        return "journalctl -u {} -n 200 -f".format(quote_for_bash(service_name))
    if action == "status":
        return "systemctl status {} --no-pager || systemctl --user status {} --no-pager".format(
            quote_for_bash(service_name),
            quote_for_bash(service_name),
        )
    if action in ("start", "stop", "restart"):
        return (
            "sudo -n systemctl {action} {service} || "
            "systemctl --user {action} {service}"
        ).format(action=action, service=quote_for_bash(service_name))
    return "echo Unsupported service action: {}".format(quote_for_bash(action))


def tensorrt_command(workdir, onnx_path, engine_path, precision):
    precision_flag = "--fp16" if precision.lower() == "fp16" else ""
    if precision.lower() == "int8":
        precision_flag = "--int8"
    args = [
        "trtexec",
        "--onnx={}".format(onnx_path.strip()),
        "--saveEngine={}".format(engine_path.strip()),
    ]
    if precision_flag:
        args.append(precision_flag)
    return "set -e; cd {}; {}".format(
        quote_for_bash(workdir.strip() or "."),
        " ".join(quote_for_bash(part) for part in args),
    )


def rknn_template_command(workdir, model_path, output_path):
    return r"""
set -e
workdir=__WORKDIR__
model_path=__MODEL__
output_path=__OUTPUT__
cd "$workdir"
echo "RKNN deployment template"
printf 'Input model: %s\n' "$model_path"
printf 'Output RKNN: %s\n' "$output_path"
echo
echo "Typical conversion runs on an x86 host with rknn-toolkit2 installed."
echo "Typical runtime test runs on RK3588 with rknn runtime and /dev/rknpu."
echo
echo "Suggested runtime command:"
printf './rknn_yolov8_demo %s ./test.jpg\n' "$output_path"
""".replace("__WORKDIR__", quote_for_bash(workdir.strip() or ".")).replace(
        "__MODEL__", quote_for_bash(model_path.strip())
    ).replace("__OUTPUT__", quote_for_bash(output_path.strip()))


def health_report_section_command():
    return r"""
echo "Hostname: $(hostname 2>/dev/null || echo unknown)"
echo "Kernel: $(uname -a 2>/dev/null || echo unknown)"
echo "Uptime: $(uptime -p 2>/dev/null || cat /proc/uptime 2>/dev/null || echo unknown)"
echo "Load: $(cat /proc/loadavg 2>/dev/null || echo unknown)"
free -h 2>/dev/null || true
df -h / 2>/dev/null || true
for zone in /sys/class/thermal/thermal_zone*; do
    [ -e "$zone/temp" ] || continue
    name="$(cat "$zone/type" 2>/dev/null || basename "$zone")"
    raw="$(cat "$zone/temp" 2>/dev/null || true)"
    printf "%s %s\n" "$name" "$raw"
done
"""


def diagnostic_report_command(windows_ip, port, video_device="/dev/video0"):
    return "\n".join([
        "echo '# Remote Diagnostic Report'",
        "date 2>/dev/null || true",
        "echo",
        "echo '## Device Health'",
        health_report_section_command(),
        "echo",
        "echo '## Network'",
        network_diagnostics_command(windows_ip, port),
        "echo",
        "echo '## Environment'",
        environment_check_command(),
        "echo",
        "echo '## Peripherals'",
        peripheral_check_command(video_device),
    ])
