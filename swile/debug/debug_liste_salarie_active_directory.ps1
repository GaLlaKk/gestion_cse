$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDirectory = Split-Path -Parent $scriptDirectory
$python = Join-Path $rootDirectory ".venv\Scripts\python.exe"
$application = Join-Path $rootDirectory "liste_salarie_active_directory.py"
& $python $application
