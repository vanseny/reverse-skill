param(
  [Parameter(Mandatory = $true)]
  [string]$SkillDir,
  [string]$Candidate,
  [switch]$UseEnvironmentCandidate,
  [switch]$Persist,
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

function Resolve-WmpfRoot {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) { return $null }

  try {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved.StartsWith('\\')) { return $null }
    $packagePath = Join-Path $resolved 'package.json'
    $sourcePath = Join-Path $resolved 'src\index.ts'
    $tsNodePath = Join-Path $resolved 'node_modules\.bin\ts-node.cmd'
    if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $sourcePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $tsNodePath -PathType Leaf)) {
      return $null
    }

    $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
    $main = [string]$package.main -replace '\\', '/'
    $dependencyNames = @($package.dependencies.PSObject.Properties.Name)
    $devDependencyNames = @($package.devDependencies.PSObject.Properties.Name)
    if ([string]$package.name -ine 'WMPFDebugger' -or
        $main -ne 'src/index.ts' -or
        'frida' -notin $dependencyNames -or
        'protobufjs' -notin $dependencyNames -or
        'ws' -notin $dependencyNames -or
        'ts-node' -notin $devDependencyNames) {
      return $null
    }

    $source = Get-Content -LiteralPath $sourcePath -Raw
    if ($source -notmatch '\bparse_cli_options\b' -or
        $source -notmatch '\bWebSocketServer\b') {
      return $null
    }

    return $resolved
  } catch {
    return $null
  }
}

$skillPath = (Resolve-Path -LiteralPath $SkillDir).Path
$configPath = Join-Path $skillPath 'local.config.json'

if ($UseEnvironmentCandidate) {
  $Candidate = $env:WMPF_ROOT_CANDIDATE
}

$resolvedRoot = $null
if (-not [string]::IsNullOrWhiteSpace($Candidate)) {
  $resolvedRoot = Resolve-WmpfRoot $Candidate
  if ($null -eq $resolvedRoot) {
    [Console]::Error.WriteLine('The supplied path is not a valid WMPFDebugger root.')
    exit 2
  }
} else {
  if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    try {
      $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
      $resolvedRoot = Resolve-WmpfRoot $config.wmpfDebuggerRoot
    } catch {
      $resolvedRoot = $null
    }
  }

  if ($null -eq $resolvedRoot) {
    $cwd = (Get-Location).Path
    $parent = Split-Path -Parent $cwd
    $candidates = @($cwd, $parent)
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
      $candidates += Join-Path $parent 'WMPFDebugger'
    }

    $seen = @{}
    foreach ($path in $candidates) {
      if ([string]::IsNullOrWhiteSpace($path) -or $seen.ContainsKey($path)) { continue }
      $seen[$path] = $true
      $resolvedRoot = Resolve-WmpfRoot $path
      if ($null -ne $resolvedRoot) { break }
    }
  }
}

if ($null -eq $resolvedRoot) {
  exit 3
}

if ($Persist) {
  $tempPath = "$configPath.$PID.tmp"
  try {
    [ordered]@{ wmpfDebuggerRoot = $resolvedRoot } |
      ConvertTo-Json |
      Set-Content -LiteralPath $tempPath -Encoding UTF8
    Move-Item -LiteralPath $tempPath -Destination $configPath -Force
  } finally {
    Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
  }
}

if (-not $Quiet) {
  Write-Output $resolvedRoot
}
exit 0
