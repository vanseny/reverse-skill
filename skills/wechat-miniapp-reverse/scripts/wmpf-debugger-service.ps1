param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Start', 'Stop', 'Status')]
  [string]$Action,
  [string]$Root,
  [switch]$UseEnvironmentRoot,
  [string]$LeaseToken
)

$ErrorActionPreference = 'Stop'
$managedPorts = @(9421, 62000)
$stateBase = if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
  [System.IO.Path]::GetTempPath()
} else {
  $env:LOCALAPPDATA
}
$stateDirectory = Join-Path $stateBase 'pi\wechat-miniapp-reverse'
$statePath = Join-Path $stateDirectory 'wmpf-debugger-state.json'

function Write-Failure {
  param([string]$Message, [int]$Code)
  [Console]::Error.WriteLine($Message)
  exit $Code
}

function Get-ManagedState {
  if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return $null }
  try {
    return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Remove-ManagedState {
  Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
}

function Test-ProcessIdentity {
  param($State)
  if ($null -eq $State -or $null -eq $State.launcherPid -or
      $null -eq $State.launcherStartUtcTicks) {
    return $false
  }

  try {
    $process = Get-Process -Id ([int]$State.launcherPid)
    $actualTicks = $process.StartTime.ToUniversalTime().Ticks
    return $actualTicks -eq [long]$State.launcherStartUtcTicks
  } catch {
    return $false
  }
}

function Get-ProcessStartTicks {
  param([int]$ProcessId)
  try {
    return (Get-Process -Id $ProcessId).StartTime.ToUniversalTime().Ticks
  } catch {
    return $null
  }
}

function Get-CimProcessStartTicks {
  param($Process)
  try {
    if ($Process.CreationDate -is [DateTime]) {
      return $Process.CreationDate.ToUniversalTime().Ticks
    }
    return [System.Management.ManagementDateTimeConverter]::ToDateTime(
      [string]$Process.CreationDate
    ).ToUniversalTime().Ticks
  } catch {
    return $null
  }
}

function Test-SameProcessStartTicks {
  param([long]$Left, [long]$Right)
  return [Math]::Abs($Left - $Right) -le [TimeSpan]::TicksPerMillisecond
}

function Test-ProcessExited {
  param($Process, [int]$ProcessId)
  try {
    if ($null -ne $Process -and [bool]$Process.HasExited) { return $true }
  } catch {
    return $true
  }
  return ($null -eq (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue))
}

function Get-ListenerProcessIds {
  param([int]$Port)
  return @(
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
      ForEach-Object { [int]$_.OwningProcess } |
      Where-Object { $_ -gt 0 } |
      Sort-Object -Unique
  )
}

function Test-IsDescendantProcess {
  param(
    [int]$ProcessId,
    [int]$AncestorProcessId,
    [long]$AncestorStartUtcTicks
  )
  $currentId = $ProcessId
  $currentTicks = Get-ProcessStartTicks $currentId
  if ($null -eq $currentTicks -or $currentTicks -lt $AncestorStartUtcTicks) { return $false }
  $seen = @{}
  for ($depth = 0; $depth -lt 32; $depth++) {
    if ($currentId -eq $AncestorProcessId) {
      return $currentTicks -eq $AncestorStartUtcTicks
    }
    if ($currentId -le 0 -or $seen.ContainsKey($currentId)) { return $false }
    $seen[$currentId] = $true
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $currentId" -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $false }
    $parentId = [int]$process.ParentProcessId
    $parentTicks = Get-ProcessStartTicks $parentId
    if ($null -eq $parentTicks -or $parentTicks -gt $currentTicks) { return $false }
    $currentId = $parentId
    $currentTicks = $parentTicks
  }
  return $false
}

function Get-AllListenerProcessIds {
  $ids = foreach ($port in $managedPorts) {
    Get-ListenerProcessIds $port
  }
  return @($ids | Sort-Object -Unique)
}

function Get-UnmanagedListenerProcessIds {
  param($State)
  if ($null -eq $State -or $null -eq $State.launcherPid) {
    return @(Get-AllListenerProcessIds)
  }

  $ancestorId = [int]$State.launcherPid
  $ancestorTicks = [long]$State.launcherStartUtcTicks
  return @(
    Get-AllListenerProcessIds |
      Where-Object { -not (Test-IsDescendantProcess $_ $ancestorId $ancestorTicks) }
  )
}

function Test-WmpfNodeIdentity {
  param([int]$ProcessId, $State)
  try {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
    if ($null -eq $process -or [string]$process.Name -ine 'node.exe') { return $false }
    $commandLine = [string]$process.CommandLine
    $rootPrefix = ([string]$State.root).TrimEnd('\') + '\'
    return $commandLine.IndexOf($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
      ($commandLine -match 'ts-node' -or $commandLine -match 'src[\\/]index\.ts')
  } catch {
    return $false
  }
}

function Get-ManagedDescendantIdentities {
  param($State, [object[]]$KnownIdentities = @())
  $snapshot = @(Get-CimInstance Win32_Process)
  $childrenByParent = @{}
  foreach ($process in $snapshot) {
    $parentKey = [string][int]$process.ParentProcessId
    if (-not $childrenByParent.ContainsKey($parentKey)) {
      $childrenByParent[$parentKey] = @()
    }
    $childrenByParent[$parentKey] += $process
  }

  $queue = New-Object System.Collections.Queue
  $queue.Enqueue([pscustomobject]@{
    Id = [int]$State.launcherPid
    StartTicks = [long]$State.launcherStartUtcTicks
    Depth = 0
  })
  $seen = @{}
  $seen[[string][int]$State.launcherPid] = $true
  foreach ($identity in $KnownIdentities) {
    $identityKey = [string][int]$identity.Id
    if ($seen.ContainsKey($identityKey)) { continue }
    $seen[$identityKey] = $true
    $queue.Enqueue($identity)
  }
  $result = @()

  while ($queue.Count -gt 0) {
    $parent = $queue.Dequeue()
    $liveParentTicks = Get-ProcessStartTicks $parent.Id
    if ($null -ne $liveParentTicks -and $liveParentTicks -ne [long]$parent.StartTicks) {
      continue
    }
    $parentKey = [string]$parent.Id
    if (-not $childrenByParent.ContainsKey($parentKey)) { continue }
    foreach ($child in $childrenByParent[$parentKey]) {
      $childId = [int]$child.ProcessId
      $childKey = [string]$childId
      if ($childId -le 0 -or $seen.ContainsKey($childKey)) { continue }
      $snapshotTicks = Get-CimProcessStartTicks $child
      $childTicks = Get-ProcessStartTicks $childId
      if ($null -eq $snapshotTicks -or $null -eq $childTicks -or
          -not (Test-SameProcessStartTicks $snapshotTicks $childTicks) -or
          $childTicks -lt $parent.StartTicks) {
        continue
      }
      $identity = [pscustomobject]@{
        Id = $childId
        StartTicks = [long]$childTicks
        Depth = $parent.Depth + 1
      }
      $seen[$childKey] = $true
      $result += $identity
      $queue.Enqueue($identity)
    }
  }
  return @($result)
}

function Stop-ExactProcess {
  param($Identity)
  $processId = [int]$Identity.Id
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($null -eq $process) { return $true }

  # PowerShell 5.1 turns a throwing property getter into $null, so never chain
  # methods off $process.StartTime directly; Get-ProcessStartTicks isolates that.
  $ticks = Get-ProcessStartTicks $processId
  if ($null -eq $ticks) {
    if (Test-ProcessExited $process $processId) { return $true }
    return $false
  }
  if (-not (Test-SameProcessStartTicks $ticks ([long]$Identity.StartTicks))) {
    return $false
  }
  Stop-Process -InputObject $process -Force -ErrorAction SilentlyContinue
  try {
    $process.WaitForExit(2000) | Out-Null
  } catch {}
  return (Test-ProcessExited $process $processId)
}

function Stop-ManagedProcessTree {
  param($State)
  $launcher = [pscustomobject]@{
    Id = [int]$State.launcherPid
    StartTicks = [long]$State.launcherStartUtcTicks
    Depth = 0
  }
  $known = @()
  $refused = @()
  for ($pass = 0; $pass -lt 5; $pass++) {
    $discovered = @(Get-ManagedDescendantIdentities $State $known)
    $identityMap = @{}
    foreach ($identity in @($known + $discovered)) {
      $identityMap["$($identity.Id):$($identity.StartTicks)"] = $identity
    }
    $known = @($identityMap.Values)
    $active = @(
      $known | Where-Object {
        (Get-ProcessStartTicks $_.Id) -eq [long]$_.StartTicks
      }
    )
    if ($active.Count -eq 0) { break }
    foreach ($identity in @($active | Sort-Object Depth -Descending)) {
      if (-not (Stop-ExactProcess $identity)) {
        $refused += [int]$identity.Id
      }
    }
    if ($refused.Count -gt 0) { return @($refused | Sort-Object -Unique) }
    Start-Sleep -Milliseconds 100
  }

  $stillActive = @(
    $known | Where-Object {
      (Get-ProcessStartTicks $_.Id) -eq [long]$_.StartTicks
    }
  )
  if ($stillActive.Count -gt 0) {
    return @($stillActive | ForEach-Object { [int]$_.Id } | Sort-Object -Unique)
  }

  if (-not (Stop-ExactProcess $launcher)) {
    return @([int]$State.launcherPid)
  }

  for ($pass = 0; $pass -lt 3; $pass++) {
    $late = @(Get-ManagedDescendantIdentities $State $known)
    if ($late.Count -eq 0) { break }
    foreach ($identity in @($late | Sort-Object Depth -Descending)) {
      if (-not (Stop-ExactProcess $identity)) {
        $refused += [int]$identity.Id
      }
      $known += $identity
    }
    if ($refused.Count -gt 0) { break }
    Start-Sleep -Milliseconds 100
  }
  $final = @(Get-ManagedDescendantIdentities $State $known)
  $finalMap = @{}
  foreach ($identity in @($known + $final)) {
    $finalMap["$($identity.Id):$($identity.StartTicks)"] = $identity
  }
  $finalActive = @(
    @($finalMap.Values) | Where-Object {
      (Get-ProcessStartTicks $_.Id) -eq [long]$_.StartTicks
    }
  )
  $refused += @($finalActive | ForEach-Object { [int]$_.Id })
  return @($refused | Sort-Object -Unique)
}

function Save-ManagedState {
  param($State)
  New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
  $tempPath = "$statePath.$PID.tmp"
  try {
    $State | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $tempPath -Encoding UTF8
    Move-Item -LiteralPath $tempPath -Destination $statePath -Force
  } finally {
    Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
  }
}

function Resolve-LeaseToken {
  param([string]$Token, [switch]$Generate)
  if ([string]::IsNullOrWhiteSpace($Token)) {
    if ($Generate) { return [Guid]::NewGuid().ToString('D') }
    Write-Failure 'A lease token from start-wmpf-debugger.cmd is required to stop this service.' 7
  }
  $parsed = [Guid]::Empty
  if (-not [Guid]::TryParse($Token, [ref]$parsed)) {
    Write-Failure 'The WMPFDebugger lease token is invalid.' 7
  }
  return $parsed.ToString('D')
}

function Get-StateLeases {
  param($State)
  return @(
    @($State.leases) |
      ForEach-Object { [string]$_ } |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
      Sort-Object -Unique
  )
}

function Repair-StaleManagedState {
  param($State)
  if ($null -eq $State) { return $false }
  $descendants = @(Get-ManagedDescendantIdentities $State)
  $nodeCandidates = @(
    $descendants | Where-Object { Test-WmpfNodeIdentity $_.Id $State }
  )
  if ($nodeCandidates.Count -ne 1) { return $false }

  $candidate = $nodeCandidates[0]
  $candidateTicks = Get-ProcessStartTicks $candidate.Id
  if ($null -eq $candidateTicks -or $candidateTicks -ne [long]$candidate.StartTicks) {
    return $false
  }
  $State.launcherPid = [int]$candidate.Id
  $State.launcherStartUtcTicks = [long]$candidateTicks
  Save-ManagedState $State
  return $true
}

function Resolve-StartRoot {
  $resolverPath = Join-Path $PSScriptRoot 'resolve-wmpf-root.ps1'
  $skillDir = Split-Path -Parent $PSScriptRoot
  $resolverArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $resolverPath,
    '-SkillDir', $skillDir, '-Persist'
  )
  if ($UseEnvironmentRoot) {
    $resolverArgs += '-UseEnvironmentCandidate'
  } elseif (-not [string]::IsNullOrWhiteSpace($Root)) {
    $resolverArgs += @('-Candidate', $Root)
  }
  $output = @(& powershell.exe @resolverArgs)
  $resolverExit = $LASTEXITCODE
  if ($resolverExit -ne 0 -or $output.Count -eq 0) {
    if ($resolverExit -le 0) { $resolverExit = 1 }
    Write-Failure 'Unable to resolve and persist a valid WMPFDebugger root.' $resolverExit
  }
  return [string]$output[-1]
}

$serviceMutex = New-Object System.Threading.Mutex($false, 'Local\Pi.WechatMiniappReverse.WmpfDebuggerService')
try {
  $lockTaken = $serviceMutex.WaitOne(5000)
} catch [System.Threading.AbandonedMutexException] {
  $lockTaken = $true
}
if (-not $lockTaken) {
  Write-Failure 'Timed out waiting for another WMPFDebugger lifecycle operation.' 6
}

try {
  if ($Action -eq 'Status') {
    $state = Get-ManagedState
    $listeners = @(Get-AllListenerProcessIds)
    if (Test-ProcessIdentity $state) {
      $unmanaged = @(Get-UnmanagedListenerProcessIds $state)
      if ($unmanaged.Count -gt 0) {
        Write-Failure "Ports 9421/62000 include unmanaged listener PID(s): $($unmanaged -join ', ')." 4
      }
      if ((Get-ListenerProcessIds 62000).Count -gt 0) {
        Write-Output "Managed WMPFDebugger is ready (launcher PID $($state.launcherPid))."
      } else {
        Write-Output "Managed WMPFDebugger is starting (launcher PID $($state.launcherPid))."
      }
      exit 0
    }
    if ($listeners.Count -gt 0) {
      Write-Failure "Ports 9421/62000 are occupied by unmanaged listener PID(s): $($listeners -join ', ')." 4
    }
    Write-Output 'Managed WMPFDebugger is not running.'
    exit 3
  }

  if ($Action -eq 'Start') {
    $lease = Resolve-LeaseToken $LeaseToken -Generate
    $rootPath = Resolve-StartRoot
    $state = Get-ManagedState
    if ($null -ne $state -and -not (Test-ProcessIdentity $state)) {
      if (-not (Repair-StaleManagedState $state)) {
        $listeners = @(Get-AllListenerProcessIds)
        $descendants = @(Get-ManagedDescendantIdentities $state)
        if ($listeners.Count -gt 0 -or $descendants.Count -gt 0) {
          Write-Failure 'Stale state still has processes that cannot be safely promoted; preserve state for manual inspection and do not kill by port.' 4
        }
        Remove-ManagedState
        $state = $null
      }
    }
    if (Test-ProcessIdentity $state) {
      $unmanaged = @(Get-UnmanagedListenerProcessIds $state)
      if ($unmanaged.Count -gt 0) {
        Write-Failure "Refusing to start: ports 9421/62000 include unmanaged listener PID(s): $($unmanaged -join ', ')." 4
      }
      if (-not [StringComparer]::OrdinalIgnoreCase.Equals([string]$state.root, $rootPath)) {
        Write-Failure 'A managed WMPFDebugger process from a different root is already active.' 5
      }
      $leases = @(Get-StateLeases $state)
      if ($lease -notin $leases) {
        $leases += $lease
        $state | Add-Member -MemberType NoteProperty -Name leases -Value @($leases) -Force
        Save-ManagedState $state
      }
      if ((Get-ListenerProcessIds 62000).Count -gt 0) {
        Write-Output "Managed WMPFDebugger is already listening on 62000 (launcher PID $($state.launcherPid))."
      } else {
        Write-Output "Managed WMPFDebugger startup is already pending (launcher PID $($state.launcherPid))."
      }
      Write-Output "WMPFDebugger lease token: $lease"
      exit 0
    }

    $listeners = @(Get-AllListenerProcessIds)
    if ($listeners.Count -gt 0) {
      Write-Failure "Refusing to start: ports 9421/62000 are occupied by unmanaged listener PID(s): $($listeners -join ', ')." 4
    }

    $escapedRoot = $rootPath.Replace("'", "''")
    $commandLine = 'call "node_modules\.bin\ts-node.cmd" "src\index.ts" >> "wmpf-debugger.log" 2>&1'
    $escapedCommand = $commandLine.Replace("'", "''")
    $hiddenScript = "Set-Location -LiteralPath '$escapedRoot'; & `$env:ComSpec /d /s /c '$escapedCommand'"
    $launcher = Start-Process -FilePath 'powershell.exe' -ArgumentList @(
      '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
      '-Command', $hiddenScript
    ) -WorkingDirectory $rootPath -WindowStyle Hidden -PassThru
    $newState = [pscustomobject][ordered]@{
      version = 2
      root = $rootPath
      launcherPid = $launcher.Id
      launcherStartUtcTicks = $launcher.StartTime.ToUniversalTime().Ticks
      createdUtc = [DateTime]::UtcNow.ToString('o')
      leases = @($lease)
    }
    try {
      Save-ManagedState $newState
    } catch {
      Stop-ManagedProcessTree $newState | Out-Null
      throw
    }

    Start-Sleep -Milliseconds 200
    $launcher.Refresh()
    if ($launcher.HasExited) {
      $refused = @(Stop-ManagedProcessTree $newState)
      $remaining = @(Get-AllListenerProcessIds)
      if ($refused.Count -gt 0 -or $remaining.Count -gt 0) {
        Write-Failure 'WMPFDebugger exited during startup and managed descendants remain; state was retained for safe recovery.' 1
      }
      Remove-ManagedState
      Write-Failure 'WMPFDebugger exited during startup; inspect wmpf-debugger.log.' 1
    }

    Write-Output "WMPFDebugger spawn requested (managed launcher PID $($launcher.Id))."
    Write-Output "WMPFDebugger lease token: $lease"
    exit 0
  }

  $state = Get-ManagedState
  $listeners = @(Get-AllListenerProcessIds)
  if ($null -eq $state) {
    if ($listeners.Count -gt 0) {
      Write-Failure "Refusing to stop unmanaged listener PID(s): $($listeners -join ', ')." 4
    }
    Write-Output 'No managed WMPFDebugger process is recorded.'
    exit 0
  }

  if (-not (Test-ProcessIdentity $state)) {
    if (-not (Repair-StaleManagedState $state)) {
      $descendants = @(Get-ManagedDescendantIdentities $state)
      if ($listeners.Count -gt 0 -or $descendants.Count -gt 0) {
        Write-Failure 'Stale state could not promote one proven WMPFDebugger Node process; automatic cleanup is refused.' 4
      }
      Remove-ManagedState
      Write-Output 'Removed stale WMPFDebugger state; no managed process is running.'
      exit 0
    }
  }

  $unmanaged = @(Get-UnmanagedListenerProcessIds $state)
  if ($unmanaged.Count -gt 0) {
    Write-Failure "Refusing to stop: ports 9421/62000 include unmanaged listener PID(s): $($unmanaged -join ', ')." 4
  }

  $lease = Resolve-LeaseToken $LeaseToken
  $leases = @(Get-StateLeases $state)
  if ($lease -notin $leases) {
    Write-Failure 'The lease token does not own this managed WMPFDebugger service.' 7
  }
  $remainingLeases = @($leases | Where-Object { $_ -ne $lease })
  if ($remainingLeases.Count -gt 0) {
    $state | Add-Member -MemberType NoteProperty -Name leases -Value @($remainingLeases) -Force
    Save-ManagedState $state
    Write-Output "Released WMPFDebugger lease $lease; service remains active for $($remainingLeases.Count) lease(s)."
    exit 0
  }

  $refused = @(Stop-ManagedProcessTree $state)
  Start-Sleep -Milliseconds 200
  if ($refused.Count -gt 0) {
    Write-Failure "Refused to stop PID(s) whose start time no longer matched state: $($refused -join ', ')." 4
  }

  $remaining = @(Get-AllListenerProcessIds)
  if ($remaining.Count -gt 0) {
    Write-Failure "Managed process stopped, but ports 9421/62000 now have listener PID(s): $($remaining -join ', ')." 4
  }
  Remove-ManagedState
  Write-Output "Stopped managed WMPFDebugger launcher PID $($state.launcherPid) and its process tree."
  exit 0
} catch {
  $line = if ($null -ne $_.InvocationInfo) { $_.InvocationInfo.ScriptLineNumber } else { 0 }
  Write-Failure "$($_.Exception.Message) (wmpf-debugger-service.ps1 line $line)" 1
}
