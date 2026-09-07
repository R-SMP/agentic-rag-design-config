# One-time setup for propeller_studio (Windows / PowerShell).
#
#   cd "<repo root>"
#   .\propeller_studio\bootstrap.ps1
#
# Creates .venv-studio next to the repo root and installs the studio's own
# dependencies into it.  Nothing is installed into your global Python.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-studio"
$py = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creating $venv ..."
    # Python 3.10+ required (PyVista wheels, modern typing).
    py -3.13 -m venv $venv
}
& $py -m pip install --upgrade pip
& $py -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host ""
Write-Host "Installing the Node dependency for the FEG geometry backend ..."
Push-Location $root
npm install --no-audit --no-fund
Pop-Location

Write-Host ""
Write-Host "Done.  Try:"
Write-Host "  .\.venv-studio\Scripts\python -m propeller_studio gui"
Write-Host "  .\.venv-studio\Scripts\python -m propeller_studio render --params propeller_studio\examples\default.json"
