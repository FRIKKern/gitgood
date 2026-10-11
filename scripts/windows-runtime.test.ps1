# Exercise the install function's actual branches with no network or file writes.
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'windows-runtime.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Runtime helper could not be parsed.' }
$definitions = @($ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Install-Archive' }, $true))
if ($definitions.Count -ne 1) { throw 'Expected one install function.' }
# Load the exact checked-in function without executing the script's real installs.
. ([scriptblock]::Create($definitions[0].Extent.Text))
$tempRoot = 'C:\synthetic-temp'
$taskRoot = Join-Path $tempRoot 'runtime'
$script:cached = $false
$script:allowed = $false
$script:hash = 'checked-hash'
$script:gateCalls = 0
$script:writes = 0
$script:network = 0
$script:extracts = 0
function Test-Path { param($LiteralPath) $script:cached }
function Test-GitgoodLocalStorage {
  param($Allocation)
  $script:gateCalls += 1
  if ($Allocation.Count -ne 1 -or $Allocation[0].Path -ne $tempRoot -or $Allocation[0].Bytes -ne 4GB) { throw 'Wrong peak allocation estimate.' }
  [pscustomobject]@{ Passed = $script:allowed }
}
function New-Item {
  $script:writes += 1
  if (-not $script:allowed) { throw 'Unexpected filesystem write' }
}
function Invoke-WebRequest {
  $script:network += 1
  if (-not $script:allowed) { throw 'Unexpected network request' }
}
function Get-FileHash { param($LiteralPath, $Algorithm) [pscustomobject]@{ Hash = $script:hash } }
function Expand-Archive {
  param($LiteralPath, $DestinationPath, [switch]$Force)
  $script:extracts += 1
  if (-not $script:allowed) { throw 'Unexpected extraction' }
  $script:destination = $DestinationPath
}
foreach ($shape in @(@{ Name = 'otp'; Probe = 'bin'; ExpandInRoot = $false }, @{ Name = 'node'; Probe = 'node.exe'; ExpandInRoot = $true })) {
  $refused = $false
  try { $null = Install-Archive 'https://invalid.example/archive.zip' 'unused' @shape } catch {
    if ($_.Exception.Message -notlike 'Runtime installation refused:*') { throw }
    $refused = $true
  }
  if (-not $refused -or $script:writes -ne 0 -or $script:network -ne 0 -or $script:extracts -ne 0) { throw 'Missing runtime was not refused before payload activity.' }
}
if ($script:gateCalls -ne 2) { throw 'Every missing runtime shape must check capacity.' }
$script:cached = $true
foreach ($shape in @(@{ Name = 'otp'; Probe = 'bin'; ExpandInRoot = $false }, @{ Name = 'node'; Probe = 'node.exe'; ExpandInRoot = $true })) {
  $result = Install-Archive 'https://invalid.example/archive.zip' 'unused' @shape
  if ($result -ne (Join-Path $taskRoot $shape.Name)) { throw 'Cached runtime path changed.' }
}
if ($script:gateCalls -ne 2 -or $script:writes -ne 0 -or $script:network -ne 0 -or $script:extracts -ne 0) { throw 'Cached runtimes must remain usable without an allocation gate or payload activity.' }
$script:cached = $false
$script:allowed = $true
foreach ($shape in @(@{ Name = 'otp'; Probe = 'bin'; ExpandInRoot = $false }, @{ Name = 'node'; Probe = 'node.exe'; ExpandInRoot = $true })) {
  $result = Install-Archive 'https://invalid.example/archive.zip' 'checked-hash' @shape
  $expected = if ($shape.ExpandInRoot) { $taskRoot } else { Join-Path $taskRoot $shape.Name }
  if ($script:destination -ne $expected -or $result -ne (Join-Path $taskRoot $shape.Name)) { throw 'Archive expansion changed the runtime layout.' }
}
if ($script:gateCalls -ne 4 -or $script:writes -ne 2 -or $script:network -ne 2 -or $script:extracts -ne 2) { throw 'Every simulated install must check capacity before its payload steps.' }
$script:hash = 'corrupt-hash'
$refused = $false
try { $null = Install-Archive 'https://invalid.example/archive.zip' 'checked-hash' 'otp' } catch {
  if ($_.Exception.Message -ne 'Runtime checksum mismatch') { throw }
  $refused = $true
}
if (-not $refused -or $script:extracts -ne 2 -or $script:network -ne 3 -or $script:gateCalls -ne 5) { throw 'Checksum mismatch must prevent extraction.' }
'Passed missing/cached runtime gates, checksum refusal and archive layouts using only stubs; no network or file writes.'
