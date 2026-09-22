# Argus

AI-assisted image deduplication backend.

## Quick Start

1. Copy environment variables:
   ```
   cp .env.example .env
   ```

2. Start services:
   ```
   docker compose up -d
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Run the server:
   ```
   uvicorn app.main:app --reload
   ```

5. Check health:
   ```
   curl http://localhost:8000/health
   ```
