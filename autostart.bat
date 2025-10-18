@echo off
REM Переходим в папку, где лежит bot.py (если батник в другой папке)
cd /d "%~dp0"

REM Запускаем бота
python bot.py

pause