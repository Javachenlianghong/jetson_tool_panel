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


def x11vnc_start_command(display=":0", xauthority="$HOME/.Xauthority", port=5900):
    return r"""
set -e
__DISPLAY_ENV__
port=__PORT__
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
__PROBE_VNC_PORT__
if [ -z "${DISPLAY:-}" ]; then
    echo "ERROR: DISPLAY is empty."
    exit 2
fi
log=/tmp/jetson-tool-panel-x11vnc.log
pkill -f "x11vnc .* -rfbport $port" 2>/dev/null || true
nohup "$x11vnc_bin" \
    -display "$DISPLAY" \
    -auth "$XAUTHORITY" \
    -localhost \
    -forever \
    -shared \
    -nopw \
    -noxdamage \
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
        "__PACKAGE_STATUS__", X11VNC_PACKAGE_STATUS_SCRIPT.strip() + "\nprint_x11vnc_package_status"
    ).replace("__PORT__", quote_for_bash(str(int(port))))


def x11vnc_stop_command(port=5900):
    return r"""
port=__PORT__
pkill -f "x11vnc .* -rfbport $port" 2>/dev/null || true
echo "x11vnc stopped on port $port"
""".replace("__PORT__", quote_for_bash(str(int(port))))


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
