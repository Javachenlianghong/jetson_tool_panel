"""SSH and SCP command helpers."""

import os
import sys

from core.command_runner import quote_for_powershell


def ssh_options(batch_mode=True):
    options = ["-n"]
    if batch_mode:
        options.extend(["-o", "BatchMode=yes"])
    options.extend([
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ])
    return options


def test_ssh_command(remote):
    return ["ssh"] + ssh_options(batch_mode=True) + [
        remote,
        "echo Jetson SSH OK && uname -a",
    ]


def remote_ssh_command(remote, remote_command, batch_mode=True):
    return ["ssh"] + ssh_options(batch_mode=batch_mode) + [remote, remote_command]


def upload_proxy_script_command(script_path, remote):
    return ["scp", "-O", str(script_path), "{}:~/jetson-proxy-session.sh".format(remote)]


def pull_project_command(remote, remote_path):
    source = "{}:{}".format(remote, remote_path)
    return ["scp", "-O", "-r", source, "."]


def python_launcher():
    if os.name == "nt":
        return ["py", "-3"]
    return [sys.executable]


def sync_command(sync_script, remote, remote_path, init=False, full=False, dry_run=False, no_delete=False):
    command = python_launcher() + [
        str(sync_script),
        "--remote",
        remote,
        "--remote-path",
        remote_path,
    ]
    if init:
        command.append("--init")
    if full:
        command.append("--full")
    if dry_run:
        command.append("--dry-run")
    if no_delete:
        command.append("--no-delete")
    return command


def ssh_key_setup_script(remote):
    remote_ps = quote_for_powershell(remote)
    return r"""
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Jetson SSH Key Setup'

try {
    $remote = __REMOTE__
    $sshDir = Join-Path $env:USERPROFILE '.ssh'
    $key = Join-Path $sshDir 'id_ed25519'
    $pub = "$key.pub"

    Write-Host ''
    Write-Host 'Jetson SSH Key Setup'
    Write-Host "Remote: $remote"
    Write-Host ''

    if (-not (Test-Path -LiteralPath $sshDir)) {
        New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
    }

    if (-not (Test-Path -LiteralPath $pub)) {
        if (Test-Path -LiteralPath $key) {
            Write-Host "Public key is missing. Rebuilding it from: $key"
            & ssh-keygen -y -f $key | Set-Content -LiteralPath $pub -Encoding ascii
        } else {
            Write-Host "Generating local SSH key: $key"
            & ssh-keygen -t ed25519 -N '' -f $key
        }
    } else {
        Write-Host "Using existing public key: $pub"
    }

    if (-not (Test-Path -LiteralPath $pub)) {
        throw "Public key was not created: $pub"
    }

    Write-Host ''
    Write-Host 'Next step needs the Jetson password.'
    Write-Host 'The password prompt may not show typed characters; that is normal.'
    Write-Host ''

    $remotePub = "/tmp/codex-ssh-key-$([guid]::NewGuid().ToString('N')).pub"
    $scpTarget = $remote + ':' + $remotePub

    Write-Host "Uploading public key to: $scpTarget"
    & scp -O -o StrictHostKeyChecking=accept-new $pub $scpTarget

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload public key to Jetson."
    }

    Write-Host ''
    Write-Host 'Installing public key into ~/.ssh/authorized_keys...'
    $installCommand = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; cat $remotePub >> ~/.ssh/authorized_keys; sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; rm -f $remotePub"
    & ssh -o StrictHostKeyChecking=accept-new $remote $installCommand

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install public key on Jetson."
    }

    Write-Host ''
    Write-Host 'Testing key login without password...'
    & ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new $remote "echo Jetson SSH key OK && uname -a"

    if ($LASTEXITCODE -ne 0) {
        throw "SSH key test failed."
    }

    Write-Host ''
    Write-Host 'Done. SSH key login is configured.'
} catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ''
Read-Host 'Press Enter to close this window'
""".replace("__REMOTE__", remote_ps)
