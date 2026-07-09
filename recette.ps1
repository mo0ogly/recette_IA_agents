<#
===========================================================================
recette.ps1 - Windows entry point for the inspect_ia_agents recette platform

Same surface as ./recette.sh (interactive menu + CLI): this wrapper locates
Git Bash and delegates verbatim to recette.sh, so the cicd/ logic stays in
ONE place (no bash/powershell drift, R19 single entry point).

Usage (PowerShell):
  .\recette.ps1                     # interactive menu
  .\recette.ps1 doctor              # Windows environment check (Git Bash, venv, docker, ports)
  .\recette.ps1 status              # full snapshot
  .\recette.ps1 all up|down|restart # TOUT d'un coup: plateforme + wire overlay + console
  .\recette.ps1 platform up         # lab mock + governed API
  .\recette.ps1 api start|stop|restart|status|logs
  .\recette.ps1 console start|stop|status|logs
  .\recette.ps1 campaign list|run <name> [--json]
  .\recette.ps1 test|gates|report|validate|run|discovery|smoke ...
  .\recette.ps1 git status|pull|push|sync
  .\recette.ps1 --help              # full command list (from recette.sh)

Known Windows limitations (Git Bash environment):
  - eBPF probe targets (probe-ebpf-build, probe-grant-caps) are Linux-only.
  - Docker lab commands require Docker Desktop to be running.
The R19 canonical-port kill works: common.sh falls back to Windows
netstat/taskkill when `ss` is unavailable.

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

# -- doctor: Windows environment check (native, before any bash delegation) --
function Invoke-Doctor {
    param([string]$BashPath)
    $script:doctorFailures = 0

    function Report([bool]$Ok, [string]$Label, [string]$Detail, [bool]$Required = $true) {
        if ($Ok) {
            Write-Host "[OK]        $Label" -ForegroundColor Green -NoNewline
        } elseif ($Required) {
            Write-Host "[ERREUR]    $Label" -ForegroundColor Red -NoNewline
            $script:doctorFailures++
        } else {
            Write-Host "[ATTENTION] $Label" -ForegroundColor Yellow -NoNewline
        }
        if ($Detail) { Write-Host " -- $Detail" } else { Write-Host '' }
    }

    Write-Host "`n== recette doctor (Windows) ==" -ForegroundColor Cyan

    Report ($null -ne $BashPath) 'Git Bash' $BashPath
    $python = Get-Command python -ErrorAction SilentlyContinue
    Report ($null -ne $python) 'python' $python.Source

    $venvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    $venvOk = Test-Path $venvPy
    Report $venvOk '.venv (Windows layout)' $(if ($venvOk) { $venvPy } else { 'creer avec: python -m venv .venv' })

    $jsonschemaOk = $false
    if ($venvOk) {
        & $venvPy -c 'import jsonschema' 2>$null
        $jsonschemaOk = ($LASTEXITCODE -eq 0)
    }
    Report $jsonschemaOk 'jsonschema (dep de base)' $(if (-not $jsonschemaOk) { "installer avec: $venvPy -m pip install jsonschema" })

    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    $daemonOk = $false
    if ($dockerCmd) {
        docker version --format '{{.Server.Version}}' 2>$null | Out-Null
        $daemonOk = ($LASTEXITCODE -eq 0)
    }
    Report ($null -ne $dockerCmd) 'docker CLI' $dockerCmd.Source $false
    Report $daemonOk 'docker daemon (Docker Desktop)' $(if (-not $daemonOk) { 'demarrer Docker Desktop pour les commandes lab/docker' }) $false

    $node = Get-Command node -ErrorAction SilentlyContinue
    Report ($null -ne $node) 'node (console React)' $node.Source $false

    foreach ($p in 8090, 8091, 5174) {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
        if ($conn) {
            $owners = ($conn.OwningProcess | Sort-Object -Unique) -join ', '
            Report $false "port canonique $p" "occupe par pid(s) $owners (libere automatiquement au demarrage, R19)" $false
        } else {
            Report $true "port canonique $p" 'libre'
        }
    }

    Write-Host ''
    if ($script:doctorFailures -gt 0) {
        Write-Host "[ERREUR] $($script:doctorFailures) verification(s) requise(s) en echec" -ForegroundColor Red
        return 1
    }
    Write-Host '[OK] environnement Windows pret pour .\recette.ps1' -ForegroundColor Green
    return 0
}

if ($args.Count -ge 1 -and $args[0] -eq 'doctor') {
    exit (Invoke-Doctor -BashPath $Bash)
}

# -- interactive menu (native PowerShell, parity with the recette.sh menu) --
# Each action delegates to recette.sh through Git Bash, so the cicd/ logic
# stays the single implementation; only the navigation is native.

function Invoke-Sh {
    param([string[]]$CliArgs)
    & $Bash './recette.sh' @CliArgs
}

function Wait-Continue {
    Write-Host ''
    Read-Host '  Entree pour continuer...' | Out-Null
}

# Show-Submenu: numbered loop over options; each option is
# @{ Label = '...'; Sh = @('cli','args') } (delegated, then pause),
# @{ Label = '...'; Action = { ... } } (native, then pause), or
# @{ Label = '...'; Menu = { ... } } (nested submenu, no pause).
# An entry $null renders a blank separator line.
function Show-Submenu {
    param([string]$Title, [object[]]$Options)
    while ($true) {
        Write-Host "`n== $Title ==" -ForegroundColor Cyan
        $i = 0
        foreach ($o in $Options) {
            if ($null -eq $o) { Write-Host ''; continue }
            $i++
            Write-Host ("  {0,2}) " -f $i) -ForegroundColor Green -NoNewline
            Write-Host $o.Label
        }
        Write-Host ''
        Write-Host '   0) ' -ForegroundColor Green -NoNewline
        Write-Host 'Retour'
        $c = Read-Host '  Choix'
        if ($c -in @('0', 'q', 'Q')) { return }
        $numbered = @($Options | Where-Object { $null -ne $_ })
        $idx = 0
        if (-not [int]::TryParse($c, [ref]$idx) -or $idx -lt 1 -or $idx -gt $numbered.Count) {
            Write-Host '[ATTENTION] choix invalide' -ForegroundColor Yellow
            continue
        }
        $sel = $numbered[$idx - 1]
        if ($sel.Menu) { & $sel.Menu }
        elseif ($sel.Sh) { Invoke-Sh $sel.Sh; Wait-Continue }
        elseif ($sel.Action) { & $sel.Action; Wait-Continue }
    }
}

function Show-DockerMenu {
    Show-Submenu 'Docker lab' @(
        @{ Label = 'Statut global';         Sh = @('status') }
        @{ Label = 'Demarrer le lab (up)';  Sh = @('up') }
        @{ Label = 'Arreter le lab (down)'; Sh = @('down') }
        @{ Label = 'Redemarrer le lab';     Sh = @('restart') }
        @{ Label = 'Rebuild image';         Sh = @('rebuild') }
        @{ Label = 'Logs lab';              Sh = @('logs') }
        @{ Label = 'ps (conteneurs)';       Sh = @('ps') }
        @{ Label = 'shell (conteneur)';     Sh = @('shell') }
    )
}

function Show-ApiMenu {
    Show-Submenu 'API gouvernee' @(
        @{ Label = 'API start';   Sh = @('api', 'start') }
        @{ Label = 'API stop';    Sh = @('api', 'stop') }
        @{ Label = 'API restart'; Sh = @('api', 'restart') }
        @{ Label = 'API statut';  Sh = @('api', 'status') }
        @{ Label = 'API logs';    Sh = @('api', 'logs') }
    )
}

function Show-ServicesMenu {
    Show-Submenu 'Services (plateforme gouvernee + console UX)' @(
        @{ Label = 'TOUT demarrer (lab + API + wire + console)'; Sh = @('all', 'up') }
        @{ Label = 'TOUT arreter';                     Sh = @('all', 'down') }
        @{ Label = 'TOUT redemarrer';                  Sh = @('all', 'restart') }
        $null
        @{ Label = 'Statut global';                    Sh = @('status') }
        @{ Label = 'Plateforme up (lab mock + API)';   Sh = @('platform', 'up') }
        @{ Label = 'Plateforme down';                  Sh = @('platform', 'down') }
        @{ Label = 'Plateforme restart';               Sh = @('platform', 'restart') }
        @{ Label = 'Console UX start (http://localhost:5174)'; Sh = @('console', 'start') }
        @{ Label = 'Console UX stop';                  Sh = @('console', 'stop') }
        @{ Label = 'Console UX statut';                Sh = @('console', 'status') }
        @{ Label = 'Console UX logs';                  Sh = @('console', 'logs') }
        $null
        @{ Label = 'Docker lab (sous-menu)';           Menu = { Show-DockerMenu } }
        @{ Label = 'API gouvernee (sous-menu)';        Menu = { Show-ApiMenu } }
    )
}

function Show-CampaignMenu {
    Show-Submenu 'Campagnes' @(
        @{ Label = 'Lister les campagnes'; Sh = @('campaign', 'list') }
        @{ Label = 'Lancer une campagne';  Sh = @('campaign', 'menu') }
    )
}

function Show-RecetteMenu {
    Show-Submenu 'Recette & Discovery' @(
        @{ Label = 'Validate (schema corpus + repos)';              Sh = @('validate') }
        @{ Label = 'Run identification (scorecard 4 dimensions)';   Sh = @('run') }
        @{ Label = 'Discovery (adapter reference)';                 Sh = @('discovery') }
        @{ Label = 'Smoke e2e (API + lab mock + replay)';           Sh = @('smoke') }
        @{ Label = 'Campagnes (sous-menu)';                         Menu = { Show-CampaignMenu } }
        @{ Label = 'Recette full (sweep deterministe + RETEX)';     Sh = @('recette-full') }
        $null
        @{ Label = 'Tests (unittest, local)';                       Sh = @('test') }
        @{ Label = 'Gates (ruff / mypy / bandit)';                  Sh = @('gates') }
        @{ Label = 'Report (scorecard agrege)';                     Sh = @('report') }
        @{ Label = 'Tests (docker)';                                Sh = @('test', '--docker') }
    )
}

function Show-BuildMenu {
    Show-Submenu 'Build (console / docs / natifs)' @(
        @{ Label = 'Console build (tsc + vite)';               Sh = @('console-build') }
        @{ Label = 'Console test (vitest)';                    Sh = @('console-test') }
        @{ Label = 'Docs build (Docusaurus fr+en)';            Sh = @('docs-build') }
        @{ Label = 'Docs serve';                               Sh = @('docs-serve') }
        $null
        @{ Label = 'Moteurs Rust discovery (cargo)';           Sh = @('discovery-build') }
        @{ Label = 'Sonde eBPF + broker CAP_BPF (Linux only)'; Sh = @('probe-ebpf-build') }
        @{ Label = 'Grant CAP_BPF au broker (Linux only)';     Sh = @('probe-grant-caps') }
    )
}

function Show-GitMenu {
    Show-Submenu 'Git' @(
        @{ Label = 'Git statut';              Sh = @('git', 'status') }
        @{ Label = 'Git pull';                Sh = @('git', 'pull') }
        @{ Label = 'Git push';                Sh = @('git', 'push') }
        @{ Label = 'Git sync (fetch + etat)'; Sh = @('git', 'sync') }
    )
}

function Show-ProxyMenu {
    Show-Submenu 'Proxy overlays (Docker, optionnel)' @(
        @{ Label = 'Wire interception (mitmproxy) up'; Sh = @('wire', 'up') }
        @{ Label = 'Wire interception down';           Sh = @('wire', 'down') }
        @{ Label = 'Wire interception statut';         Sh = @('wire', 'status') }
        @{ Label = 'Wire interception logs';           Sh = @('wire', 'logs') }
        @{ Label = 'LLM-proxy (LiteLLM) up';           Sh = @('llm-proxy', 'up') }
        @{ Label = 'LLM-proxy down';                   Sh = @('llm-proxy', 'down') }
        @{ Label = 'LLM-proxy statut';                 Sh = @('llm-proxy', 'status') }
        @{ Label = 'LLM-proxy logs';                   Sh = @('llm-proxy', 'logs') }
    )
}

function Show-CleanupMenu {
    Show-Submenu 'Nettoyage' @(
        @{ Label = 'Purger les serveurs web locaux (API, lab, console)'; Sh = @('platform', 'purge') }
    )
}

function Show-MainMenu {
    while ($true) {
        Write-Host "`n== inspect_ia_agents recette - gestion (Windows) ==" -ForegroundColor Cyan
        $entries = @(
            'Services        (lab + API + console UX + statut)'
            'Recette         (validate / run / discovery / smoke / campagnes / gates)'
            'Build           (console / docs / rust-discovery / ebpf)'
            'Git'
            'Proxy overlays  (Docker, optionnel)'
            'Cleanup'
            'Doctor          (verification environnement Windows)'
        )
        $i = 0
        foreach ($e in $entries) {
            $i++
            Write-Host ("  {0,2}) " -f $i) -ForegroundColor Green -NoNewline
            Write-Host $e
        }
        Write-Host ''
        Write-Host '   0) ' -ForegroundColor Green -NoNewline
        Write-Host 'Quitter'
        $c = Read-Host '  Choix'
        switch ($c) {
            '1' { Show-ServicesMenu }
            '2' { Show-RecetteMenu }
            '3' { Show-BuildMenu }
            '4' { Show-GitMenu }
            '5' { Show-ProxyMenu }
            '6' { Show-CleanupMenu }
            '7' { Invoke-Doctor -BashPath $Bash | Out-Null; Wait-Continue }
            { $_ -in @('0', 'q', 'Q') } { Write-Host '[INFO] Bye' -ForegroundColor Blue; return }
            default { Write-Host '[ATTENTION] choix invalide' -ForegroundColor Yellow }
        }
    }
}

Push-Location $RepoRoot
try {
    if ($args.Count -eq 0) {
        Show-MainMenu
        exit 0
    }
    # Delegate verbatim; keep stdin attached for interactive sub-flows.
    & $Bash './recette.sh' @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
