@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 스마트제조 코디네이터 MVP - 모바일 접속 모드
echo 이 PC와 휴대폰을 같은 Wi-Fi에 연결하세요.
echo 아래에 표시될 Mobile URL 전체를 휴대폰 브라우저에서 여세요.
echo 처음 실행 시 Windows 방화벽에서 개인 네트워크 허용이 필요할 수 있습니다.
echo 종료하려면 이 창에서 Ctrl+C를 누르세요.
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -X utf8 app.py --host 0.0.0.0
) else (
  py -3 -X utf8 app.py --host 0.0.0.0
)
pause
