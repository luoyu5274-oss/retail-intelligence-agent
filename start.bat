@echo off
chcp 65001 >nul
title 零售研究助手

set "ROOT=%~dp0"

echo.
echo  ==========================================
echo    零售研究助手  Retail Intelligence Agent
echo  ==========================================
echo.

echo  [1/2] 启动后端 FastAPI (端口 8000)...
cd /d "%ROOT%backend"
start "Backend" cmd /k "title 后端-Backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
cd /d "%ROOT%"

echo  等待后端启动 (3秒)...
timeout /t 3 /nobreak >nul

echo  [2/2] 启动前端 React (端口 5173)...
cd /d "%ROOT%frontend"
start "Frontend" cmd /k "title 前端-Frontend && npm run dev"
cd /d "%ROOT%"

echo  等待前端启动 (6秒)...
timeout /t 6 /nobreak >nul

echo.
echo  正在打开浏览器...
powershell -Command "Start-Process 'http://localhost:5173'"

echo.
echo  ✅ 完成！如果浏览器没有自动打开，请手动访问：
echo     http://localhost:5173
echo.
echo  按任意键关闭此窗口（两个服务窗口继续运行）
pause >nul