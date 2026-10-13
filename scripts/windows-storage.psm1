Set-StrictMode -Version Latest

function ConvertTo-GitgoodStorageAllocation {
    param([object[]] $Allocation)
    if ($Allocation.Count -gt 64) {
        throw 'Supply at most 64 allocations with Path and Bytes.'
    }
    foreach ($item in $Allocation) {
        if ($item -isnot [System.Collections.IDictionary] -or $item.Count -ne 2 -or
            -not $item.Contains('Path') -or -not $item.Contains('Bytes') -or
            $item.Path -isnot [string] -or [string]::IsNullOrWhiteSpace($item.Path)) {
            throw 'Each allocation must contain only Path (an existing directory) and Bytes (an integer).'
        }
        $integer = $item.Bytes -is [byte] -or $item.Bytes -is [sbyte] -or
            $item.Bytes -is [int16] -or $item.Bytes -is [uint16] -or
            $item.Bytes -is [int32] -or $item.Bytes -is [uint32] -or
            $item.Bytes -is [int64] -or $item.Bytes -is [uint64]
        if (-not $integer -or [decimal]$item.Bytes -lt 0 -or [decimal]$item.Bytes -gt [long]::MaxValue) {
            throw 'Bytes must be a nonnegative integer no greater than Int64.MaxValue; strings and fractions are refused.'
        }
        [pscustomobject]@{ Path = $item.Path; Bytes = [long]$item.Bytes }
    }
}

function Get-GitgoodStorageVolume {
    param([string] $Path)
    # Inspect each named ancestor without resolving a link into another tree.
    if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(3) -match '[<>:"|?*\x00-\x1f]') {
        throw 'Use an absolute drive-letter directory such as C:\work; UNC, device and relative paths are refused.'
    }
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not [string]::Equals($full.TrimEnd('\'), $Path.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Use a canonical directory path without dot segments or duplicate separators.'
    }
    $root = [System.IO.Path]::GetPathRoot($full)
    $cursor = $root
    $segments = @('') + @($full.Substring(3).TrimEnd('\').Split('\', [StringSplitOptions]::RemoveEmptyEntries))
    foreach ($segment in $segments) {
        if ($segment) { $cursor = Join-Path $cursor $segment }
        $entry = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if ($entry.PSProvider.Name -ne 'FileSystem' -or -not $entry.PSIsContainer -or
            ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not [string]::Equals($entry.FullName.TrimEnd('\'), $cursor.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Every path segment must be an existing ordinary directory at that exact path; aliases, links and mounted folders are refused.'
        }
    }
    # Storage's FilePath query identifies the actual volume. Comparing its real
    # drive letter rejects SUBST/PSDrive aliases instead of trusting their label.
    $volumes = @(Get-Volume -FilePath ($full.TrimEnd('\') + '\') -ErrorAction Stop)
    if ($volumes.Count -ne 1) { throw 'The directory must resolve to exactly one known local volume.' }
    $volume = $volumes[0]
    if ($volume.DriveType.ToString() -ne 'Fixed' -or
        [string]$volume.DriveLetter -ine $root.Substring(0, 1) -or
        [string]$volume.UniqueId -notmatch '^\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\$') {
        throw 'The directory must use its real fixed-volume drive letter; aliases and unknown volumes are refused.'
    }
    $drive = [System.IO.DriveInfo]::new($root)
    if (-not $drive.IsReady -or $drive.DriveType -ne [IO.DriveType]::Fixed) {
        throw 'The local drive is unavailable or is not fixed storage.'
    }
    $free = [Math]::Min([long]$volume.SizeRemaining, $drive.AvailableFreeSpace)
    if ($free -lt 0) { throw 'Available storage could not be measured.' }
    [pscustomobject]@{ Id = $volume.UniqueId.ToUpperInvariant(); Drive = $root; FreeBytes = $free }
}

function Get-GitgoodStorageBudget {
    param([object[]] $Resolved)
    $reserve = [long](20GB)
    $groups = @{}
    foreach ($item in $Resolved) {
        if (-not $groups.ContainsKey($item.Volume.Id)) {
            $groups[$item.Volume.Id] = [pscustomobject]@{
                Volume = $item.Volume.Id; Drive = $item.Volume.Drive
                FreeBytes = [long]$item.Volume.FreeBytes; EstimatedBytes = [long]0
            }
        }
        $row = $groups[$item.Volume.Id]
        $sum = [decimal]$row.EstimatedBytes + [decimal]$item.Bytes
        if ($sum -gt [long]::MaxValue) { throw 'Combined allocation estimates overflow the supported byte count.' }
        $row.EstimatedBytes = [long]$sum
        $row.FreeBytes = [Math]::Min($row.FreeBytes, [long]$item.Volume.FreeBytes)
    }
    $rows = @($groups.Values | Sort-Object Drive | ForEach-Object {
        $remaining = [decimal]$_.FreeBytes - [decimal]$_.EstimatedBytes
        [pscustomobject]@{
            Drive = $_.Drive; Volume = $_.Volume; FreeBytes = $_.FreeBytes
            EstimatedBytes = $_.EstimatedBytes; RemainingBytes = $remaining
            ReserveBytes = $reserve; Passed = $remaining -ge $reserve
        }
    })
    [pscustomobject]@{ Passed = @($rows | Where-Object { -not $_.Passed }).Count -eq 0; Volumes = $rows }
}

function Test-GitgoodLocalStorage {
    [CmdletBinding()]
    param([object[]] $Allocation = @())
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Run this preflight in Windows PowerShell on the host, including before WSL allocations.'
    }
    $planned = @(ConvertTo-GitgoodStorageAllocation $Allocation)
    # The OS determines its system directory; caller-supplied output choices
    # cannot omit the system volume. Its allocation is zero unless listed too.
    $planned += [pscustomobject]@{ Path = [Environment]::SystemDirectory; Bytes = [long]0 }
    $resolved = @($planned | ForEach-Object {
        [pscustomobject]@{ Path = $_.Path; Bytes = $_.Bytes; Volume = Get-GitgoodStorageVolume $_.Path }
    })
    foreach ($item in $resolved) {
        $latest = Get-GitgoodStorageVolume $item.Path
        if ($latest.Id -cne $item.Volume.Id -or $latest.Drive -ine $item.Volume.Drive) {
            throw 'A volume mapping changed during the check; stop and rerun the preflight.'
        }
        $item.Volume.FreeBytes = [Math]::Min($item.Volume.FreeBytes, $latest.FreeBytes)
    }
    Get-GitgoodStorageBudget $resolved
}

Export-ModuleMember -Function Test-GitgoodLocalStorage
