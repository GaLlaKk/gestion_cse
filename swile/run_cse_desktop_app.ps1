$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $scriptDirectory ".venv\Scripts\python.exe"
$application = Join-Path $scriptDirectory "cse_desktop_app.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Environnement Python introuvable. Exécutez debug\debug_deploy.ps1 d'abord."
}

if (-not (Test-Path -LiteralPath $application)) {
    throw "Application introuvable : $application"
}

& $python $application
exit $LASTEXITCODE
