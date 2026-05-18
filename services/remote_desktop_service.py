"""Remote desktop service commands for sharing Jetson's active X11 display."""

from core.command_runner import quote_for_bash


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
if ! command -v x11vnc >/dev/null 2>&1; then
    echo "ERROR: x11vnc not found. Install it with: sudo apt install -y x11vnc"
    exit 127
fi
if [ -z "${DISPLAY:-}" ]; then
    echo "ERROR: DISPLAY is empty."
    exit 2
fi
log=/tmp/jetson-tool-panel-x11vnc.log
pkill -f "x11vnc .* -rfbport $port" 2>/dev/null || true
nohup x11vnc \
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
sleep 1
if ! kill -0 "$pid" 2>/dev/null; then
    echo "ERROR: x11vnc failed to start."
    tail -n 80 "$log" 2>/dev/null || true
    exit 1
fi
echo "x11vnc started on localhost:$port"
echo "pid=$pid"
tail -n 30 "$log" 2>/dev/null || true
""".replace("__DISPLAY_ENV__", _display_env(display, xauthority)).replace("__PORT__", quote_for_bash(str(int(port))))


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
if command -v x11vnc >/dev/null 2>&1; then
    echo "x11vnc already installed: $(command -v x11vnc)"
    exit 0
fi
if command -v apt-get >/dev/null 2>&1; then
    echo "Installing x11vnc with apt-get..."
    sudo apt-get update
    sudo apt-get install -y x11vnc
    command -v x11vnc
    exit 0
fi
echo "ERROR: x11vnc is missing and this system does not have apt-get."
exit 127
"""
