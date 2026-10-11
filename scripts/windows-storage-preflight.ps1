<#
.SYNOPSIS
Check Windows system/output volumes before a large local allocation.
.DESCRIPTION
Each allocation is @{ Path = <existing absolute directory>; Bytes = <integer> }.
Include peak temporary, download, extraction and output bytes. The fixed reserve
is 20 GiB per actual volume. This read-only snapshot does not reserve capacity.
#>
[CmdletBinding(DefaultParameterSetName = 'Inventory')]
param(
    [Parameter(ParameterSetName = 'Allocation', Mandatory)][object[]] $Allocation,
    [Parameter(ParameterSetName = 'Inventory')][string[]] $Path = @()
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'windows-storage.psm1') -Force
if ($PSCmdlet.ParameterSetName -eq 'Inventory') {
    $Allocation = @($Path | ForEach-Object { @{ Path = $_; Bytes = 0 } })
}
$result = Test-GitgoodLocalStorage -Allocation $Allocation
$result.Volumes | Select-Object Drive,
    @{ Name = 'FreeGiB'; Expression = { [Math]::Round($_.FreeBytes / 1GB, 2) } },
    @{ Name = 'PlannedGiB'; Expression = { [Math]::Round($_.EstimatedBytes / 1GB, 2) } },
    @{ Name = 'AfterGiB'; Expression = { [Math]::Round($_.RemainingBytes / 1GB, 2) } },
    @{ Name = 'ReserveGiB'; Expression = { 20 } }, Passed | Format-Table -AutoSize
if (-not $result.Passed) {
    throw 'Storage preflight failed: every volume needs at least 20 GiB after the estimated allocation. Use hosted verification; do not start the local allocation.'
}
Write-Host 'Storage preflight passed. This is a snapshot, not a reservation; coordinate concurrent allocations and rerun immediately before starting.'
