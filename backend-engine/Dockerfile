FROM python:3.12-slim

WORKDIR /app

# pyproject.toml is at the project root; backend-engine/ is the package source.
# Build context must be the project root (set in docker-compose.yml).
COPY pyproject.toml ./
COPY backend-engine/ ./backend-engine/
COPY docs/architecture/roles.json ./docs/architecture/roles.json
COPY puzzles.md ./puzzles.md

RUN pip install --no-cache-dir -e .

RUN chmod +x /app/backend-engine/entrypoint.sh
CMD ["/app/backend-engine/entrypoint.sh"]
