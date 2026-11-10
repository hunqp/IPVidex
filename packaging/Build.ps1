param(
    [ValidateSet('onefile', 'onedir')][string]$Mode = 'onefile',
    [string]$VlcDirectory = 'C:\Program Files\VideoLAN\VLC'
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project 'venv\Scripts\python.exe'
$env:IPVIDEX_VLC_DIR = $VlcDirectory
$env:IPVIDEX_BUILD_MODE = $Mode
Push-Location $project
try {
    & $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/IPVidex.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    & $python -m pip freeze | Set-Content 'dist\build-packages.txt' -Encoding utf8
    if ($Mode -eq 'onedir') {
        Copy-Item -LiteralPath 'packaging\CUSTOMER-README.txt' -Destination 'dist\IPVidex\README.txt' -Force
        Copy-Item -LiteralPath 'LICENSE' -Destination 'dist\IPVidex\LICENSE.txt' -Force
        Write-Host 'Portable folder build: dist/IPVidex. Zip and send the entire folder.'
    }
    else {
        Copy-Item -LiteralPath 'packaging\CUSTOMER-README.txt' -Destination 'dist\README.txt' -Force
        Copy-Item -LiteralPath 'LICENSE' -Destination 'dist\LICENSE.txt' -Force
        Write-Host 'Single-file build: dist/IPVidex.exe. Send that one file.'
    }
}
finally { Pop-Location }
