# Source this file on Jetson:
#   source ./jetson-proxy-session.sh 192.168.1.11 7897
#
# Disable in the current shell:
#   proxyoff
# or:
#   source ./jetson-proxy-session.sh off
#
# This script only changes the current shell session. It does not write
# ~/.bashrc, ~/.profile, ~/.gitconfig, or apt configuration files.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "Do not run this script directly."
    echo "Use: source $0 [WINDOWS_IP] [PORT]"
    echo "Example: source $0 192.168.1.11 7897"
    exit 1
fi

proxyoff() {
    unset http_proxy https_proxy ftp_proxy all_proxy no_proxy
    unset HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY NO_PROXY
    unset WINDOWS_CLASH_PROXY_HOST WINDOWS_CLASH_PROXY_PORT WINDOWS_CLASH_PROXY_URL
    unset -f gitp aptp curlp wgetp pipp proxystatus proxyoff 2>/dev/null || true
    echo "Proxy disabled for this shell."
}

case "${1:-on}" in
    off|disable|stop)
        proxyoff
        return 0
        ;;
esac

export WINDOWS_CLASH_PROXY_HOST="${1:-192.168.1.11}"
export WINDOWS_CLASH_PROXY_PORT="${2:-7897}"
export WINDOWS_CLASH_PROXY_URL="http://${WINDOWS_CLASH_PROXY_HOST}:${WINDOWS_CLASH_PROXY_PORT}"

export http_proxy="$WINDOWS_CLASH_PROXY_URL"
export https_proxy="$WINDOWS_CLASH_PROXY_URL"
export ftp_proxy="$WINDOWS_CLASH_PROXY_URL"
export all_proxy="$WINDOWS_CLASH_PROXY_URL"

export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export FTP_PROXY="$ftp_proxy"
export ALL_PROXY="$all_proxy"

export no_proxy="localhost,127.0.0.1,::1,${WINDOWS_CLASH_PROXY_HOST},192.168.1.0/24"
export NO_PROXY="$no_proxy"

gitp() {
    git -c "http.proxy=$http_proxy" -c "https.proxy=$https_proxy" "$@"
}

aptp() {
    sudo env \
        "http_proxy=$http_proxy" \
        "https_proxy=$https_proxy" \
        "HTTP_PROXY=$HTTP_PROXY" \
        "HTTPS_PROXY=$HTTPS_PROXY" \
        "no_proxy=$no_proxy" \
        "NO_PROXY=$NO_PROXY" \
        apt "$@"
}

curlp() {
    curl -x "$http_proxy" "$@"
}

wgetp() {
    wget -e "use_proxy=yes" \
        -e "http_proxy=$http_proxy" \
        -e "https_proxy=$https_proxy" \
        "$@"
}

pipp() {
    python3 -m pip --proxy "$http_proxy" "$@"
}

proxystatus() {
    echo "http_proxy=$http_proxy"
    echo "https_proxy=$https_proxy"
    echo "no_proxy=$no_proxy"
    if command -v curl >/dev/null 2>&1; then
        curl -I -L --max-time 10 -x "$http_proxy" https://www.google.com/generate_204
    fi
}

echo "Proxy enabled for this shell only: $WINDOWS_CLASH_PROXY_URL"
echo "Quick test: proxystatus"
echo "Git example: gitp clone --depth 1 https://github.com/Qengineering/YoloV8-TensorRT-Jetson_Nano.git"
echo "Apt example: aptp update"
echo "Disable now: proxyoff"

