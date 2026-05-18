"""Generic remote development commands for Linux edge devices."""

from core.command_runner import quote_for_bash


ENVIRONMENT_SECTION_ORDER = [
    "OS",
    "Kernel",
    "CPU",
    "Python",
    "Build tools",
    "OpenCV Python",
    "FFmpeg",
    "Jetson",
    "RK3588 / Rockchip",
    "Common libraries",
]

ENVIRONMENT_STATUS_TEXT = {
    "ok": "正常",
    "warning": "注意",
    "error": "异常",
    "unknown": "未检测",
}
CHECK_STATUS_TEXT = ENVIRONMENT_STATUS_TEXT

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

TRTEXEC_CANDIDATES = (
    "/usr/src/tensorrt/bin/trtexec",
    "/usr/local/tensorrt/bin/trtexec",
    "/usr/local/TensorRT/bin/trtexec",
    "/opt/tensorrt/bin/trtexec",
)


def suggest_engine_output_name(model_path, precision="fp16"):
    name = str(model_path or "").strip().split("/")[-1].split("\\")[-1]
    if "." in name:
        stem = ".".join(name.split(".")[:-1]) or name
    else:
        stem = name or "model"
    suffix = str(precision or "fp16").strip().lower() or "fp16"
    if suffix == "fp32":
        return "{}.engine".format(stem)
    return "{}-{}.engine".format(stem, suffix)


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


def _meaningful_lines(lines):
    return [line.strip() for line in lines if str(line).strip()]


def _section_summary(lines, max_lines=4):
    meaningful = _meaningful_lines(lines)
    if not meaningful:
        return "无输出"
    return "\n".join(meaningful[:max_lines])


def _split_double_equal_sections(lines):
    sections = []
    title = None
    body = []

    def flush():
        if title:
            sections.append({
                "title": title,
                "lines": list(body),
            })

    for raw_line in lines:
        line = str(raw_line).rstrip("\r\n")
        stripped = line.strip()
        if stripped.startswith("== ") and stripped.endswith(" =="):
            flush()
            title = stripped[3:-3].strip()
            body = []
        elif title:
            body.append(line)
    flush()
    return sections


def _environment_section_status(title, lines):
    meaningful = _meaningful_lines(lines)
    if not meaningful:
        return "unknown"

    text = "\n".join(meaningful)
    lower_text = text.lower()
    negative_markers = (
        "不可用",
        "不存在",
        "not found",
        "no such file",
        "command not found",
        "modulenotfounderror",
        "traceback",
        "[miss]",
    )

    def has_negative(line):
        lower_line = line.lower()
        return any(marker in lower_line for marker in negative_markers)

    if title == "Jetson":
        for line in meaningful:
            lower_line = line.lower()
            if has_negative(line):
                continue
            if any(marker in lower_line for marker in ("nv_tegra", "tegrastats:", "nvinfer", "cuda", "cudnn", "tensorrt")):
                return "ok"
        if any(line.startswith("ii ") for line in meaningful):
            return "ok"
        return "unknown"

    if title == "RK3588 / Rockchip":
        for line in meaningful:
            lower_line = line.lower()
            if has_negative(line):
                continue
            if any(marker in lower_line for marker in ("rk3588", "rockchip", "rknpu", "rknn")):
                return "ok"
        return "unknown"

    if title == "Common libraries":
        unavailable = sum(1 for line in meaningful if "不可用" in line or "not found" in line.lower())
        if unavailable == 0:
            return "ok"
        if unavailable < len(meaningful):
            return "warning"
        return "error"

    if any(marker in lower_text for marker in negative_markers):
        if title in ("OS", "Kernel", "CPU", "Python"):
            return "error"
        return "warning"

    return "ok"


def parse_environment_check_output(lines):
    found_sections = _split_double_equal_sections(lines)
    by_title = {section["title"]: section for section in found_sections}
    items = []

    for title in ENVIRONMENT_SECTION_ORDER:
        section = by_title.get(title, {"title": title, "lines": []})
        status = _environment_section_status(title, section["lines"])
        details = "\n".join(_meaningful_lines(section["lines"]))
        items.append({
            "title": title,
            "status": status,
            "status_text": ENVIRONMENT_STATUS_TEXT.get(status, status),
            "summary": _section_summary(section["lines"]),
            "details": details,
        })

    known_titles = set(ENVIRONMENT_SECTION_ORDER)
    for section in found_sections:
        if section["title"] in known_titles:
            continue
        status = _environment_section_status(section["title"], section["lines"])
        details = "\n".join(_meaningful_lines(section["lines"]))
        items.append({
            "title": section["title"],
            "status": status,
            "status_text": ENVIRONMENT_STATUS_TEXT.get(status, status),
            "summary": _section_summary(section["lines"]),
            "details": details,
        })

    summary = {status: 0 for status in ENVIRONMENT_STATUS_TEXT}
    for item in items:
        summary[item["status"]] = summary.get(item["status"], 0) + 1

    return {
        "items": items,
        "summary": summary,
    }


def parse_device_init_advice_output(lines):
    sections = _split_double_equal_sections(lines)
    summary = []
    for section in sections:
        meaningful = _meaningful_lines(section["lines"])
        if not meaningful:
            continue
        if section["title"] in ("Network and proxy", "Required tools", "Suggested install commands"):
            summary.append("== {} ==\n{}".format(section["title"], "\n".join(meaningful[:12])))
    return "\n\n".join(summary) if summary else "\n".join(_meaningful_lines(lines)[-30:])


def _status_from_success_flags(flags):
    if not flags:
        return "unknown"
    if any(flag is False for flag in flags):
        return "error"
    return "ok"


def _combined_statuses(statuses):
    statuses = [status for status in statuses if status]
    if not statuses:
        return "unknown"
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    if "unknown" in statuses:
        return "warning" if "ok" in statuses else "unknown"
    return "ok"


def parse_network_diagnostics_output(lines):
    sections = _split_double_equal_sections(lines)
    by_title = {section["title"]: section for section in sections}
    checks = []
    for section in sections:
        title = section["title"]
        for line in _meaningful_lines(section["lines"]):
            if line.startswith("[OK] "):
                checks.append({"name": line[5:], "status": "ok", "section": title})
            elif line.startswith("[FAIL] "):
                checks.append({"name": line[7:], "status": "error", "section": title})

    check_by_name = {check["name"]: check for check in checks}

    def check_status(name):
        return check_by_name.get(name, {}).get("status", "unknown")

    groups = [
        {
            "title": "远端地址",
            "status": "ok" if _meaningful_lines(by_title.get("IP addresses", {}).get("lines", [])) else "unknown",
            "summary": _section_summary(by_title.get("IP addresses", {}).get("lines", []), 3),
        },
        {
            "title": "公网连通",
            "status": check_status("Ping public IP 8.8.8.8"),
            "summary": "Ping public IP 8.8.8.8: {}".format(
                CHECK_STATUS_TEXT.get(check_status("Ping public IP 8.8.8.8"), "未检测")
            ),
        },
        {
            "title": "DNS / GitHub",
            "status": _combined_statuses([
                check_status("DNS github.com"),
                check_status("Ping github.com"),
                check_status("HTTPS github.com"),
            ]),
            "summary": "DNS: {}\nPing: {}\nHTTPS: {}".format(
                CHECK_STATUS_TEXT.get(check_status("DNS github.com"), "未检测"),
                CHECK_STATUS_TEXT.get(check_status("Ping github.com"), "未检测"),
                CHECK_STATUS_TEXT.get(check_status("HTTPS github.com"), "未检测"),
            ),
        },
        {
            "title": "Windows 代理",
            "status": check_status("Windows proxy port"),
            "summary": "代理端口: {}".format(CHECK_STATUS_TEXT.get(check_status("Windows proxy port"), "未检测")),
        },
        {
            "title": "pip / apt",
            "status": "ok" if (
                _meaningful_lines(by_title.get("pip config", {}).get("lines", []))
                or _meaningful_lines(by_title.get("apt sources", {}).get("lines", []))
            ) else "unknown",
            "summary": "pip: {}\napt: {}".format(
                _section_summary(by_title.get("pip config", {}).get("lines", []), 1),
                _section_summary(by_title.get("apt sources", {}).get("lines", []), 2),
            ),
        },
    ]
    summary = {status: 0 for status in CHECK_STATUS_TEXT}
    for group in groups:
        summary[group["status"]] = summary.get(group["status"], 0) + 1
    return {
        "groups": groups,
        "checks": checks,
        "summary": summary,
    }


def parse_peripheral_check_output(lines):
    sections = _split_double_equal_sections(lines)
    by_title = {section["title"]: section for section in sections}
    specs = [
        ("USB", "USB"),
        ("Video devices", "摄像头"),
        ("Display", "显示"),
        ("Storage", "磁盘"),
        ("Network interfaces", "网卡"),
        ("I2C / SPI", "I2C / SPI"),
    ]
    items = []
    for section_title, display_title in specs:
        section_lines = by_title.get(section_title, {}).get("lines", [])
        meaningful = _meaningful_lines(section_lines)
        text = "\n".join(meaningful).lower()
        if not meaningful:
            status = "unknown"
        elif any(marker in text for marker in ("不可用", "未发现", "not found", "no such file")):
            status = "warning"
        else:
            status = "ok"
        items.append({
            "title": display_title,
            "status": status,
            "status_text": CHECK_STATUS_TEXT.get(status, status),
            "summary": _section_summary(section_lines, 4),
            "details": "\n".join(meaningful),
        })
    summary = {status: 0 for status in CHECK_STATUS_TEXT}
    for item in items:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    return {
        "items": items,
        "summary": summary,
    }


def parse_process_list_output(lines):
    rows = []
    for raw_line in lines:
        line = str(raw_line).strip()
        if not line or line.startswith("PID ") or line.startswith("开始:") or line.startswith("+ "):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        rows.append({
            "pid": parts[0],
            "ppid": parts[1],
            "cpu": parts[2],
            "mem": parts[3],
            "elapsed": parts[4],
            "command": parts[5],
        })
    return rows


def parse_file_list_output(lines):
    path = ""
    rows = []
    for raw_line in lines:
        line = str(raw_line).rstrip("\r\n")
        stripped = line.strip()
        if stripped.startswith("Listing:"):
            path = stripped.split(":", 1)[1].strip()
            continue
        if not stripped or stripped.startswith("total "):
            continue
        parts = stripped.split(None, 8)
        if len(parts) < 9 or not parts[0]:
            continue
        mode = parts[0]
        if mode[0] not in "-dlcbsp":
            continue
        rows.append({
            "mode": mode,
            "owner": parts[2],
            "group": parts[3],
            "size": parts[4],
            "modified": " ".join(parts[5:8]),
            "name": parts[8],
        })
    return {
        "path": path,
        "rows": rows,
    }


def parse_service_status_output(lines):
    meaningful = _meaningful_lines(lines)
    text = "\n".join(meaningful)
    active = ""
    loaded = ""
    pid = ""
    summary = ""
    for line in meaningful:
        stripped = line.strip()
        if not summary and ".service" in stripped:
            summary = stripped
        if stripped.startswith("Loaded:"):
            loaded = stripped
        elif stripped.startswith("Active:"):
            active = stripped
        elif stripped.startswith("Main PID:"):
            pid = stripped

    lower_active = active.lower()
    if "active (running)" in lower_active or "active (exited)" in lower_active:
        status = "ok"
    elif "inactive" in lower_active or "dead" in lower_active:
        status = "warning"
    elif "failed" in lower_active:
        status = "error"
    elif active:
        status = "unknown"
    else:
        status = "error" if any("could not be found" in line.lower() or "not-found" in line.lower() for line in meaningful) else "unknown"

    return {
        "status": status,
        "status_text": CHECK_STATUS_TEXT.get(status, status),
        "summary": summary or "服务状态输出",
        "active": active or "Active: 未检测",
        "loaded": loaded or "Loaded: 未检测",
        "pid": pid or "Main PID: 未检测",
        "details": text,
    }


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


def device_init_advice_command(windows_ip, port):
    return r"""
windows_ip=__WINDOWS_IP__
proxy_port=__PROXY_PORT__

section() {
    echo
    echo "== $1 =="
}

echo "Device initialization checklist"
date 2>/dev/null || true

section "System identity"
hostname 2>/dev/null || true
cat /etc/os-release 2>/dev/null | head -n 8 || true
uname -a 2>/dev/null || true

section "Time and locale"
timedatectl status 2>/dev/null || date
locale 2>/dev/null | head -n 12 || true

section "Network and proxy"
ip -o -4 addr show 2>/dev/null || ifconfig 2>/dev/null || true
printf 'Suggested temporary proxy:\n'
printf '  export http_proxy=http://%s:%s\n' "$windows_ip" "$proxy_port"
printf '  export https_proxy=http://%s:%s\n' "$windows_ip" "$proxy_port"

section "APT sources"
grep -Rhs '^[^#]' /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null | head -n 60 || echo "apt sources unavailable"

section "pip config"
python3 -m pip config list 2>/dev/null || pip3 config list 2>/dev/null || echo "pip config unavailable"

section "Required tools"
for cmd in git cmake make gcc g++ python3 pip3 curl rsync; do
    if command -v "$cmd" >/dev/null 2>&1; then
        printf '[OK] %s -> %s\n' "$cmd" "$(command -v "$cmd")"
    else
        printf '[MISS] %s\n' "$cmd"
    fi
done

section "Suggested install commands"
cat <<'EOF'
# Review before running manually:
sudo apt update
sudo apt install -y git cmake build-essential python3-pip curl rsync v4l-utils
python3 -m pip install --upgrade pip
EOF
""".replace("__WINDOWS_IP__", quote_for_bash(windows_ip.strip())).replace(
        "__PROXY_PORT__", quote_for_bash(str(port).strip())
    )


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


def trtexec_resolver_command():
    candidates = " ".join(quote_for_bash(path) for path in TRTEXEC_CANDIDATES)
    return (
        'trtexec_bin="$(command -v trtexec || true)"; '
        'if [ -z "$trtexec_bin" ]; then '
        "for candidate in {}; do "
        'if [ -x "$candidate" ]; then trtexec_bin="$candidate"; break; fi; '
        "done; "
        "fi; "
        'if [ -z "$trtexec_bin" ]; then '
        "echo 'ERROR: trtexec not found. Install TensorRT samples or add trtexec to PATH.' >&2; "
        "exit 127; "
        "fi"
    ).format(candidates)


def tensorrt_environment_command():
    return r"""
set +e
echo "== TensorRT executable =="
__TRTEXEC_RESOLVER__
status=$?
if [ "$status" -ne 0 ]; then
    exit "$status"
fi
printf 'trtexec: %s\n' "$trtexec_bin"
"$trtexec_bin" --help 2>&1 | head -n 8 || true
echo
echo "== CUDA =="
command -v nvcc >/dev/null 2>&1 && nvcc --version || echo "nvcc not found"
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
echo
echo "== TensorRT libraries =="
python3 - <<'PY' 2>/dev/null || true
try:
    import tensorrt as trt
    print("TensorRT Python:", trt.__version__)
except Exception as exc:
    print("TensorRT Python unavailable:", exc)
PY
ldconfig -p 2>/dev/null | grep -E 'libnvinfer|libnvonnxparser' | head -n 12 || true
""".replace("__TRTEXEC_RESOLVER__", trtexec_resolver_command())


def model_validate_command(workdir, model_path, output_path="", test_image=""):
    return r"""
set -e
workdir=__WORKDIR__
model_path=__MODEL__
output_path=__OUTPUT__
test_image=__IMAGE__
echo "== Model validation =="
cd "$workdir"
printf 'Workdir: %s\n' "$PWD"
if [ ! -f "$model_path" ]; then
    echo "ERROR: input model not found: $model_path"
    exit 2
fi
printf 'Input model: '
ls -lh "$model_path"
if [ -n "$output_path" ]; then
    output_dir="$(dirname "$output_path")"
    [ "$output_dir" = "." ] || mkdir -p "$output_dir"
    if [ ! -w "$output_dir" ]; then
        echo "ERROR: output directory is not writable: $output_dir"
        exit 3
    fi
    printf 'Output target: %s\n' "$output_path"
fi
if [ -n "$test_image" ]; then
    if [ -f "$test_image" ]; then
        printf 'Test image: '
        ls -lh "$test_image"
    else
        printf 'WARN: test image not found: %s\n' "$test_image"
    fi
fi
echo "Model validation OK"
""".replace("__WORKDIR__", quote_for_bash(workdir.strip() or ".")).replace(
        "__MODEL__", quote_for_bash(model_path.strip())
    ).replace("__OUTPUT__", quote_for_bash(output_path.strip())).replace(
        "__IMAGE__", quote_for_bash(test_image.strip())
    )


def tensorrt_command(workdir, onnx_path, engine_path, precision):
    precision_flag = "--fp16" if precision.lower() == "fp16" else ""
    if precision.lower() == "int8":
        precision_flag = "--int8"
    args = [
        "--onnx={}".format(onnx_path.strip()),
        "--saveEngine={}".format(engine_path.strip()),
    ]
    if precision_flag:
        args.append(precision_flag)
    return 'set -e; cd {}; {}; "$trtexec_bin" {}'.format(
        quote_for_bash(workdir.strip() or "."),
        trtexec_resolver_command(),
        " ".join(quote_for_bash(part) for part in args),
    )


def tensorrt_benchmark_command(workdir, engine_path):
    args = [
        "--loadEngine={}".format(engine_path.strip()),
        "--warmUp=200",
        "--duration=10",
        "--useCudaGraph",
    ]
    return 'set -e; cd {}; {}; "$trtexec_bin" {}'.format(
        quote_for_bash(workdir.strip() or "."),
        trtexec_resolver_command(),
        " ".join(quote_for_bash(part) for part in args),
    )


def parse_tensorrt_output(lines):
    text = "\n".join(str(line) for line in lines)
    lower = text.lower()
    warnings = []
    for line in lines:
        raw = str(line).strip()
        low = raw.lower()
        if any(marker in low for marker in ("[w]", "warning", "insufficient workspace", "no implementation")):
            warnings.append(raw)

    metrics = {}
    import re

    throughput = re.search(r"Throughput:\s*([0-9.]+)\s*qps", text, re.IGNORECASE)
    if throughput:
        metrics["throughput"] = "{} qps".format(throughput.group(1))
    latency = re.search(r"Latency:\s*min\s*=\s*([^,]+),\s*max\s*=\s*([^,]+),\s*mean\s*=\s*([^,\n]+)", text, re.IGNORECASE)
    if latency:
        metrics["latency"] = "min {}, max {}, mean {}".format(
            latency.group(1).strip(),
            latency.group(2).strip(),
            latency.group(3).strip(),
        )
    gpu_compute = re.search(r"GPU Compute Time:\s*min\s*=\s*([^,]+),\s*max\s*=\s*([^,]+),\s*mean\s*=\s*([^,\n]+)", text, re.IGNORECASE)
    if gpu_compute:
        metrics["gpu_compute"] = "min {}, max {}, mean {}".format(
            gpu_compute.group(1).strip(),
            gpu_compute.group(2).strip(),
            gpu_compute.group(3).strip(),
        )

    if "trtexec not found" in lower or "command not found" in lower:
        status = "error"
        summary = "trtexec 不可用，请安装 TensorRT samples 或把 trtexec 加入 PATH。"
    elif "error" in lower or "[e]" in lower or "failed" in lower:
        status = "error"
        summary = "TensorRT 命令失败，查看日志中的 ERROR/failed 行。"
    elif metrics:
        status = "ok"
        summary = "TensorRT 执行完成: " + ", ".join("{}={}".format(k, v) for k, v in metrics.items())
    else:
        status = "warning" if warnings else "unknown"
        summary = "命令完成，但未解析到 TensorRT 性能指标。"

    if any("workspace" in item.lower() for item in warnings):
        summary += " 注意：存在 workspace 不足提示，可能影响性能。"

    return {
        "status": status,
        "summary": summary,
        "metrics": metrics,
        "warnings": warnings[:12],
        "details": text,
    }


def diagnose_command_output(lines):
    text = "\n".join(str(line) for line in lines)
    lower = text.lower()
    hints = []
    if "cannot open display" in lower:
        hints.append("DISPLAY 无法打开：确认 Jetson 桌面已登录，并在 SSH 会话导出 DISPLAY=:0 和 XAUTHORITY=/home/jetson/.Xauthority。")
    if "trtexec not found" in lower or "bash: trtexec: command not found" in lower:
        hints.append("trtexec 未找到：使用模型页“检测 TensorRT”，或把 /usr/src/tensorrt/bin 加入 PATH。")
    if "no such file" in lower or "not found" in lower:
        hints.append("存在文件不存在提示：检查远端工作目录、模型文件、视频或图片路径。")
    if "out of memory" in lower or "cuda error" in lower or "insufficient workspace" in lower:
        hints.append("内存/显存可能不足：尝试 fp16、降低输入尺寸/batch，关闭占用 GPU 的进程或增加 swap。")
    if "permission denied" in lower:
        hints.append("权限不足：检查文件权限，必要时 chmod +x 或使用有权限的目录。")
    return hints


def parse_runtime_output(lines):
    text = "\n".join(str(line) for line in lines)
    lower = text.lower()
    import re

    metrics = {}
    fps = re.search(r"\bFPS[:=\s]+([0-9.]+)", text, re.IGNORECASE)
    if fps:
        metrics["fps"] = fps.group(1)
    qps = re.search(r"Throughput:\s*([0-9.]+)\s*qps", text, re.IGNORECASE)
    if qps:
        metrics["throughput"] = "{} qps".format(qps.group(1))
    pid = re.search(r"\bPID[:=\s]+(\d+)", text, re.IGNORECASE)
    if pid:
        metrics["pid"] = pid.group(1)
    log_path = re.search(r"(?:log|日志)[:=\s]+([^\s]+\.log)", text, re.IGNORECASE)
    if log_path:
        metrics["log"] = log_path.group(1)

    hints = diagnose_command_output(lines)
    if "cannot open display" in lower:
        status = "error"
        summary = "图形显示打开失败。"
    elif any(marker in lower for marker in ("error", "failed", "traceback", "command not found")):
        status = "error"
        summary = "运行命令返回错误。"
    elif metrics:
        status = "ok"
        summary = "运行完成: " + ", ".join("{}={}".format(key, value) for key, value in metrics.items())
    else:
        status = "ok"
        summary = "运行命令已完成。"
    return {
        "status": status,
        "summary": summary,
        "metrics": metrics,
        "hints": hints,
        "details": text,
    }


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


def rknn_benchmark_template_command(workdir, output_path, test_image):
    return r"""
set -e
workdir=__WORKDIR__
model_path=__MODEL__
test_image=__IMAGE__
cd "$workdir"
echo "RKNN runtime smoke test template"
printf 'RKNN model : %s\n' "$model_path"
printf 'Test image : %s\n' "$test_image"
echo
ls -lh "$model_path" "$test_image" 2>/dev/null || true
echo
echo "Run the project-specific RKNN demo with the saved model and test image."
printf 'Example: ./rknn_yolov8_demo %s %s\n' "$model_path" "$test_image"
""".replace("__WORKDIR__", quote_for_bash(workdir.strip() or ".")).replace(
        "__MODEL__", quote_for_bash(output_path.strip())
    ).replace("__IMAGE__", quote_for_bash(test_image.strip() or "test.jpg"))


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
