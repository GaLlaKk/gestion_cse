$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $scriptDirectory ".venv\Scripts\python.exe"
$application = Join-Path $scriptDirectory "cse_file_manager.py"
& $python $application
