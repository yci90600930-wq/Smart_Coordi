@echo off
chcp 65001 >nul
cd /d "%~dp0"
where tailscale >nul 2>nul
if errorlevel 1 (
  echo Tailscale이 설치되어 있지 않습니다.
  echo PC와 휴대폰에 Tailscale을 설치하고 같은 계정으로 로그인한 뒤 다시 실행하세요.
  echo https://tailscale.com/download
  pause
  exit /b 1
)
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/' -TimeoutSec 3 ^| Out-Null; exit 0 } catch { exit 2 }"
if errorlevel 2 (
  echo 먼저 start.cmd를 실행하여 스마트제조 코디네이터 앱을 시작하세요.
  pause
  exit /b 2
)
tailscale serve --bg 8765
if errorlevel 1 (
  echo Tailscale Serve 설정에 실패했습니다. 위 안내 주소에서 HTTPS 사용을 승인한 뒤 다시 실행하세요.
  pause
  exit /b 3
)
echo.
echo 비공개 HTTPS 모바일 배포가 완료되었습니다.
tailscale serve status
echo 휴대폰 Tailscale을 연결한 뒤 위 https 주소를 여세요.
pause
