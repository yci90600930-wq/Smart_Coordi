@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 스마트제조 코디네이터 MVP
echo 브라우저에서 http://127.0.0.1:8765 를 여세요.
echo 종료하려면 이 창에서 Ctrl+C를 누르세요.
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -X utf8 app.py
) else (
  py -3 -X utf8 app.py
)
pause
