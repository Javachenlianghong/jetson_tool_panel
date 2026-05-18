"""Windows Clash proxy command helpers."""

from core.command_runner import quote_for_powershell


def firewall_args(script_path, port, remote_address, program="", include_stop=False):
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Port",
        str(port),
        "-RemoteAddress",
        remote_address,
    ]
    if program:
        args.extend(["-Program", program])
    if include_stop:
        args.append("-Stop")
    return args


def elevated_firewall_args(script_path, port, remote_address, program=""):
    arguments = [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        quote_for_powershell(str(script_path)),
        "-Port",
        str(port),
        "-RemoteAddress",
        quote_for_powershell(remote_address),
    ]
    if program:
        arguments.extend(["-Program", quote_for_powershell(program)])

    start_process_args = " ".join(arguments)
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Start-Process powershell -Verb RunAs -ArgumentList {}".format(
            quote_for_powershell(start_process_args)
        ),
    ]


def proxy_command_text(windows_ip, port):
    return "source ./jetson-proxy-session.sh {} {}".format(windows_ip, port)


def disable_jetson_proxy_command():
    return r"""
unset http_proxy https_proxy ftp_proxy all_proxy no_proxy
unset HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY NO_PROXY
echo "Cleared proxy environment variables for this shell."

git config --global --unset-all http.proxy 2>/dev/null || true
git config --global --unset-all https.proxy 2>/dev/null || true
git config --global --unset-all core.gitproxy 2>/dev/null || true
echo "Cleared git global proxy settings if present."

tmp="${TMPDIR:-/tmp}/jtp-disable-proxy-$$.sh"
cat > "$tmp" <<'JTP_PROXY_OFF'
#!/bin/sh
set -eu
backup_suffix=".jtp-proxy-bak-$(date +%Y%m%d%H%M%S)"
changed=0

clean_file() {
    path="$1"
    [ -f "$path" ] || return 0
    if grep -Eqi 'Acquire::.*Proxy|(^|_)(http|https|ftp|all)_proxy=|(^|_)(HTTP|HTTPS|FTP|ALL)_PROXY=' "$path"; then
        cp -a "$path" "$path$backup_suffix"
        sed -i -E \
            -e '/Acquire::.*Proxy/Id' \
            -e '/(^|_)(http|https|ftp|all)_proxy=/Id' \
            -e '/(^|_)(HTTP|HTTPS|FTP|ALL)_PROXY=/d' \
            "$path"
        if [ ! -s "$path" ]; then
            rm -f "$path"
        fi
        echo "cleaned $path"
        changed=$((changed + 1))
    fi
}

clean_file /etc/apt/apt.conf
for path in /etc/apt/apt.conf.d/*; do
    clean_file "$path"
done
clean_file /etc/environment
for path in /etc/profile.d/*proxy*.sh /etc/profile.d/*Proxy*.sh; do
    clean_file "$path"
done

echo "changed_files=$changed"
JTP_PROXY_OFF

echo "Cleaning system proxy config with sudo..."
sudo sh "$tmp"
rm -f "$tmp"

echo "Remaining proxy config references:"
grep -RniE 'Acquire::.*Proxy|(^|_)(http|https|ftp|all)_proxy=' \
    /etc/apt/apt.conf /etc/apt/apt.conf.d /etc/environment /etc/profile.d 2>/dev/null || true
echo "Jetson proxy config cleanup done."
"""
