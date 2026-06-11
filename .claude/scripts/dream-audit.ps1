#Requires -Version 5.1
<#
.SYNOPSIS
    dream-audit.ps1 — Mechanical memory audit for Claude Code
.DESCRIPTION
    Audits the Claude Code memory directory for orphans, stale files,
    credentials, duplicates, and index inconsistencies.
.PARAMETER MemoryDir
    Path to memory directory. Auto-detected if omitted.
.EXAMPLE
    .\dream-audit.ps1
    .\dream-audit.ps1 -MemoryDir "C:\Users\me\.claude\projects\my-project\memory"
#>
param(
    [string]$MemoryDir
)

$ErrorActionPreference = "Stop"

# --- Resolve memory directory ---
if (-not $MemoryDir) {
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if (-not $repoRoot) { $repoRoot = (Get-Location).Path }
    $slug = ($repoRoot -replace '[/\\:]', '-') -replace '^-+', ''
    $MemoryDir = Join-Path $env:USERPROFILE ".claude\projects\$slug\memory"
}

$index = Join-Path $MemoryDir "MEMORY.md"
$warnings = 0
$errors = 0

Write-Host "=== DREAM AUDIT ===" -ForegroundColor Cyan
Write-Host "Memory dir: $MemoryDir"
Write-Host "Date: $(Get-Date -Format 'o')"
Write-Host ""

# --- Check 1: Memory directory exists ---
if (-not (Test-Path $MemoryDir)) {
    Write-Host "[SKIP] Memory directory does not exist. Nothing to audit." -ForegroundColor DarkGray
    exit 0
}

# --- Check 2: MEMORY.md exists ---
if (-not (Test-Path $index)) {
    Write-Host "[ERROR] MEMORY.md index missing" -ForegroundColor Red
    $errors++
}

# --- Check 3: Index sync — orphan files ---
Write-Host "--- Index Sync ---" -ForegroundColor Yellow
$mdFiles = Get-ChildItem -Path $MemoryDir -Filter "*.md" | Where-Object { $_.Name -ne "MEMORY.md" }
$indexContent = if (Test-Path $index) { Get-Content $index -Raw } else { "" }

foreach ($f in $mdFiles) {
    if ($indexContent -notmatch [regex]::Escape($f.Name)) {
        Write-Host "[WARN] Orphan file not in index: $($f.Name)" -ForegroundColor DarkYellow
        $warnings++
    }
}

# --- Check 4: Index entries without files ---
if (Test-Path $index) {
    $refs = [regex]::Matches($indexContent, '\[.*?\]\(([^)]+\.md)\)')
    foreach ($m in $refs) {
        $ref = $m.Groups[1].Value
        $refPath = Join-Path $MemoryDir $ref
        if (-not (Test-Path $refPath)) {
            Write-Host "[ERROR] Index references missing file: $ref" -ForegroundColor Red
            $errors++
        }
    }
}

# --- Check 5: Index line count ---
if (Test-Path $index) {
    $lineCount = (Get-Content $index).Count
    Write-Host ""
    Write-Host "--- Index Size ---" -ForegroundColor Yellow
    Write-Host "MEMORY.md: $lineCount lines"
    if ($lineCount -gt 200) {
        Write-Host "[ERROR] Index exceeds 200 lines (truncation threshold)" -ForegroundColor Red
        $errors++
    } elseif ($lineCount -gt 150) {
        Write-Host "[WARN] Index approaching limit (>150 lines)" -ForegroundColor DarkYellow
        $warnings++
    } else {
        Write-Host "[OK] Under limit" -ForegroundColor Green
    }
}

# --- Check 6: Stale files ---
Write-Host ""
Write-Host "--- Staleness ---" -ForegroundColor Yellow
$now = Get-Date
foreach ($f in $mdFiles) {
    $ageDays = ($now - $f.LastWriteTime).Days
    if ($ageDays -gt 30) {
        Write-Host "[WARN] Stale ($ageDays days): $($f.Name)" -ForegroundColor DarkYellow
        $warnings++
    } elseif ($ageDays -gt 14) {
        Write-Host "[INFO] Aging ($ageDays days): $($f.Name)" -ForegroundColor DarkGray
    }
}

# --- Check 7: Credential patterns ---
Write-Host ""
Write-Host "--- Credential Scan ---" -ForegroundColor Yellow
$credHits = 0
foreach ($f in $mdFiles) {
    $content = Get-Content $f.FullName -Raw
    if ($content -match '(?i)(password|passwd|secret|token|api.?key)\s*[:=]') {
        Write-Host "[CRITICAL] Potential credential in: $($f.Name)" -ForegroundColor Red
        $credHits++
        $errors++
    }
}
if ($credHits -eq 0) {
    Write-Host "[OK] No credentials detected" -ForegroundColor Green
}

# --- Check 8: Duplicate descriptions ---
Write-Host ""
Write-Host "--- Duplicate Detection ---" -ForegroundColor Yellow
$descriptions = @{}
$dupFound = $false
foreach ($f in $mdFiles) {
    $content = Get-Content $f.FullName -Raw
    if ($content -match '(?m)^description:\s*(.+)$') {
        $desc = $Matches[1].Trim()
        if ($descriptions.ContainsKey($desc)) {
            Write-Host "[WARN] Duplicate description in $($f.Name) (same as $($descriptions[$desc]))" -ForegroundColor DarkYellow
            $warnings++
            $dupFound = $true
        } else {
            $descriptions[$desc] = $f.Name
        }
    }
}
if (-not $dupFound -and $warnings -eq 0 -and $errors -eq 0) {
    Write-Host "[OK] No duplicates" -ForegroundColor Green
}

# --- Check 9: Summary ---
Write-Host ""
Write-Host "--- Summary ---" -ForegroundColor Yellow
$totalLines = 0
foreach ($f in (Get-ChildItem -Path $MemoryDir -Filter "*.md")) {
    $totalLines += (Get-Content $f.FullName).Count
}
Write-Host "Files: $($mdFiles.Count) (excl. index)"
Write-Host "Total lines: $totalLines"
Write-Host "Warnings: $warnings"
Write-Host "Errors: $errors"

# --- Verdict ---
Write-Host ""
if ($errors -gt 0) {
    Write-Host "VERDICT: CRITICAL ($errors errors, $warnings warnings)" -ForegroundColor Red
    exit 2
} elseif ($warnings -gt 2) {
    Write-Host "VERDICT: NEEDS_CONSOLIDATION ($warnings warnings)" -ForegroundColor DarkYellow
    exit 1
} else {
    Write-Host "VERDICT: CLEAN" -ForegroundColor Green
    exit 0
}
