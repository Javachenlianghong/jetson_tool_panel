"""Generic remote development commands for Linux edge devices."""

from core.command_runner import quote_for_bash


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
