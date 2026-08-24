# Imagem oficial do Playwright: já vem com Python, Chromium e todas as
# bibliotecas nativas necessárias pré-instaladas (evita o problema de
# dependências nativas do WeasyPrint/Playwright que tivemos localmente).
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY templates ./templates
COPY frontend ./frontend

WORKDIR /app/backend

# Render injeta a variável PORT em tempo de execução; usamos 8000 como
# fallback para rodar local via `docker run` sem precisar definir nada.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
