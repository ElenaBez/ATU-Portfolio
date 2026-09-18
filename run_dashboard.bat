@echo off
cd /d "%~dp0"
if not exist .venv (
    py -3.14 -m venv .venv
    call .venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate
)
streamlit run app.py
