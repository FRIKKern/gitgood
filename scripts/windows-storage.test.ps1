# No Pester, downloads, large files, or changes to drives are needed.
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'windows-storage.psm1') -Force
$storageModule = Get-Module windows-storage
& $storageModule {
    param($ExistingDirectory)
    $script:checked = 0
    function Assert-Storage($condition, $message) {
        if (-not $condition) { throw "FAIL: $message" }
        $script:checked += 1
    }
    function Assert-StorageRefusal([scriptblock] $action, $message) {
        $refused = $false
        try { $null = & $action } catch { $refused = $true }
        Assert-Storage $refused $message
    }
    function Volume($id, $free) {
        [pscustomobject]@{ Id = $id; Drive = "$id`:\"; FreeBytes = [long]$free }
    }
    function Allocation($volume, $bytes) {
        [pscustomobject]@{ Volume = $volume; Bytes = $bytes }
    }

    foreach ($bytes in @(-1, $true, 1.5, '1024', [double]1024, [decimal]1024, [uint64]::MaxValue, $null)) {
        Assert-StorageRefusal { ConvertTo-GitgoodStorageAllocation @(@{ Path = 'C:\'; Bytes = $bytes }) } 'Malformed bytes refused'
    }
    foreach ($bad in @(@{}, @{ Path = 'C:\'; Bytes = 0; Extra = 1 }, @{ Path = 3; Bytes = 0 }, @{ Path = ' '; Bytes = 0 })) {
        Assert-StorageRefusal { ConvertTo-GitgoodStorageAllocation @($bad) } 'Malformed allocation refused'
    }
    Assert-Storage (@(ConvertTo-GitgoodStorageAllocation @()).Count -eq 0) 'Empty plan means zero estimated bytes'
    Assert-StorageRefusal { ConvertTo-GitgoodStorageAllocation (@(@{ Path = 'C:\'; Bytes = 0 }) * 65) } 'Unbounded input refused'
    $valid = @(ConvertTo-GitgoodStorageAllocation @(@{ Path = 'C:\'; Bytes = 0 }, @{ Path = 'E:\'; Bytes = 2GB }))
    Assert-Storage ($valid.Count -eq 2 -and $valid[1].Bytes -eq 2147483648) 'Whole byte counts retained exactly'

    $equal = Get-GitgoodStorageBudget @(Allocation (Volume C (22GB)) (2GB))
    Assert-Storage ($equal.Passed -and $equal.Volumes[0].RemainingBytes -eq 20GB) 'Exact reserve passes'
    $below = Get-GitgoodStorageBudget @(Allocation (Volume C ((22GB) - 1)) (2GB))
    Assert-Storage (-not $below.Passed) 'One byte below reserve fails'
    $same = Get-GitgoodStorageBudget @(
        (Allocation (Volume C (23GB)) (1GB)), (Allocation (Volume C (23GB)) (2GB)),
        (Allocation (Volume C (23GB)) 0)
    )
    Assert-Storage ($same.Passed -and $same.Volumes.Count -eq 1 -and $same.Volumes[0].EstimatedBytes -eq 3GB) 'Same-volume estimates aggregate once with one reserve'
    $falling = Get-GitgoodStorageBudget @((Allocation (Volume C (40GB)) (1GB)), (Allocation (Volume C (20GB)) 0))
    Assert-Storage (-not $falling.Passed) 'Lowest observed free space wins'
    Assert-StorageRefusal {
        Get-GitgoodStorageBudget @((Allocation (Volume C ([long]::MaxValue)) ([long]::MaxValue)), (Allocation (Volume C ([long]::MaxValue)) 1))
    } 'Estimate addition cannot overflow into success'

    foreach ($path in @('relative', 'C:relative', '\\server\share', '\\?\C:\', 'C:\a\..\b', 'C:\a\\b', 'C:\a:stream')) {
        Assert-StorageRefusal { Get-GitgoodStorageVolume $path } 'Ambiguous path refused'
    }

    # Model a junction ancestor and prove traversal stops before its child or
    # any volume query. No actual junction or filesystem allocation is created.
    function Get-Item {
        param($LiteralPath, [switch]$Force, $ErrorAction)
        $script:visited += $LiteralPath
        $attributes = if ($LiteralPath -eq 'C:\link') { [IO.FileAttributes]::ReparsePoint } else { [IO.FileAttributes]::Directory }
        [pscustomobject]@{ PSProvider = @{ Name = 'FileSystem' }; PSIsContainer = $true; Attributes = $attributes; FullName = $LiteralPath }
    }
    $script:visited = @()
    Assert-StorageRefusal { Get-GitgoodStorageVolume 'C:\link\child' } 'Junction ancestor refused'
    Assert-Storage (($script:visited -join ',') -eq 'C:\,C:\link') 'Root inspected and linked child never followed'
    function Get-Item {
        param($LiteralPath, [switch]$Force, $ErrorAction)
        [pscustomobject]@{ PSProvider = @{ Name = 'FileSystem' }; PSIsContainer = $true; Attributes = [IO.FileAttributes]::Directory; FullName = 'D:\' }
    }
    Assert-StorageRefusal { Get-GitgoodStorageVolume 'C:\output' } 'PSDrive alias shadowing a real letter refused'
    Remove-Item Function:Get-Item

    function Get-Volume { param($FilePath, $ErrorAction) @() }
    Assert-StorageRefusal { Get-GitgoodStorageVolume $ExistingDirectory } 'Unknown volume refused'
    function Get-Volume {
        param($FilePath, $ErrorAction)
        [pscustomobject]@{ DriveType = 'Fixed'; DriveLetter = '0'; UniqueId = '\\?\Volume{11111111-1111-1111-1111-111111111111}\'; SizeRemaining = 100GB }
    }
    Assert-StorageRefusal { Get-GitgoodStorageVolume $ExistingDirectory } 'Aliased drive mapping refused'
    Remove-Item Function:Get-Volume

    $originalReader = (Get-Item Function:Get-GitgoodStorageVolume).ScriptBlock
    try {
        function Get-GitgoodStorageVolume {
            param($Path)
            if ($Path -eq 'E:\output') { Volume E (100GB) } else { Volume C (10GB) }
        }
        $systemLow = Test-GitgoodLocalStorage @(@{ Path = 'E:\output'; Bytes = 1GB })
        Assert-Storage (-not $systemLow.Passed -and $systemLow.Volumes.Count -eq 2) 'Low system volume blocks even with healthy output volume'
        Assert-Storage ($systemLow.Volumes[0].EstimatedBytes -eq 0 -and $systemLow.Volumes[1].EstimatedBytes -eq 1GB) 'System volume included without inventing allocation bytes'
        $inventory = Test-GitgoodLocalStorage
        Assert-Storage (-not $inventory.Passed -and $inventory.Volumes.Count -eq 1 -and $inventory.Volumes[0].EstimatedBytes -eq 0) 'Default inventory includes system volume at zero estimate'

        $script:reads = 0
        function Get-GitgoodStorageVolume {
            param($Path)
            $script:reads += 1
            if ($script:reads -le 2) { Volume C (100GB) } else { Volume E (100GB) }
        }
        Assert-StorageRefusal { Test-GitgoodLocalStorage @(@{ Path = 'C:\output'; Bytes = 0 }) } 'Mapping change on recheck refused'
    } finally {
        Set-Item Function:Get-GitgoodStorageVolume $originalReader
    }
    # Actual local metadata read, but no allocation and no assumption about how
    # much space the test machine has. Windows Storage must resolve this checkout.
    $actual = Get-GitgoodStorageVolume $ExistingDirectory
    Assert-Storage ($actual.FreeBytes -ge 0 -and $actual.Id.StartsWith('\\?\VOLUME{')) 'Actual ordinary directory resolves to fixed volume'
    "Passed $script:checked Windows storage preflight checks."
} $PSScriptRoot
