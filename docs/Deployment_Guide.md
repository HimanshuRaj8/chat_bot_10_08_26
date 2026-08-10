# Deployment Guide — Enterprise Approval System AI Assistant

---

## 🏗️ Prerequisites

1. **Python Runtime**: Python 3.11+
2. **LLM Engine**: [Ollama](https://ollama.ai/) running locally or on a GPU server with `qwen2.5:3b` model:
   ```bash
   ollama pull qwen2.5:3b
   ```

---

## 🚀 Environment Setup & Deployment

### 1. Clone & Configure

#### 🪟 Windows (Command Prompt / PowerShell)
```cmd
git clone https://github.com/HimanshuRaj8/enterprise-approval-ai-assistant.git
cd enterprise-approval-ai-assistant

python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
```

#### 🍎 / 🐧 macOS & Linux (Terminal)
```bash
git clone https://github.com/HimanshuRaj8/enterprise-approval-ai-assistant.git
cd enterprise-approval-ai-assistant

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

### 2. Run Production Backend V3 (Port 8002)

#### Windows (Waitress / Direct WSGI)
```cmd
python backend_v3/app.py
```

#### macOS / Linux (Gunicorn / Direct WSGI)
```bash
.venv/bin/python backend_v3/app.py
# OR using Gunicorn:
gunicorn --bind 0.0.0.0:8002 backend_v3.app:app --workers 4 --timeout 120
```

---

## 🧪 System Verification & Health Check

Run the automated system verification script:

### Windows:
```cmd
python scripts/health_check.py
```

### macOS / Linux:
```bash
.venv/bin/python scripts/health_check.py
```
