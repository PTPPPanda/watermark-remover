@echo off
chcp 65001 >nul
echo ========================================
echo  WatermarkRemover 一键打包 (Windows)
echo  虾王开发 · 2026-06-25
echo ========================================
echo.

REM 检查 Python
echo [1/4] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未检测到 Python，请先安装 Python 3.9+
    echo    下载: https://www.python.org/downloads/
    echo    安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
python --version
echo.

REM 装 Pillow + tkinterdnd2 + pyinstaller
echo [2/4] 安装依赖（Pillow + tkinterdnd2 + pyinstaller）...
python -m pip install --upgrade pip
python -m pip install pillow tkinterdnd2 pyinstaller
echo.

REM 打 .exe
echo [3/4] 打包 WatermarkRemover.exe（这步要 1-3 分钟）...
cd /d "%~dp0"
pyinstaller --onefile --noconsole --name WatermarkRemover watermark_remover.py
echo.

REM 完成
echo [4/4] 完成！
echo.
echo ✅ 已生成: dist\WatermarkRemover.exe
echo.
echo 使用方法：
echo   1. 双击 dist\WatermarkRemover.exe 启动
echo   2. 拖入图片 → 自动去右下角水印
echo   3. 输出到原图同目录（加 _去水印 后缀）
echo.
pause
