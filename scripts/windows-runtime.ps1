$ErrorActionPreference = 'Stop'
# Dot-source to download/extract missing pinned runtimes under temp and configure this process's environment.
Import-Module (Join-Path $PSScriptRoot 'windows-storage.psm1') -Force
$tempRoot = [IO.Path]::GetTempPath()
$taskRoot = Join-Path $tempRoot 'gitgood-runtime-1.20.4-29.1.1'
function Install-Archive([string]$Url, [string]$Hash, [string]$Name, [string]$Probe = 'bin', [switch]$ExpandInRoot) {
  $target = Join-Path $taskRoot $Name
  if (!(Test-Path -LiteralPath (Join-Path $target $Probe))) {
    # These pinned archives install sequentially. Allow 4 GiB for one download
    # and extraction peak, then measure again before the next missing runtime.
    $existingRoot = if (Test-Path -LiteralPath $taskRoot) { $taskRoot } else { $tempRoot }
    $allocations = @(@{ Path = $existingRoot; Bytes = 4GB })
    if (Test-Path -LiteralPath $target) { $allocations += @{ Path = $target; Bytes = 0 } }
    $capacity = Test-GitgoodLocalStorage -Allocation $allocations
    if (-not $capacity.Passed) { throw 'Runtime installation refused: the 4 GiB estimate would leave less than the 20 GiB storage reserve. Use existing runtimes or hosted verification.' }
    New-Item -ItemType Directory -Force $taskRoot | Out-Null
    $archive = Join-Path $taskRoot ($Name + '.zip')
    Invoke-WebRequest $Url -OutFile $archive
    if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) { throw 'Runtime checksum mismatch' }
    $destination = if ($ExpandInRoot) { $taskRoot } else { $target }
    Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
  }
  return $target
}
$otpPath = Install-Archive 'https://github.com/erlang/otp/releases/download/OTP-29.1.1/otp_win64_29.1.1.zip' '337480af988eca993c2e98b68850f00fc6724d366346565e38941ac0d1b7c56b' 'otp'
$elixirPath = Install-Archive 'https://github.com/elixir-lang/elixir/releases/download/v1.20.4/elixir-otp-29.zip' '7863c546cda13fecc949e562e326042451dacf8fd8698a36783cb71eeb223b46' 'elixir'
$nodePath = Install-Archive 'https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip' '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71' 'node-v22.23.3-win-x64' 'node.exe' -ExpandInRoot
$env:PATH = "$otpPath\bin;$elixirPath\bin;$nodePath;$env:PATH"
$env:MIX_HOME = Join-Path $taskRoot 'mix'
$env:HEX_HOME = Join-Path $taskRoot 'hex'
& (Join-Path $elixirPath 'bin/elixir.bat') --version
& (Join-Path $nodePath 'node.exe') --version
