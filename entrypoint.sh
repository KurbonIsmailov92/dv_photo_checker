#!/bin/sh
set -eu

export CV_SERVICE_URL="${CV_SERVICE_URL:-http://127.0.0.1:8000}"

python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
python_pid=$!

cleanup() {
  go_pid="${go_pid:-}"

  kill "$python_pid" 2>/dev/null || true
  if [ -n "$go_pid" ]; then
    kill "$go_pid" 2>/dev/null || true
  fi

  wait "$python_pid" 2>/dev/null || true
  if [ -n "$go_pid" ]; then
    wait "$go_pid" 2>/dev/null || true
  fi
}

trap cleanup INT TERM EXIT

attempt=0
until curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))

  if ! kill -0 "$python_pid" 2>/dev/null; then
    if wait "$python_pid"; then
      :
    else
      :
    fi
    exit 1
  fi

  if [ "$attempt" -ge 120 ]; then
    echo "Timed out waiting for the CV service to become healthy" >&2
    exit 1
  fi

  sleep 1
done

/app/main &
go_pid=$!

while :; do
  if ! kill -0 "$python_pid" 2>/dev/null; then
    if wait "$python_pid"; then
      status=0
    else
      status=$?
    fi
    kill "$go_pid" 2>/dev/null || true
    wait "$go_pid" 2>/dev/null || true
    exit "$status"
  fi

  if ! kill -0 "$go_pid" 2>/dev/null; then
    if wait "$go_pid"; then
      status=0
    else
      status=$?
    fi
    kill "$python_pid" 2>/dev/null || true
    wait "$python_pid" 2>/dev/null || true
    exit "$status"
  fi

  sleep 1
done
