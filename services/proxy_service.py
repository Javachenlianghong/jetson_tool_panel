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
