"""Remote device health collection helpers."""


UNKNOWN = "未知"


def health_command():
    return r"""
echo __HEALTH_BEGIN__
kv() {
    key="$1"
    shift
    value="$*"
    if [ -z "$value" ]; then
        value="未知"
    fi
    printf 'KV|%s|%s\n' "$key" "$value"
}

hostname_value="$(hostname 2>/dev/null || true)"
kernel_value="$(uname -r 2>/dev/null || true)"
arch_value="$(uname -m 2>/dev/null || true)"
uname_value="$(uname -a 2>/dev/null || true)"
uptime_value="$(uptime -p 2>/dev/null || awk '{printf "%.0f 秒", $1}' /proc/uptime 2>/dev/null || true)"
load_value="$(cat /proc/loadavg 2>/dev/null | awk '{print $1 " " $2 " " $3}' || true)"
memory_value="$(free -m 2>/dev/null | awk '/Mem:/ { if ($2 > 0) printf "%s/%s MB (%.1f%%)", $3, $2, $3 * 100 / $2 }' || true)"
disk_value="$(df -h / 2>/dev/null | awk 'NR==2 {print $3 "/" $2 " (" $5 ")"}' || true)"
network_value="$(ip -o -4 addr show scope global 2>/dev/null | awk '{print $2 " " $4}' | tr '\n' '; ' | sed 's/; $//' || true)"

device_type="Linux"
device_detail="$uname_value"
if [ -f /etc/nv_tegra_release ] || [ -x /usr/bin/tegrastats ] || [ -e /sys/devices/gpu.0 ]; then
    device_type="Jetson"
    device_detail="$(cat /etc/nv_tegra_release 2>/dev/null || echo "$uname_value")"
else
    compatible="$(tr '\0' '\n' < /proc/device-tree/compatible 2>/dev/null || true)"
    cpu_info="$(lscpu 2>/dev/null || true)"
    if printf "%s\n%s\n%s\n" "$compatible" "$cpu_info" "$uname_value" | grep -Eiq 'rockchip|rk3588'; then
        device_type="RK3588"
        device_detail="$(printf "%s\n%s" "$compatible" "$cpu_info" | grep -Eim1 'rockchip|rk3588' || echo "$uname_value")"
    fi
fi

cpu_value="未知"
if [ -r /proc/stat ]; then
    read cpu user nice system idle iowait irq softirq steal rest < /proc/stat
    prev_idle=$((idle + iowait))
    prev_non_idle=$((user + nice + system + irq + softirq + steal))
    prev_total=$((prev_idle + prev_non_idle))
    sleep 0.2
    read cpu user nice system idle iowait irq softirq steal rest < /proc/stat
    idle_all=$((idle + iowait))
    non_idle=$((user + nice + system + irq + softirq + steal))
    total=$((idle_all + non_idle))
    total_delta=$((total - prev_total))
    idle_delta=$((idle_all - prev_idle))
    cpu_value="$(awk -v total="$total_delta" -v idle="$idle_delta" 'BEGIN { if (total > 0) printf "%.1f%%", (total - idle) * 100 / total; else print "未知" }')"
fi

kv device_type "$device_type"
kv device_detail "$device_detail"
kv hostname "$hostname_value"
kv kernel "$kernel_value"
kv arch "$arch_value"
kv uptime "$uptime_value"
kv load "$load_value"
kv cpu "$cpu_value"
kv memory "$memory_value"
kv disk "$disk_value"
kv network "$network_value"

for zone in /sys/class/thermal/thermal_zone*; do
    [ -e "$zone/temp" ] || continue
    zone_name="$(cat "$zone/type" 2>/dev/null || basename "$zone")"
    raw_temp="$(cat "$zone/temp" 2>/dev/null || true)"
    printf "%s" "$raw_temp" | grep -Eq '^-?[0-9]+$' || continue
    if [ "$raw_temp" -gt 1000 ] 2>/dev/null || [ "$raw_temp" -lt -1000 ] 2>/dev/null; then
        temp_value="$(awk -v temp="$raw_temp" 'BEGIN { printf "%.1f C", temp / 1000 }')"
    else
        temp_value="${raw_temp} C"
    fi
    printf 'TEMP|%s|%s\n' "$zone_name" "$temp_value"
done

if command -v tegrastats >/dev/null 2>&1; then
    tegra_line="$(timeout 3 tegrastats --interval 1000 2>/dev/null | head -n 1 || true)"
    kv tegrastats "$tegra_line"
fi

if command -v rknn_server >/dev/null 2>&1; then
    kv accelerator "检测到 rknn_server"
elif ls /dev/rknpu* >/dev/null 2>&1; then
    kv accelerator "检测到 RKNPU 设备节点"
else
    kv accelerator "未知"
fi

echo __HEALTH_END__
"""


def parse_health_output(lines):
    data = {
        "device_type": UNKNOWN,
        "device_detail": UNKNOWN,
        "hostname": UNKNOWN,
        "kernel": UNKNOWN,
        "arch": UNKNOWN,
        "uptime": UNKNOWN,
        "load": UNKNOWN,
        "cpu": UNKNOWN,
        "memory": UNKNOWN,
        "disk": UNKNOWN,
        "network": UNKNOWN,
        "tegrastats": UNKNOWN,
        "accelerator": UNKNOWN,
    }
    temperatures = []
    in_block = False

    for raw_line in lines:
        line = raw_line.strip()
        if line == "__HEALTH_BEGIN__":
            in_block = True
            continue
        if line == "__HEALTH_END__":
            break
        if not in_block:
            continue
        if line.startswith("KV|"):
            parts = line.split("|", 2)
            if len(parts) == 3:
                data[parts[1]] = parts[2] or UNKNOWN
        elif line.startswith("TEMP|"):
            parts = line.split("|", 2)
            if len(parts) == 3:
                temperatures.append("{} {}".format(parts[1], parts[2]))

    data["temperature"] = "; ".join(temperatures) if temperatures else UNKNOWN
    return data
