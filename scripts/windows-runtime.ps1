$ErrorActionPreference = 'Stop'
# Dot-source this script in a PowerShell process; it changes only that process's environment.
$taskRoot = Join-Path ([IO.Path]::GetTempPath()) 'gitgood-runtime-1.20.4-29.1.1'
New-Item -ItemType Directory -Force $taskRoot | Out-Null
function Install-Archive([string]$Url, [string]$Hash, [string]$Name) {
  $target = Join-Path $taskRoot $Name
  if (!(Test-Path (Join-Path $target 'bin'))) {
    $archive = Join-Path $taskRoot ($Name + '.zip')
    Invoke-WebRequest $Url -OutFile $archive
    if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) { throw 'Runtime checksum mismatch' }
    Expand-Archive -LiteralPath $archive -DestinationPath $target -Force
  }
  return $target
}
$otpPath = Install-Archive 'https://github.com/erlang/otp/releases/download/OTP-29.1.1/otp_win64_29.1.1.zip' '337480af988eca993c2e98b68850f00fc6724d366346565e38941ac0d1b7c56b' 'otp'
$elixirPath = Install-Archive 'https://github.com/elixir-lang/elixir/releases/download/v1.20.4/elixir-otp-29.zip' '7863c546cda13fecc949e562e326042451dacf8fd8698a36783cb71eeb223b46' 'elixir'
$nodePath = Join-Path $taskRoot 'node-v22.23.3-win-x64'
if (!(Test-Path (Join-Path $nodePath 'node.exe'))) {
  $nodeArchive = Join-Path $taskRoot 'node-v22.23.3-win-x64.zip'
  Invoke-WebRequest 'https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip' -OutFile $nodeArchive
  if ((Get-FileHash $nodeArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71') { throw 'Node checksum mismatch' }
  Expand-Archive -LiteralPath $nodeArchive -DestinationPath $taskRoot -Force
}
$env:PATH = "$otpPath\bin;$elixirPath\bin;$nodePath;$env:PATH"
$env:MIX_HOME = Join-Path $taskRoot 'mix'
$env:HEX_HOME = Join-Path $taskRoot 'hex'
& (Join-Path $elixirPath 'bin/elixir.bat') --version
& (Join-Path $nodePath 'node.exe') --version
