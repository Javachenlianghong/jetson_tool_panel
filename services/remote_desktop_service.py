"""Remote desktop service commands for sharing Jetson's active X11 display."""

from core.command_runner import quote_for_bash


X11VNC_RESOLVE_SCRIPT = r"""
x11vnc_bin="$(command -v x11vnc || true)"
if [ -z "$x11vnc_bin" ]; then
    for candidate in /usr/bin/x11vnc /usr/local/bin/x11vnc /bin/x11vnc; do
        if [ -x "$candidate" ]; then
            x11vnc_bin="$candidate"
            break
        fi
    done
fi
"""


VNC_PORT_PROBE_SCRIPT = r"""
probe_vnc_port() {
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$port" <<'PY'
import socket
import sys

sock = socket.socket()
sock.settimeout(0.4)
try:
    sock.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
        return $?
    fi
    if command -v nc >/dev/null 2>&1; then
        nc -z 127.0.0.1 "$port" >/dev/null 2>&1
        return $?
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | grep -E "[:.]$port\\b|\\]$port\\b" >/dev/null 2>&1
        return $?
    fi
    if command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | grep -E "[:.]$port\\b" >/dev/null 2>&1
        return $?
    fi
    return 2
}
"""


VNC_PORT_CLEANUP_SCRIPT = r"""
terminate_pid() {
    target_pid="$1"
    [ -n "$target_pid" ] || return 0
    if ! kill -0 "$target_pid" 2>/dev/null; then
        return 0
    fi
    kill "$target_pid" 2>/dev/null || true
    wait_attempt=0
    while [ "$wait_attempt" -lt 10 ]; do
        wait_attempt=$((wait_attempt + 1))
        if ! kill -0 "$target_pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    echo "Force killing stale x11vnc pid=$target_pid"
    kill -KILL "$target_pid" 2>/dev/null || true
}

configured_x11vnc_pids() {
    pgrep -af '[x]11vnc' 2>/dev/null \
        | awk -v port="$port" '
            $0 ~ "-rfbport[[:space:]]+" port {print $1}
            $0 ~ "localhost:" port {print $1}
        ' \
        | sort -u
}

vnc_port_owner_pids() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null \
            | awk -v suffix=":$port" '$4 ~ suffix"$" {print $0}' \
            | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
            | sort -u
        return 0
    fi
    if command -v netstat >/dev/null 2>&1; then
        netstat -ltnp 2>/dev/null \
            | awk -v suffix=":$port" '$4 ~ suffix"$" {print $7}' \
            | sed -n 's|^\([0-9][0-9]*\)/.*|\1|p' \
            | sort -u
        return 0
    fi
    if command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
        return 0
    fi
    if command -v fuser >/dev/null 2>&1; then
        fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' | sed '/^$/d' | sort -u
        return 0
    fi
    return 0
}

print_vnc_port_owners() {
    pids="$(vnc_port_owner_pids | tr '\n' ' ')"
    if [ -z "$pids" ]; then
        echo "No PID information available for port $port."
        return 0
    fi
    for owner_pid in $pids; do
        ps -p "$owner_pid" -o pid= -o args= 2>/dev/null || true
    done
}

clear_stale_x11vnc_port() {
    echo "Cleaning stale x11vnc on port $port..."
    for configured_pid in $(configured_x11vnc_pids); do
        echo "Stopping configured x11vnc pid=$configured_pid"
        terminate_pid "$configured_pid"
    done
    pids="$(vnc_port_owner_pids | tr '\n' ' ')"
    for owner_pid in $pids; do
        if ps -p "$owner_pid" -o args= 2>/dev/null | grep -q '[x]11vnc'; then
            echo "Stopping stale x11vnc pid=$owner_pid"
            terminate_pid "$owner_pid"
        fi
    done
    attempt=0
    while [ "$attempt" -lt 20 ]; do
        attempt=$((attempt + 1))
        if ! probe_vnc_port; then
            return 0
        fi
        sleep 0.1
    done
    echo "ERROR: 127.0.0.1:$port is still occupied."
    print_vnc_port_owners
    return 1
}
"""


X11VNC_PACKAGE_STATUS_SCRIPT = r"""
print_x11vnc_package_status() {
    if command -v dpkg-query >/dev/null 2>&1; then
        dpkg-query -W -f='dpkg=${db:Status-Abbrev} package=${binary:Package} version=${Version}\n' x11vnc 2>/dev/null || true
    fi
    if command -v apt-cache >/dev/null 2>&1; then
        apt-cache policy x11vnc 2>/dev/null | sed -n '1,12p' || true
    fi
}
"""


def _display_env(display, xauthority):
    display = str(display or ":0").strip() or ":0"
    xauthority = str(xauthority or "$HOME/.Xauthority").strip() or "$HOME/.Xauthority"
    return "export DISPLAY={}; export XAUTHORITY={};".format(
        quote_for_bash(display),
        quote_for_bash(xauthority),
    )


def _scale_value(scale):
    scale = str(scale or "").strip()
    if scale in ("1/2", "2/3", "3/4", "17/20"):
        return scale
    return ""


def x11vnc_start_command(display=":0", xauthority="$HOME/.Xauthority", port=5900, scale=""):
    return r"""
set -e
__DISPLAY_ENV__
port=__PORT__
scale_option=__SCALE_OPTION__
__RESOLVE_X11VNC__
if [ -z "$x11vnc_bin" ]; then
    echo "ERROR: x11vnc not found."
    echo "PATH=$PATH"
    __PACKAGE_STATUS__
    echo "Install it in this panel with the terminal install button, or run in SSH workbench:"
    echo "  sudo apt-get update && sudo apt-get install -y x11vnc"
    exit 127
fi
echo "x11vnc=$x11vnc_bin"
scale_args=""
if [ -n "$scale_option" ]; then
    scale_args="-scale $scale_option"
    echo "scale=$scale_option"
fi
__PROBE_VNC_PORT__
if [ -z "${DISPLAY:-}" ]; then
    echo "ERROR: DISPLAY is empty."
    exit 2
fi
log=/tmp/jetson-tool-panel-x11vnc.log
__CLEANUP_VNC_PORT__
clear_stale_x11vnc_port
nohup "$x11vnc_bin" \
    -display "$DISPLAY" \
    -auth "$XAUTHORITY" \
    -localhost \
    -forever \
    -shared \
    -nopw \
    -noxdamage \
    -no6 \
    -noipv6 \
    $scale_args \
    -rfbport "$port" \
    > "$log" 2>&1 &
pid=$!
ready=0
attempt=0
while [ "$attempt" -lt 30 ]; do
    attempt=$((attempt + 1))
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "ERROR: x11vnc failed to start."
        tail -n 80 "$log" 2>/dev/null || true
        exit 1
    fi
    if probe_vnc_port; then
        ready=1
        break
    fi
    sleep 0.2
done
if [ "$ready" != "1" ]; then
    echo "ERROR: x11vnc started but 127.0.0.1:$port is not accepting connections."
    echo "Processes:"
    pgrep -af "x11vnc" 2>/dev/null || true
    echo "Listening ports:"
    ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null || true
    tail -n 120 "$log" 2>/dev/null || true
    exit 1
fi
echo "x11vnc started on localhost:$port"
echo "pid=$pid"
tail -n 30 "$log" 2>/dev/null || true
""".replace("__DISPLAY_ENV__", _display_env(display, xauthority)).replace(
        "__RESOLVE_X11VNC__", X11VNC_RESOLVE_SCRIPT.strip()
    ).replace(
        "__PROBE_VNC_PORT__", VNC_PORT_PROBE_SCRIPT.strip()
    ).replace(
        "__CLEANUP_VNC_PORT__", VNC_PORT_CLEANUP_SCRIPT.strip()
    ).replace(
        "__PACKAGE_STATUS__", X11VNC_PACKAGE_STATUS_SCRIPT.strip() + "\nprint_x11vnc_package_status"
    ).replace("__PORT__", quote_for_bash(str(int(port)))).replace(
        "__SCALE_OPTION__", quote_for_bash(_scale_value(scale))
    )


def x11vnc_stop_command(port=5900):
    return r"""
port=__PORT__
__PROBE_VNC_PORT__
__CLEANUP_VNC_PORT__
clear_stale_x11vnc_port || true
echo "x11vnc stopped on port $port"
""".replace("__PORT__", quote_for_bash(str(int(port)))).replace(
        "__PROBE_VNC_PORT__", VNC_PORT_PROBE_SCRIPT.strip()
    ).replace(
        "__CLEANUP_VNC_PORT__", VNC_PORT_CLEANUP_SCRIPT.strip()
    )


def x11vnc_status_command(port=5900):
    return r"""
port=__PORT__
if pgrep -af "x11vnc .* -rfbport $port" >/dev/null 2>&1; then
    echo "x11vnc is running:"
    pgrep -af "x11vnc .* -rfbport $port" || true
else
    echo "x11vnc is not running on port $port"
fi
tail -n 40 /tmp/jetson-tool-panel-x11vnc.log 2>/dev/null || true
""".replace("__PORT__", quote_for_bash(str(int(port))))


def x11vnc_install_command():
    return r"""
set -e
__RESOLVE_X11VNC__
if [ -n "$x11vnc_bin" ]; then
    echo "x11vnc already installed: $x11vnc_bin"
    exit 0
fi
if command -v apt-get >/dev/null 2>&1; then
    echo "Installing x11vnc with apt-get..."
    if [ "$(id -u)" = "0" ]; then
        apt-get update
        apt-get install -y x11vnc
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo -n apt-get update
        sudo -n apt-get install -y x11vnc
    else
        echo "ERROR: sudo password is required."
        echo "Open this panel's SSH workbench and run:"
        echo "  sudo apt-get update && sudo apt-get install -y x11vnc"
        exit 126
    fi
    __RESOLVE_X11VNC__
    if [ -n "$x11vnc_bin" ]; then
        echo "$x11vnc_bin"
    else
        command -v x11vnc
    fi
    exit 0
fi
echo "ERROR: x11vnc is missing and this system does not have apt-get."
exit 127
""".replace("__RESOLVE_X11VNC__", X11VNC_RESOLVE_SCRIPT.strip())
