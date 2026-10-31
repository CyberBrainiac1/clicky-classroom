param([switch]$FullClicky)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    $uv=Get-Command uv -ErrorAction SilentlyContinue
    if(-not $uv){throw 'Install uv or create a Python3.11/3.12 virtual environment manually; see CLASSROOM.md.'}
    if(-not(Test-Path -LiteralPath '.venv\Scripts\python.exe')){
        & $uv.Source venv --python 3.11 .venv
        if($LASTEXITCODE -ne 0){throw 'Could not create the Python environment'}
    }
    & $uv.Source pip install --python .venv\Scripts\python.exe -r requirements-classroom.txt
    if($LASTEXITCODE -ne 0){throw 'Classroom dependency installation failed'}
    if($FullClicky){
        & $uv.Source pip install --python .venv\Scripts\python.exe -r requirements.txt
        if($LASTEXITCODE -ne 0){throw 'Full Clicky dependency installation failed'}
    }
    Write-Output 'Ready. Run run-classroom.cmd when you want the window. No recording has started.'
    Write-Output 'Use Prepare offline Whisper or select an existing Parakeet model folder, then choose your local notes model.'
} finally {Pop-Location}
