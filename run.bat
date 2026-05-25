@echo off
cd /d "%~dp0"
echo Starting Flask app...
call venv\Scripts\activate
python -m flask run --host=127.0.0.1 --port=5000
