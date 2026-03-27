FROM python:3.12-slim

WORKDIR /app

# pyproject.toml is at the project root; backend-engine/ is the package source.
# Build context must be the project root (set in docker-compose.yml).
COPY pyproject.toml ./
COPY backend-engine/ ./backend-engine/
COPY docs/architecture/roles.json ./docs/architecture/roles.json
COPY puzzles.md ./puzzles.md

RUN pip install --no-cache-dir -e .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
