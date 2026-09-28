@echo off
echo ========================================================
echo  Iniciando ProsperAI - Clinic EHR Engine (FastAPI)
echo  URL: http://127.0.0.1:8000
echo ========================================================
.\venv\Scripts\uvicorn.exe ehr_api:app --reload --port 8000
pause
