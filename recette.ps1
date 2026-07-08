<#
===========================================================================
recette.ps1 - Windows entry point for the inspect_ia_agents recette platform

Same surface as ./recette.sh (interactive menu + CLI): this wrapper locates
Git Bash and delegates verbatim to recette.sh, so the cicd/ logic stays in
ONE place (no bash/powershell drift, R19 single entry point).

Usage (PowerShell):
  .\recette.ps1                     # interactive menu
  .\recette.ps1 status              # full snapshot
  .\recette.ps1 platform up         # lab mock + governed API
  .\recette.ps1 api start|stop|restart|status|logs
  .\recette.ps1 console start|stop|status|logs
  .\recette.ps1 campaign list|run <name> [--json]
  .\recette.ps1 test|gates|report|validate|run|discovery|smoke ...
  .\recette.ps1 git status|pull|push|sync
  .\recette.ps1 --help              # full command list (from recette.sh)

Known Windows limitations (Git Bash environment):
  - `ss` is unavailable, so the R19 port-holder kill is a no-op: if a
    canonical port (8090/8091/5174) is squatted, free it manually
    (Get-NetTCPConnection -LocalPort 8090 | Select OwningProcess).
  - eBPF probe targets (probe-ebpf-build, probe-grant-caps) are Linux-only.

Auteur : Fabrice Pizzi - ANSSI
===========================================================================
#>

$ErrorActionPreference = 'Stop'

$RepoRoot = $PSScriptRoot
$RecetteSh = Join-Path $RepoRoot 'recette.sh'

if (-not (Test-Path $RecetteSh)) {
    Write-Error "recette.sh introuvable dans $RepoRoot"
    exit 1
}

# Resolve Git Bash explicitly. Do NOT trust `bash` on PATH: on Windows,
# C:\WINDOWS\system32\bash.exe is the WSL launcher, which needs a full Linux
# distro (only docker-desktop may be present). Git Bash runs recette.sh as-is.
function Find-GitBash {
    $candidates = @()
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        # ...\Git\cmd\git.exe -> ...\Git\bin\bash.exe
        $gitRoot = Split-Path (Split-Path $git.Source -Parent) -Parent
        $candidates += (Join-Path $gitRoot 'bin\bash.exe')
    }
    $candidates += "$env:ProgramFiles\Git\bin\bash.exe"
    $candidates += "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
    $candidates += "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    return $null
}

$Bash = Find-GitBash
if (-not $Bash) {
    Write-Error "Git Bash introuvable (git for Windows requis). Installer: https://gitforwindows.org/"
    exit 1
}

# Delegate verbatim; keep stdin attached so the interactive menu works.
Push-Location $RepoRoot
try {
    & $Bash './recette.sh' @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
