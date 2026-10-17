param(
    [ValidateSet("compare", "additions", "all")]
    [string]$Action = "all"
)

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDirectory = Split-Path -Parent $scriptDirectory
$python = Join-Path $rootDirectory ".venv\Scripts\python.exe"
$application = Join-Path $rootDirectory "swile_active_directory.py"
& $python $application $Action
