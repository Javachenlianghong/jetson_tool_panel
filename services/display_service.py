"""Remote display command helpers."""

from core.command_runner import quote_for_bash


def display_env_prefix(display, xauthority):
    if not display:
        display = ":0"

    prefix = "export DISPLAY={}; ".format(quote_for_bash(display))
    if xauthority:
        if xauthority == "$HOME/.Xauthority":
            prefix += 'export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"; '
        else:
            prefix += "export XAUTHORITY={}; ".format(quote_for_bash(xauthority))
    return prefix


def query_display_command(display, xauthority):
    return (
        display_env_prefix(display, xauthority)
        + "echo DISPLAY=$DISPLAY; "
        + "echo XAUTHORITY=$XAUTHORITY; "
        + "if ! command -v xrandr >/dev/null 2>&1; then "
        + "echo 'xrandr not found. Install it with: sudo apt install x11-xserver-utils'; exit 127; "
        + "fi; "
        + "xrandr --query"
    )


def set_resolution_command(display, xauthority, output, mode, rate, framebuffer_fallback):
    remote_script = display_env_prefix(display, xauthority) + r"""
set -e
if ! command -v xrandr >/dev/null 2>&1; then
    echo "xrandr not found. Install it with: sudo apt install x11-xserver-utils"
    exit 127
fi

output=__OUTPUT__
mode=__MODE__
rate=__RATE__
framebuffer_fallback=__FRAMEBUFFER_FALLBACK__

if [ -z "$output" ] || [ "$output" = "auto" ]; then
    output="$(xrandr --query | awk '$2 == "connected" { print $1; exit }')"
fi

if [ -z "$output" ]; then
    if [ "$framebuffer_fallback" = "1" ]; then
        echo "No connected display output found."
        echo "Applying framebuffer size only for headless/VNC session: $mode"
        xrandr --fb "$mode"
        echo "Framebuffer size applied."
        xrandr --query
        exit 0
    fi
    echo "No connected display output found."
    xrandr --query
    exit 1
fi

output_state="$(xrandr --query | awk -v out="$output" '$1 == out { print $2; exit }')"
if [ "$output_state" != "connected" ]; then
    if [ "$framebuffer_fallback" = "1" ]; then
        echo "Output $output is not connected; state is: ${output_state:-missing}"
        echo "Applying framebuffer size only for headless/VNC session: $mode"
        xrandr --fb "$mode"
        echo "Framebuffer size applied."
        xrandr --query
        exit 0
    fi
    echo "Output $output is not connected; state is: ${output_state:-missing}"
    xrandr --query
    exit 1
fi

echo "Output: $output"
echo "Requested mode: $mode"
echo "Requested refresh: $rate Hz"

if ! xrandr --query | awk -v out="$output" -v mode="$mode" '
    $1 == out && $2 == "connected" { inside = 1; next }
    inside && /^[^[:space:]]/ { inside = 0 }
    inside && $1 == mode { found = 1 }
    END { exit found ? 0 : 1 }
'; then
    echo "Mode $mode is not listed for $output. Trying to create a temporary mode..."
    width="${mode%x*}"
    height="${mode#*x}"
    height="${height%%_*}"

    if ! printf "%s %s\n" "$width" "$height" | grep -Eq '^[0-9]+ [0-9]+$'; then
        echo "Cannot create modeline from mode: $mode"
        exit 1
    fi

    generate_rate="$rate"
    if [ "$generate_rate" -le 0 ]; then
        generate_rate=60
    fi

    if command -v cvt >/dev/null 2>&1; then
        modeline="$(cvt "$width" "$height" "$generate_rate" | awk -F'Modeline ' '/Modeline/{print $2}')"
    elif command -v gtf >/dev/null 2>&1; then
        modeline="$(gtf "$width" "$height" "$generate_rate" | awk -F'Modeline ' '/Modeline/{print $2}')"
    else
        echo "Mode is unavailable and neither cvt nor gtf exists on Jetson."
        exit 1
    fi

    if [ -z "$modeline" ]; then
        echo "Failed to generate modeline."
        exit 1
    fi

    generated_mode="$(printf "%s\n" "$modeline" | awk '{print $1}' | tr -d '"')"
    modeline_args="$(printf "%s\n" "$modeline" | cut -d' ' -f2-)"
    echo "Generated mode: $generated_mode"
    xrandr --newmode "$generated_mode" $modeline_args 2>/dev/null || true
    xrandr --addmode "$output" "$generated_mode" 2>/dev/null || true
    mode="$generated_mode"
fi

if [ "$rate" -gt 0 ]; then
    if ! xrandr --output "$output" --mode "$mode" --rate "$rate"; then
        echo "Retrying without explicit refresh rate..."
        xrandr --output "$output" --mode "$mode"
    fi
else
    xrandr --output "$output" --mode "$mode"
fi

echo "Resolution applied."
xrandr --query
"""
    return (
        remote_script
        .replace("__OUTPUT__", quote_for_bash(output))
        .replace("__MODE__", quote_for_bash(mode))
        .replace("__RATE__", quote_for_bash(str(rate)))
        .replace("__FRAMEBUFFER_FALLBACK__", quote_for_bash("1" if framebuffer_fallback else "0"))
    )


def auto_display_command(display, xauthority, output, framebuffer_fallback):
    remote_script = display_env_prefix(display, xauthority) + r"""
set -e
if ! command -v xrandr >/dev/null 2>&1; then
    echo "xrandr not found. Install it with: sudo apt install x11-xserver-utils"
    exit 127
fi

output=__OUTPUT__
framebuffer_fallback=__FRAMEBUFFER_FALLBACK__
if [ -z "$output" ] || [ "$output" = "auto" ]; then
    output="$(xrandr --query | awk '$2 == "connected" { print $1; exit }')"
fi

if [ -z "$output" ]; then
    if [ "$framebuffer_fallback" = "1" ]; then
        echo "No connected display output found."
        echo "Restoring headless/VNC framebuffer to 640x480."
        xrandr --fb 640x480
        xrandr --query
        exit 0
    fi
    echo "No connected display output found."
    xrandr --query
    exit 1
fi

echo "Restoring automatic mode for: $output"
xrandr --output "$output" --auto
xrandr --query
"""
    return (
        remote_script
        .replace("__OUTPUT__", quote_for_bash(output))
        .replace("__FRAMEBUFFER_FALLBACK__", quote_for_bash("1" if framebuffer_fallback else "0"))
    )
