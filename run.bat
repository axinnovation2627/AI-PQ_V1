@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo [설치] 가상환경을 만들고 필요한 라이브러리를 설치합니다...
  python -m venv .venv || goto :err
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements.txt || goto :err
)
if not exist .env (
  copy .env.example .env >nul
  echo [안내] .env 파일을 만들었습니다. GEMINI_API_KEY 값을 넣은 뒤 다시 실행하세요.
  notepad .env
)
echo PQ 경력평가: http://127.0.0.1:8765  (종료: Ctrl+C)
start "" http://127.0.0.1:8765
.venv\Scripts\python -m uvicorn pqweb.server:app --host 127.0.0.1 --port 8765
goto :eof
:err
echo 설치 중 오류가 발생했습니다.
pause
