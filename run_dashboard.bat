@echo off
cd /d "%~dp0"
if not exist .venv (
    rem prefer Python 3.14; fall back to any installed Python 3
    py -3.14 -m venv .venv 2>nul || py -3 -m venv .venv
    call .venv\Scripts\activate
    python -m pip install --upgrade pip
) else (
    call .venv\Scripts\activate
)
rem installs anything new in requirements.txt (quick when nothing has changed)
pip install -q -r requirements.txt
streamlit run app.py
