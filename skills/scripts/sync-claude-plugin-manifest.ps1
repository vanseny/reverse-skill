#requires -Version 5
<#
.SYNOPSIS
  Keep the Claude Code plugin manifest's explicit `skills` array in sync with the
  on-disk skill catalog.

.DESCRIPTION
  Why an explicit array instead of a directory scan: Claude Code treats a
  `skills/` directory that contains a root-level `SKILL.md` as ONE skill and
  skips every nested subdirectory. This repository keeps `skills/SKILL.md` as the
  master routing entry point (referenced by verify-routing-coherence.ps1, README,
  and CONTRIBUTING), so the plugin manifest must enumerate each skill path
  explicitly. Globs (`./skills/*`, `./skills/*/`) are NOT expanded by the loader.

  Run this script after adding, renaming, or removing a skill directory so the
  published marketplace never silently drops skills.

.PARAMETER Check
  Verify mode. Do not write; fail with exit code 1 when the manifest array and
  the on-disk catalog differ. Intended for CI.

.PARAMETER ManifestPath
  Path to plugin.json. Defaults to <repo>/.claude-plugin/plugin.json.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File skills/scripts/sync-claude-plugin-manifest.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File skills/scripts/sync-claude-plugin-manifest.ps1 -Check
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [string]$ManifestPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillsRoot = Split-Path -Parent $scriptDir
$packageRoot = Split-Path -Parent $skillsRoot

if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $ManifestPath = Join-Path $packageRoot '.claude-plugin/plugin.json'
}

function Get-ExpectedSkillPaths {
    param([string]$Root)

    $paths = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $Root -Recurse -Filter 'SKILL.md' -File | ForEach-Object {
        $dir = $_.Directory.FullName
        $rel = $dir.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
        if ([string]::IsNullOrWhiteSpace($rel)) {
            $paths.Add('./skills/')
        } else {
            $paths.Add('./skills/' + $rel + '/')
        }
    }
    # Deterministic order: the master entry ('./skills/') first, then alphabetical.
    $sorted = $paths | Sort-Object -CaseSensitive
    $master = @($sorted | Where-Object { $_ -eq './skills/' })
    $rest = @($sorted | Where-Object { $_ -ne './skills/' })
    return @($master + $rest)
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "plugin manifest not found: $ManifestPath"
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expected = @(Get-ExpectedSkillPaths -Root $skillsRoot)
$actual = @()
if ($manifest.PSObject.Properties.Name -contains 'skills') {
    $actual = @($manifest.skills)
}

$missing = @($expected | Where-Object { $_ -notin $actual })
$extra = @($actual | Where-Object { $_ -notin $expected })

if ($Check) {
    if ($missing.Count -eq 0 -and $extra.Count -eq 0) {
        Write-Host "[OK] Claude plugin manifest skills array is in sync ($($expected.Count) skills)"
        exit 0
    }
    if ($missing.Count -gt 0) {
        Write-Host "[FAIL] manifest is missing skills: $($missing -join ', ')"
    }
    if ($extra.Count -gt 0) {
        Write-Host "[FAIL] manifest references unknown skills: $($extra -join ', ')"
    }
    Write-Host "Run: powershell -NoProfile -ExecutionPolicy Bypass -File skills/scripts/sync-claude-plugin-manifest.ps1"
    exit 1
}

# Rewrite preserving key order and existing metadata.
$ordered = [ordered]@{}
foreach ($prop in $manifest.PSObject.Properties) {
    if ($prop.Name -eq 'skills') {
        $ordered['skills'] = $expected
    } else {
        $ordered[$prop.Name] = $prop.Value
    }
}
if (-not ($ordered.Keys -contains 'skills')) {
    $ordered['skills'] = $expected
}

$json = $ordered | ConvertTo-Json -Depth 20
# Normalize to LF to match .gitattributes (`*.json text eol=lf`), and write UTF-8
# WITHOUT BOM: the manifest is consumed by cross-platform JSON tooling (Python
# json, jq, the Claude loader) that chokes on a leading BOM.
$json = $json -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($ManifestPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] updated $ManifestPath with $($expected.Count) skill paths"
