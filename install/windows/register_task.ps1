# SafeEject Windows Task Scheduler Hook
# Registers scheduled tasks triggered by Windows Kernel-Power Event 42 (Sleep) and 107 (Wake)

param (
    [switch]$Uninstall
)

$ActionScript = "$PSScriptRoot\..\..\main.py"
$PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Error "Python executable not found in PATH."
    exit 1
}

$TaskNameSleep = "SafeEject_PreSleep"
$TaskNameWake = "SafeEject_PostWake"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskNameSleep -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskNameWake -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "SafeEject Windows Scheduled Tasks uninstalled successfully."
    exit 0
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

# Action for Sleep: python.exe main.py eject-all
$ActionSleep = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ActionScript`" eject-all"

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

# Action for Wake: python.exe main.py remount-all
$ActionWake = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ActionScript`" remount-all"

Register-ScheduledTask -TaskName $TaskNameSleep -Action $ActionSleep -Trigger $CimTriggerSleep -Force
Register-ScheduledTask -TaskName $TaskNameWake -Action $ActionWake -Trigger $CimTriggerWake -Force

Write-Host "SafeEject Task Scheduler hooks installed successfully!"
