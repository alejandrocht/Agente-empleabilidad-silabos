#!/usr/bin/env bash

# Resolve project paths
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Clean up existing processes on target ports
echo "==> Verificando puertos 8001 y 3000..."
lsof -ti:8001,3000 | xargs kill -9 2>/dev/null || true
sleep 1

# Cleanup on exit
cleanup() {
    echo ""
    echo "==> Deteniendo servicios..."
    kill $(jobs -p) 2>/dev/null || true
    lsof -ti:8001,3000 | xargs kill -9 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Backend auto-restart loop
run_backend() {
    while true; do
        echo "[$(date '+%H:%M:%S')] [BACKEND] Iniciando FastAPI / Uvicorn en http://127.0.0.1:8001..."
        cd "$BACKEND_DIR" && ./.venv/bin/python -m uvicorn api.servidor:app --reload --port 8001
        EXIT_CODE=$?
        echo "[$(date '+%H:%M:%S')] [BACKEND] Proceso finalizó con código $EXIT_CODE. Reiniciando en 2 segundos..."
        sleep 2
    done
}

# Frontend auto-restart loop
run_frontend() {
    while true; do
        echo "[$(date '+%H:%M:%S')] [FRONTEND] Iniciando Next.js en http://localhost:3000..."
        cd "$FRONTEND_DIR" && npm run dev
        EXIT_CODE=$?
        echo "[$(date '+%H:%M:%S')] [FRONTEND] Proceso finalizó con código $EXIT_CODE. Reiniciando en 2 segundos..."
        sleep 2
    done
}

echo "=========================================="
echo "  CIAR: Iniciando Frontend y Backend      "
echo "  - Backend:  http://127.0.0.1:8001       "
echo "  - Frontend: http://localhost:3000       "
echo "  (Modo supervisado con auto-reinicio)    "
echo "=========================================="

run_backend &
run_frontend &

# Wait for all background loops
wait
