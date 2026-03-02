@echo off
cd /d "C:\Rafa\Project"
call .venv\Scripts\activate
streamlit run app.py
pause