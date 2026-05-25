# Start Sensia React UI (proxies /api -> http://127.0.0.1:8000)
chcp 65001 | Out-Null
$env:PYTHONUTF8 = "1"
Set-Location "$PSScriptRoot\sensia_ui-main"
if (-not (Test-Path "node_modules")) {
  npm install
}
npm run dev
