#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — add your ANTHROPIC_API_KEY then re-run."
  exit 1
fi

cd backend
pip install -r requirements.txt -q
echo ""
echo "SkillSense AI running at http://localhost:8000"
echo "Press Ctrl+C to stop."
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
