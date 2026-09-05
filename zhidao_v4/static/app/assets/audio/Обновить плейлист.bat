@echo off
chcp 65001 > nul
rem Двойной клик по этому файлу пересобирает playlist.json по содержимому папки.
rem Лежит рядом с музыкой намеренно: искать его в другом месте незачем.
setlocal
set "PYTHONIOENCODING=utf-8"
pushd "%~dp0..\..\..\..\.."
if not exist ".venv-web\Scripts\python.exe" goto :nopython
".venv-web\Scripts\python.exe" "tools\build_playlist.py"
goto :done

:nopython
echo.
echo Не найден .venv-web\Scripts\python.exe
echo Похоже, папка проекта переехала или окружение не создано.

:done
popd
echo.
pause
