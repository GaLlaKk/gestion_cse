$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDirectory = Split-Path -Parent $scriptDirectory
$environment = Join-Path $rootDirectory ".venv"
$python = Join-Path $environment "Scripts\python.exe"
$requirements = Join-Path $rootDirectory "requirements.txt"

py -m venv $environment
& $python -m pip install -r $requirements
