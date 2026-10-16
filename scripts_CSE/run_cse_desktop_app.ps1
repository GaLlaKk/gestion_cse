py -m venv scripts_CSE\.venv
.\scripts_CSE\.venv\Scripts\python.exe -m pip install -r scripts_CSE\requirements.txt
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $scriptDirectory ".venv\Scripts\python.exe"
$application = Join-Path $scriptDirectory "cse_desktop_app.py"
& $python $application
