param(
    [int]$Port = 7897,
    [string]$RemoteAddress = "192.168.1.0/24",
    [string]$Program = "C:\Program Files\Clash Verge\verge-mihomo.exe",
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$ruleName = "Codex-Clash-Verge-LAN-Proxy-$Port-Temp"

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-TempRule {
    foreach ($store in @("ActiveStore", "PersistentStore")) {
        try {
            Get-NetFirewallRule -PolicyStore $store -Name $ruleName -ErrorAction SilentlyContinue |
                Remove-NetFirewallRule -ErrorAction SilentlyContinue
        } catch {
            # Ignore stores that are not writable on this Windows build.
        }
    }
}

if (-not (Test-Admin)) {
    throw "Run this script from an Administrator PowerShell."
}

if ($Stop) {
    Remove-TempRule
    Write-Host "Removed temporary firewall rule: $ruleName"
    exit 0
}

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listeners) {
    Write-Warning "No process is listening on TCP port $Port. Start Clash Verge first."
} else {
    $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $pids) {
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            Write-Host "Listening process: $($process.ProcessName) pid=$processId"
        } catch {
            Write-Host "Listening process pid=$processId"
        }
    }
}

Remove-TempRule

$ruleArgs = @{
    PolicyStore   = "ActiveStore"
    Name          = $ruleName
    DisplayName   = "Temporary Clash Verge LAN Proxy $Port"
    Direction     = "Inbound"
    Action        = "Allow"
    Protocol      = "TCP"
    LocalPort     = $Port
    RemoteAddress = $RemoteAddress
    Profile       = "Any"
}

if (Test-Path -LiteralPath $Program) {
    $ruleArgs.Program = $Program
} else {
    Write-Warning "Program not found: $Program"
    Write-Warning "Creating a port-only rule for TCP $Port instead."
}

New-NetFirewallRule @ruleArgs | Out-Null

$ipv4 = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
    Select-Object IPAddress, InterfaceAlias

Write-Host ""
Write-Host "Temporary firewall rule enabled."
Write-Host "Rule name: $ruleName"
Write-Host "Port: $Port"
Write-Host "Allowed remote address: $RemoteAddress"
Write-Host "This rule is in ActiveStore and is intended to disappear after reboot/firewall restart."
Write-Host ""
Write-Host "Windows IPv4 addresses:"
$ipv4 | Format-Table -AutoSize
Write-Host ""
Write-Host "Jetson command example:"
Write-Host "source ./jetson-proxy-session.sh 192.168.1.11 $Port"
Write-Host ""
Write-Host "To remove before reboot:"
Write-Host ".\windows-clash-lan-temp.ps1 -Stop"
