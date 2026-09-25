# SafeEject Windows Task Scheduler Hook
# Registers scheduled tasks triggered by Windows Kernel-Power Event 42 (Sleep) and 107 (Wake)

param (
    [switch]$Uninstall
)

$TaskNameSleep = "SafeEject_PreSleep"
$TaskNameWake = "SafeEject_PostWake"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskNameSleep -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskNameWake -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "SafeEject Windows Scheduled Tasks uninstalled successfully."
    exit 0
}

# 1. Locate executable (prefer standalone safeeject_cli.exe over python script)
$CandidateExes = @(
    "$PSScriptRoot\safeeject_cli.exe",
    "$PSScriptRoot\..\..\safeeject_cli.exe",
    "$env:LOCALAPPDATA\Programs\SafeDriveEjector\safeeject_cli.exe"
)

$CliExe = $null
foreach ($cand in $CandidateExes) {
    if (Test-Path $cand) {
        $CliExe = (Resolve-Path $cand).Path
        break
    }
}

if ($CliExe) {
    Write-Host "Using standalone CLI executable: $CliExe"
    $ActionSleep = New-ScheduledTaskAction -Execute $CliExe -Argument "eject-all"
    $ActionWake  = New-ScheduledTaskAction -Execute $CliExe -Argument "remount-all"
} else {
    $PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    $ActionScript = "$PSScriptRoot\..\..\main.py"
    if (-not $PythonExe -or -not (Test-Path $ActionScript)) {
        Write-Error "Neither standalone safeeject_cli.exe nor python.exe with main.py was found."
        exit 1
    }
    Write-Host "Using Python script runner: $PythonExe $ActionScript"
    $ActionSleep = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ActionScript`" eject-all"
    $ActionWake  = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ActionScript`" remount-all"
}

Write-Host "Registering SafeEject Sleep & Wake Scheduled Tasks..."

# Trigger on System Sleep: Microsoft-Windows-Kernel-Power Event ID 42
$CimTriggerSleep = New-CimInstance -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler -ClientOnly
$CimTriggerSleep.Subscription = @"
<QueryList>
  <Query Id="0" Path="System">
    <Select Path="System">*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=42]]</Select>
  </Query>
</QueryList>
"@
$CimTriggerSleep.Enabled = $true

# Trigger on System Wake: Microsoft-Windows-Kernel-Power Event ID 107
$CimTriggerWake = New-CimInstance -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler -ClientOnly
$CimTriggerWake.Subscription = @"
<QueryList>
  <Query Id="0" Path="System">
    <Select Path="System">*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=107]]</Select>
  </Query>
</QueryList>
"@
$CimTriggerWake.Enabled = $true

Register-ScheduledTask -TaskName $TaskNameSleep -Action $ActionSleep -Trigger $CimTriggerSleep -Force
Register-ScheduledTask -TaskName $TaskNameWake -Action $ActionWake -Trigger $CimTriggerWake -Force

Write-Host "SafeEject Task Scheduler hooks installed successfully!"
