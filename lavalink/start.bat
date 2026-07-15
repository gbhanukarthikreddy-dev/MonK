@echo off
cd /d "%~dp0"
if not exist Lavalink.jar (
  echo Run download_lavalink.ps1 first.
  pause
  exit /b 1
)
java -Xms256M -Xmx1G -jar Lavalink.jar
pause
