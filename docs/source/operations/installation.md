# Installation

## Requirements

Local development requires:

- Python 3.11 or newer;
- Node.js 20 or newer;
- npm;
- Docker and Docker Compose for full-stack execution;
- an LLM provider API key.

## Backend Setup

```bash
git clone <repository-url>
cd ai-testplan-generator
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and set the provider keys you need.

Run the backend:

```bash
uvicorn ai_testplan_generator.api.app:create_app --factory --reload --port 8000
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Create Admin User

```bash
python scripts/create_admin.py
```

Then sign in with the configured test account.
