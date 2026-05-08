#!/usr/bin/env bash
#
# GhostWatch — one-command setup + run
#
# Usage:
#   ./run.sh           # set up (idempotent) and start both services
#   ./run.sh stop      # stop everything
#   ./run.sh logs      # tail all service logs
#   ./run.sh status    # show what's running
#
# What this does:
#   1. Finds a Python 3.10+ interpreter (tries 3.13/3.12/3.11/3.10/python3)
#   2. Checks Node 20+ and npm
#   3. Creates 2 isolated Python venvs (sim / ghostwatch)
#   4. Installs Python + Node deps (skips if already installed)
#   5. Builds the React frontend into ghostwatch/frontend/dist
#   6. Starts the 2 services in the background:
#        - SimSat orbit + imagery       → http://localhost:9005
#        - GhostWatch (API + dashboard) → http://localhost:9010
#   7. Opens the dashboard in your browser
#
# All logs go to ./logs/. Stop with `./run.sh stop`.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"
PIDS="$ROOT/.pids"
mkdir -p "$LOGS" "$PIDS"

B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
log()    { printf "${C}[$(date +%H:%M:%S)]${N} $1\n"; }
ok()     { printf "${G}✓${N} $1\n"; }
warn()   { printf "${Y}⚠${N} $1\n"; }
err()    { printf "${R}✗${N} $1\n" >&2; }
section(){ printf "\n${B}── $1 ──${N}\n"; }

cmd_stop() {
  section "Stopping services"

  # Kill recorded PIDs and their immediate children (the bash wrappers).
  for svc in sim ghostwatch; do
    pidfile="$PIDS/$svc.pid"
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null && ok "stopped $svc (pid $pid)"
        pkill -P "$pid" 2>/dev/null || true
      else
        warn "$svc not running (stale pidfile)"
      fi
      rm -f "$pidfile"
    else
      warn "$svc not running"
    fi
  done

  # Sweep the ports twice — uvicorn's reloader may respawn workers between sweeps.
  for attempt in 1 2; do
    sleep 0.5
    any_killed=false
    for port in 9005 9010; do
      while true; do
        pids=$(lsof -ti tcp:$port 2>/dev/null || true)
        [ -z "$pids" ] && break
        for p in $pids; do
          kill -9 "$p" 2>/dev/null && any_killed=true
        done
      done
    done
    [ "$any_killed" = "true" ] && [ $attempt -eq 1 ] && ok "killed orphan listeners on 9005/9010"
  done

  # Final check
  for port in 9005 9010; do
    if lsof -ti tcp:$port >/dev/null 2>&1; then
      warn "port $port STILL bound after kill attempts — something else is holding it"
    fi
  done
}

cmd_logs() {
  section "Tailing logs (Ctrl+C to exit)"
  exec tail -F "$LOGS"/sim.log "$LOGS"/ghostwatch.log
}

cmd_status() {
  section "Service status"
  for svc in sim ghostwatch; do
    pidfile="$PIDS/$svc.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat $pidfile)" 2>/dev/null; then
      ok "$svc — running (pid $(cat $pidfile))"
    else
      warn "$svc — stopped"
    fi
  done
}

case "${1:-start}" in
  stop)   cmd_stop;   exit 0 ;;
  logs)   cmd_logs;   exit 0 ;;
  status) cmd_status; exit 0 ;;
  start)  ;;
  *) err "Unknown command: $1"; echo "Usage: $0 [start|stop|logs|status]"; exit 1 ;;
esac

section "Prerequisites"

# Find a Python 3.10+ interpreter — try named versions before falling back to python3.
# This handles macOS / multi-version setups where `python3` might point at an old build.
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
      PYTHON=$(command -v "$candidate")
      PY_VER=$("$candidate" -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
      ok "python $PY_VER ($PYTHON)"
      break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  err "Python 3.10+ not found. Install with: brew install python@3.11  (or your distro's 3.10+ package)"
  exit 1
fi

command -v node >/dev/null || { err "node not found (need v20+)"; exit 1; }
NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
[ "$NODE_VER" -ge 20 ] || { err "Node 20+ required (have v$NODE_VER)"; exit 1; }
ok "node $(node -v)"

command -v npm >/dev/null || { err "npm not found"; exit 1; }
ok "npm $(npm -v)"

setup_venv() {
  local name=$1 dir=$2 reqs=$3
  if [ ! -d "$dir/.venv" ]; then
    log "creating venv for $name (using $PYTHON)..."
    (cd "$dir" && "$PYTHON" -m venv .venv)
    (cd "$dir" && .venv/bin/pip install --quiet --upgrade pip wheel)
    (cd "$dir" && .venv/bin/pip install --quiet -r "$reqs")
    ok "$name venv ready"
  else
    ok "$name venv already exists (skip)"
  fi
}

section "Python environments"
setup_venv "sim"        "$ROOT/SimSat/src/sim" "requirements.txt"
setup_venv "ghostwatch" "$ROOT"                "ghostwatch/requirements.txt"

section "Frontend build"
if [ ! -d "$ROOT/ghostwatch/frontend/node_modules" ]; then
  log "installing npm packages (~30s, one-time)..."
  (cd "$ROOT/ghostwatch/frontend" && npm install --silent)
  ok "node modules installed"
else
  ok "node_modules already present (skip)"
fi

if [ ! -f "$ROOT/ghostwatch/frontend/dist/index.html" ]; then
  log "building React bundle..."
  (cd "$ROOT/ghostwatch/frontend" && npm run build --silent)
  ok "frontend built"
else
  ok "frontend dist already exists (skip — rebuild manually if you changed sources)"
fi

section "Starting services"

cmd_stop >/dev/null 2>&1 || true

start_service() {
  local name=$1; shift
  local logfile="$LOGS/$name.log"
  : > "$logfile"
  ( "$@" >>"$logfile" 2>&1 ) &
  echo $! > "$PIDS/$name.pid"
  ok "$name started (pid $!), log: logs/$name.log"
}

start_service "sim" \
  bash -c "cd '$ROOT/SimSat/src/sim' && SIM_PORT=9005 DASHBOARD_URL=http://localhost:9010 .venv/bin/python main.py --timing 25 --time-step 20"

start_service "ghostwatch" \
  bash -c "cd '$ROOT' && GHOSTWATCH_MODEL=AryanNsc/LMF2.5-VL-Ghost-V1 SIMSAT_API_URL=http://localhost:9005 .venv/bin/python -m ghostwatch.main"

section "Health checks"

wait_for() {
  local name=$1 url=$2 timeout=${3:-30}
  local elapsed=0
  while [ $elapsed -lt $timeout ]; do
    if curl -fsS -o /dev/null --max-time 2 "$url" 2>/dev/null; then
      ok "$name responsive ($url)"
      return 0
    fi
    if ! kill -0 "$(cat $PIDS/$name.pid)" 2>/dev/null; then
      err "$name crashed during startup — check logs/$name.log"
      tail -20 "$LOGS/$name.log" | sed 's/^/    | /'
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  warn "$name not responsive after ${timeout}s (continuing — check logs/$name.log)"
}

wait_for "sim"        "http://localhost:9005/data/current/position"  30
wait_for "ghostwatch" "http://localhost:9010/api/health"             120

section "Ready"
printf "${G}${B}GhostWatch is running:${N}\n\n"
printf "  Dashboard:  ${C}http://localhost:9010${N}\n"
printf "  API docs:   ${C}http://localhost:9010/docs${N}\n"
printf "  Sim API:    ${C}http://localhost:9005/docs${N}\n\n"
printf "  Logs:       ${C}./run.sh logs${N}\n"
printf "  Status:     ${C}./run.sh status${N}\n"
printf "  Stop:       ${C}./run.sh stop${N}\n\n"

if command -v open >/dev/null 2>&1; then
  open http://localhost:9010
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:9010
fi

printf "${Y}Note:${N} The first ${B}Scan Now${N} click downloads the model from HuggingFace (~900 MB)\n"
printf "and runs CPU inference (~30-90s per scan on Mac without GPU).\n"
