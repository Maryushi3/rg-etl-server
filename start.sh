#!/usr/bin/env bash
# Launcher for Linux / macOS / Raspberry Pi (start.bat is the Windows twin).
# Device detection and the "which device is which" prompts live in `server.py --auto`;
# without a terminal (systemd, cron) it never prompts, so pass --serial / --arduino-serial there.
#
#   ./start.sh [--serial /dev/...] [--arduino-serial /dev/...] [--rs485-gpio N] [--port N]
#   PORT=9000 ./start.sh
set -euo pipefail
cd "$(dirname "$0")"
exec python3 server.py --auto --port "${PORT:-8080}" "$@"
