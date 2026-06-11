# PowerShell Collection Script Template

## Full Template

```powershell
<#
.SYNOPSIS
    Collect {Technology} configuration and version data for LIA-Scan analysis.

.DESCRIPTION
    Collects raw data from {Technology} using {method discovered in Phase 0}.

    ObjectClass(es) produced:
    - {technology_lowercase}_instance: Server/instance information
    - {technology_lowercase}_config: Configuration settings (if applicable)

    MOTOR_FIX_010 COMPLIANT: This script collects RAW DATA only.
    All detection logic is in the YAML rules, NOT in this script.

    Collection method: {PowerShell cmdlets / REST API / WMI / Registry}
    Source: {URL from research}

.PARAMETER OutputPath
    Path to save JSON output file (mandatory).

.PARAMETER Server
    Target server hostname or IP address.

.PARAMETER Credential
    PSCredential for authentication (if required).

.EXAMPLE
    .\Collect-{Technology}.ps1 -OutputPath "output.json" -Server "srv01"

.NOTES
    Author: LIA-Scan Platform
    Version: 1.0.0
    Date: {YYYY-MM-DD}
    ObjectClass: {technology_lowercase}_instance
    Requires: {PowerShell module or pre-requisite}
    Research: See COLLECTION_RESEARCH.md for methodology
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$OutputPath,

    [Parameter(Mandatory=$false)]
    [string]$Server = "localhost",

    # Replace with REAL default port of the technology (e.g., 443, 8443, 5986...)
    # Source: official vendor documentation (see COLLECTION_RESEARCH.md)
    [Parameter(Mandatory=$false)]
    [int]$Port = 443,

    [Parameter(Mandatory=$false)]
    [PSCredential]$Credential
)

$ErrorActionPreference = "Continue"
$results = @()
$collectionErrors = @()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

function Get-NormalizedVersion {
    <#
    .SYNOPSIS
        Normalize version string to semantic format (X.Y.Z).
        This is FORMAT TRANSFORMATION only (MOTOR_FIX_010 compliant).
        NO version comparison logic here.
    #>
    param([string]$Version)

    # Remove build metadata or non-standard prefixes
    $clean = $Version -replace '^v', '' -replace '\s.*$', ''

    # Normalize vendor-specific formats
    # Example: "9.1R14.4" -> "9.1.14.4"
    if ($clean -match '^(\d+\.\d+)R(\d+\.\d+)$') {
        return "$($Matches[1]).$($Matches[2])"
    }

    return $clean
}

# ============================================================================
# MAIN COLLECTION
# ============================================================================

Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Starting {Technology} collection from $Server"

try {
    # -----------------------------------------------------------------------
    # CONNECT (method identified in Phase 0 - COLLECTION_RESEARCH.md)
    # -----------------------------------------------------------------------
    # REPLACE this block with the method found in Phase 0.
    # Supported options (choose one per technology):
    #
    # Option A: PowerShell Module (e.g., Exchange, Hyper-V, SharePoint)
    #   Import-Module {RealModuleName} -ErrorAction Stop
    #
    # Option B: REST API (e.g., FortiGate, Palo Alto, vCenter)
    #   $headers = @{ "Content-Type" = "application/json" }
    #   if ($Credential) {
    #       $token = Invoke-RestMethod -Uri "https://$Server:$Port/api/v1/auth" ...
    #       $headers["Authorization"] = "Bearer $token"
    #   }
    #
    # Option C: WMI/CIM native Windows (e.g., Windows Server, Hyper-V)
    #   $cimSession = New-CimSession -ComputerName $Server -Credential $Credential
    #
    # NONE of these options should remain commented in the deliverable.
    # The chosen method must be implemented, not commented.

    # -----------------------------------------------------------------------
    # COLLECT RAW DATA (real commands from Phase 0)
    # -----------------------------------------------------------------------
    # Implement the commands found in Phase 0 - WebSearch mandatory.
    # Each command must have a source URL in COLLECTION_RESEARCH.md.

    # -----------------------------------------------------------------------
    # BUILD OUTPUT OBJECTS (RAW DATA ONLY)
    # -----------------------------------------------------------------------

    # foreach ($item in $instances) {
    #     $results += [PSCustomObject]@{
    #         ObjectClass       = "{technology_lowercase}_instance"
    #         Hostname          = $Server
    #         Version           = $item.Version
    #         VersionNormalized = (Get-NormalizedVersion -Version $item.Version)
    #         MajorVersion      = ($item.Version -split '\.')[0]
    #         MinorVersion      = ($item.Version -split '\.')[1]
    #         Product           = "{Technology}"
    #         CollectionDate    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    #         CollectorVersion  = "1.0.0"
    #     }
    # }

    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Collected $($results.Count) objects"
}
catch {
    $errorMsg = "Collection failed: $($_.Exception.Message)"
    Write-Error $errorMsg
    $collectionErrors += $errorMsg
}

# ============================================================================
# OUTPUT
# ============================================================================

if ($results.Count -gt 0) {
    $results | ConvertTo-Json -Depth 10 | Out-File -Path $OutputPath -Encoding UTF8
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Output saved to $OutputPath ($($results.Count) objects)"
} else {
    Write-Warning "No data collected. Errors: $($collectionErrors -join '; ')"
    # Write empty array for downstream compatibility
    "[]" | Out-File -Path $OutputPath -Encoding UTF8
}

# Summary
Write-Host ""
Write-Host "Collection Summary:"
Write-Host "  Objects collected: $($results.Count)"
Write-Host "  Errors: $($collectionErrors.Count)"
Write-Host "  Output: $OutputPath"
```

## Connection Patterns Reference

### Option A: PowerShell Module (Exchange, Hyper-V, SharePoint)

```powershell
Import-Module {RealModuleName} -ErrorAction Stop
# Command found: see COLLECTION_RESEARCH.md "Primary Method"
```

### Option B: REST API (FortiGate, Palo Alto, vCenter)

```powershell
$headers = @{ "Content-Type" = "application/json" }
if ($Credential) {
    $token = Invoke-RestMethod -Uri "https://$Server:$Port/api/v1/auth" ...
    $headers["Authorization"] = "Bearer $token"
}
```

### Option C: WMI/CIM native Windows (Windows Server, Hyper-V)

```powershell
$cimSession = New-CimSession -ComputerName $Server -Credential $Credential
```
