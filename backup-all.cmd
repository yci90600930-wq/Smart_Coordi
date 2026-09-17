@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 스마트제조 코디네이터 전체 백업을 시작합니다.
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -X utf8 backup_app.py
) else (
  py -3 -X utf8 backup_app.py
)
if errorlevel 1 (
  echo 백업에 실패했습니다. 위 오류 내용을 확인하세요.
) else (
  echo 프로그램, 데이터베이스, HWPX 양식과 문서가 ZIP 파일에 저장되었습니다.
)
pause
