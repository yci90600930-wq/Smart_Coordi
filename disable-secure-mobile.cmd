@echo off
chcp 65001 >nul
where tailscale >nul 2>nul
if errorlevel 1 exit /b 1
tailscale serve off
echo 비공개 HTTPS 모바일 배포를 중지했습니다.
pause
