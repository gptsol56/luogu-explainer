<#
.SYNOPSIS
    把 luogu_punch 注册成 Windows 计划任务, 每天定时打卡。
.DESCRIPTION
    需要先把凭据写进用户级环境变量, 否则任务会因缺凭据失败:
        setx LUOGU_CLIENT_ID <你的 __client_id>
        setx LUOGU_UID       <你的 _uid>
    用法:
        powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
        powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -At 08:30
        powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -DryRun
        powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string] $TaskName   = "LuoguPunch",
    [string] $At         = "10:00",
    [string] $Python     = "python",
    [string] $ScriptPath,
    [switch] $Remove,
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

if (-not $ScriptPath) {
    $ScriptPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'luogu_punch.py'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "找不到 luogu_punch.py : $ScriptPath"
}

if ($Remove) {
    schtasks /Delete /TN $TaskName /F
    Write-Host "已删除计划任务 : $TaskName"
    return
}

if ($At -notmatch '^\d{1,2}:\d{2}$') {
    throw "-At 格式应为 HH:MM , 收到 : $At"
}

$missing = @()
foreach ($varName in @('LUOGU_CLIENT_ID', 'LUOGU_UID')) {
    $value = [Environment]::GetEnvironmentVariable($varName, 'User')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($varName, 'Process') }
    if (-not $value) { $missing += $varName }
}
if ($missing.Count -gt 0) {
    Write-Warning ("未检测到环境变量 : " + ($missing -join ' , ') + " ; 计划任务会因缺凭据失败, 请先 setx 后重开终端")
}

$runCmd = '"{0}" "{1}"' -f $Python, $ScriptPath
Write-Host "计划任务名 : $TaskName"
Write-Host "  执行     : $runCmd"
Write-Host "  时间     : 每天 $At"
Write-Host "  工作目录 : $(Split-Path -Parent $ScriptPath)"
if ($DryRun) {
    Write-Host "  (DryRun, 未真正创建)"
    return
}

schtasks /Create /TN $TaskName /SC DAILY /ST $At /TR $runCmd /F
Write-Host "创建成功。立即试跑一次 : schtasks /Run /TN $TaskName"