@echo off
echo Starting SkillSense AI...
cd /d "%~dp0"

if not exist ".env" (
    copy .env.example .env
    echo Created .env from template. Please add your ANTHROPIC_API_KEY to .env
    pause
    exit /b 1
)

cd backend
pip install -r requirements.txt --quiet
echo.
echo SkillSense AI is running at http://localhost:8000
echo Press Ctrl+C to stop.
echo.
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
