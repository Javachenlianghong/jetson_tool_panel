"""Continuous remote resource monitor backed by a separate SSH process."""

import re
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from core.command_runner import decode_process_output
from services import ssh_service


MONITOR_SCRIPT = r"""
if command -v tegrastats >/dev/null 2>&1; then
    exec tegrastats --interval 2000
fi

prev_total=0
prev_idle=0
while true; do
    if [ -r /proc/stat ]; then
        read _ user nice system idle iowait irq softirq steal _rest < /proc/stat
        idle_all=$((idle + iowait))
        non_idle=$((user + nice + system + irq + softirq + steal))
        total=$((idle_all + non_idle))
        if [ "$prev_total" -gt 0 ]; then
            total_delta=$((total - prev_total))
            idle_delta=$((idle_all - prev_idle))
            cpu_value="$(awk -v total="$total_delta" -v idle="$idle_delta" 'BEGIN { if (total > 0) printf "%.1f%%", (total - idle) * 100 / total; else print "未知" }')"
        else
            cpu_value="采集中"
        fi
        prev_total=$total
        prev_idle=$idle_all
    else
        cpu_value="未知"
    fi

    memory_value="$(free -m 2>/dev/null | awk '/Mem:/ { if ($2 > 0) printf "%s/%s MB (%.1f%%)", $3, $2, $3 * 100 / $2 }' || true)"
    [ -n "$memory_value" ] || memory_value="未知"

    temp_value="未知"
    for zone in /sys/class/thermal/thermal_zone*; do
        [ -r "$zone/temp" ] || continue
        zone_name="$(cat "$zone/type" 2>/dev/null || basename "$zone")"
        raw_temp="$(cat "$zone/temp" 2>/dev/null || true)"
        printf "%s" "$raw_temp" | grep -Eq '^-?[0-9]+$' || continue
        temp_value="$(awk -v temp="$raw_temp" -v name="$zone_name" 'BEGIN { if (temp > 1000 || temp < -1000) printf "%s %.1fC", name, temp / 1000; else printf "%s %sC", name, temp }')"
        break
    done

    gpu_value="未知"
    for busy in /sys/devices/gpu.0/load /sys/devices/*gpu*/load; do
        [ -r "$busy" ] || continue
        raw_gpu="$(cat "$busy" 2>/dev/null || true)"
        printf "%s" "$raw_gpu" | grep -Eq '^[0-9]+$' || continue
        gpu_value="$(awk -v load="$raw_gpu" 'BEGIN { printf "%.1f%%", load / 10 }')"
        break
    done

    printf 'MON|cpu=%s|memory=%s|gpu=%s|temperature=%s\n' "$cpu_value" "$memory_value" "$gpu_value" "$temp_value"
    sleep 2
done
"""


def _average_cpu_percent(cpu_text):
    values = [int(value) for value in re.findall(r"(\d+)%@", cpu_text or "")]
    if not values:
        return cpu_text.strip() if cpu_text else "未知"
    return "{:.1f}%".format(sum(values) / len(values))


def _format_memory(used, total):
    try:
        used_value = int(used)
        total_value = int(total)
    except (TypeError, ValueError):
        return "未知"
    if total_value <= 0:
        return "{} MB".format(used_value)
    return "{}/{} MB ({:.1f}%)".format(used_value, total_value, used_value * 100 / total_value)


def _max_temperature(temp_pairs):
    if not temp_pairs:
        return "未知"
    normalized = []
    for name, value in temp_pairs:
        try:
            normalized.append((name, float(value)))
        except (TypeError, ValueError):
            pass
    if not normalized:
        return "未知"
    name, value = max(normalized, key=lambda item: item[1])
    return "{} {:.1f}C".format(name, value)


def parse_monitor_line(line):
    text = str(line or "").strip()
    if not text:
        return None

    if text.startswith("MON|"):
        data = {}
        for part in text.split("|")[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                data[key] = value or "未知"
        return {
            "cpu": data.get("cpu", "未知"),
            "memory": data.get("memory", "未知"),
            "gpu": data.get("gpu", "未知"),
            "temperature": data.get("temperature", "未知"),
            "raw": text,
        }

    result = {"cpu": "未知", "memory": "未知", "gpu": "未知", "temperature": "未知", "raw": text}
    matched = False

    memory_match = re.search(r"\bRAM\s+(\d+)/(\d+)MB", text)
    if memory_match:
        result["memory"] = _format_memory(memory_match.group(1), memory_match.group(2))
        matched = True

    cpu_match = re.search(r"\bCPU\s+\[([^\]]+)\]", text)
    if cpu_match:
        result["cpu"] = _average_cpu_percent(cpu_match.group(1))
        matched = True

    gpu_match = re.search(r"\bGR3D_FREQ\s+([0-9]+)%", text)
    if gpu_match:
        result["gpu"] = "{}%".format(gpu_match.group(1))
        matched = True

    temp_pairs = re.findall(r"\b([A-Za-z0-9_]+)@([0-9]+(?:\.[0-9]+)?)C", text)
    if temp_pairs:
        result["temperature"] = _max_temperature(temp_pairs)
        matched = True

    return result if matched else None


class ResourceMonitorWorker(QThread):
    metrics = pyqtSignal(dict)
    status = pyqtSignal(str)

    def __init__(self, remote, parent=None):
        super().__init__(parent)
        self.remote = remote
        self._process = None
        self._stopping = False

    def run(self):
        command = ["ssh"] + ssh_service.ssh_options(batch_mode=True) + [self.remote, MONITOR_SCRIPT]
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.status.emit("监控启动失败: {}".format(exc))
            return

        self.status.emit("监控中: {}".format(self.remote))
        assert self._process.stdout is not None
        for raw_line in self._process.stdout:
            if self._stopping:
                break
            line = decode_process_output(raw_line)
            parsed = parse_monitor_line(line)
            if parsed:
                self.metrics.emit(parsed)
            elif line:
                self.status.emit(line)

        return_code = self._process.wait()
        if not self._stopping:
            if return_code != 0:
                self.status.emit("监控已停止: {}".format(return_code))
            else:
                self.status.emit("监控已停止")

    def stop(self):
        self._stopping = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except OSError:
                pass
