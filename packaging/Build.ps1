param(
    [ValidateSet('onefile', 'onedir', 'installer')][string]$Mode = 'onefile',
    [string]$VlcDirectory = 'C:\Program Files\VideoLAN\VLC'
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project 'venv\Scripts\python.exe'
$compiler = $null
if ($Mode -eq 'installer') {
    $compiler = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $compiler) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($command) { $compiler = $command.Source }
    }
    if (-not $compiler) { throw 'Install Inno Setup 6, then run build.cmd again.' }
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Missing venv. Follow the first-time setup in GUIDELINE.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $VlcDirectory 'libvlc.dll'))) {
    throw 'Install VLC 3.x x64, or pass -VlcDirectory with its installation folder.'
}
$env:IPVIDEX_VLC_DIR = $VlcDirectory
$env:IPVIDEX_BUILD_MODE = if ($Mode -eq 'installer') { 'onedir' } else { $Mode }
Push-Location $project
try {
    & $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/IPVidex.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    & $python -m pip freeze | Set-Content 'dist\build-packages.txt' -Encoding utf8
    if ($Mode -in @('onedir', 'installer')) {
        Copy-Item -LiteralPath 'packaging\CUSTOMER-README.txt' -Destination 'dist\IPVidex\README.txt' -Force
        Copy-Item -LiteralPath 'LICENSE' -Destination 'dist\IPVidex\LICENSE.txt' -Force
        if ($Mode -eq 'installer') {
            & $compiler (Join-Path $PSScriptRoot 'Installer.iss')
            if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
            Write-Host 'Installer ready: dist/IPVidex-Setup.exe'
        }
        else { Write-Host 'Portable folder build: dist/IPVidex. Zip and send the entire folder.' }
    }
    else {
        Copy-Item -LiteralPath 'packaging\CUSTOMER-README.txt' -Destination 'dist\README.txt' -Force
        Copy-Item -LiteralPath 'LICENSE' -Destination 'dist\LICENSE.txt' -Force
        Write-Host 'Single-file build: dist/IPVidex.exe. Send that one file.'
    }
}
finally { Pop-Location }
