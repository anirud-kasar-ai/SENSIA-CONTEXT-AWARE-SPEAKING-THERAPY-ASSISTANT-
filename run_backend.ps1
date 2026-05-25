# Start Sensia FastAPI backend (from project root)
chcp 65001 | Out-Null
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
& .\venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8000 --reload
