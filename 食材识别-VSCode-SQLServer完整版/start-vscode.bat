@echo off
chcp 65001 >nul
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
python app.py
pause
