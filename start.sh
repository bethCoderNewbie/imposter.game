#!/usr/bin/env bash
set -euo pipefail

# ── 0. Windows Firewall — open port 80 for LAN access ─────────────────────────
# Rules created by New-NetFirewallRule are persistent (survive reboots).
# This is a fast no-op once the rule exists; elevation is only needed the first time.
if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command "
    \$name = 'Imposter Game - Port 80'
    if (-not (Get-NetFirewallRule -DisplayName \$name -ErrorAction SilentlyContinue)) {
      try {
        New-NetFirewallRule -DisplayName \$name -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow | Out-Null
        Write-Host 'Firewall rule added for port 80'
      } catch {
        Write-Warning 'Could not add firewall rule for port 80 — run start.sh once as Administrator to fix LAN access permanently.'
      }
    }
  " 2>/dev/null || true
fi

# ── 1. Determine LAN IP ────────────────────────────────────────────────────────

if [ -n "${1:-}" ]; then
  LAN_IP="$1"
else
  # Prefer the IP used to reach the default gateway (Linux, macOS, Git Bash/WSL)
  LAN_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '/src/{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)

  # macOS fallback
  if [ -z "$LAN_IP" ]; then
    LAN_IP=$(/sbin/ipconfig getifaddr en0 2>/dev/null || true)
  fi

  # WSL/Windows fallback — exclude loopback, APIPA, and vEthernet virtual adapters
  if [ -z "$LAN_IP" ]; then
    LAN_IP=$(powershell.exe -NoProfile -Command \
      "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { \$_.IPAddress -notmatch '^(127\.|169\.254\.)' -and \$_.InterfaceAlias -notlike 'vEthernet*' } | Sort-Object PrefixLength -Descending | Select-Object -First 1).IPAddress" \
      2>/dev/null | tr -d '\r\n' || true)
  fi
fi

if [ -z "$LAN_IP" ]; then
  echo "ERROR: Could not auto-detect LAN IP. Run:  ./start.sh 192.168.X.X"
  exit 1
fi

export HOST_IP="http://${LAN_IP}"

echo "LAN IP     : $LAN_IP"
echo "Mobile URL : ${HOST_IP}/?g=<GAME_CODE>"
echo "Display    : ${HOST_IP}/display/?g=<GAME_CODE>"
echo "API        : ${HOST_IP}/api/health"
echo ""

# ── 2. GPU detection ──────────────────────────────────────────────────────────
COMPOSE_FILES="-f docker-compose.yml"
if nvidia-smi &>/dev/null 2>&1; then
  echo "GPU detected  — narrator will use GPU-accelerated Ollama + Kokoro"
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
else
  echo "No GPU detected — narrator will run on CPU (inference ~10–30 s per line)"
fi

# ── 3. Build and launch ────────────────────────────────────────────────────────
# HOST_IP is picked up by docker-compose.yml → frontend-display build arg → VITE_HOST_IP
# so the QR code is baked with the correct LAN address at build time.

# shellcheck disable=SC2086
docker compose $COMPOSE_FILES up --build "$@"
