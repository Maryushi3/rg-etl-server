#!/usr/bin/env bash
# Launcher: detects serial devices, asks which is which (when run interactively), starts server.py.
# Non-interactive (systemd, cron): never prompts; pass --serial / --arduino-serial explicitly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8080}"
SERIAL=""
ARDUINO_SERIAL=""
RS485_GPIO=""

usage() {
  echo "Usage: $0 [--serial /dev/...] [--arduino-serial /dev/...] [--rs485-gpio N] [--port N]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial) [[ $# -ge 2 ]] || usage; SERIAL="$2"; shift 2 ;;
    --arduino-serial) [[ $# -ge 2 ]] || usage; ARDUINO_SERIAL="$2"; shift 2 ;;
    --rs485-gpio) [[ $# -ge 2 ]] || usage; RS485_GPIO="$2"; shift 2 ;;
    --port) [[ $# -ge 2 ]] || usage; PORT="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

# Can we prompt? (false under systemd, where /dev/tty can't be opened)
INTERACTIVE=0
if [[ -t 1 || -t 2 ]] && { : </dev/tty; } 2>/dev/null; then INTERACTIVE=1; fi

# ask VAR "prompt" default  -> reads an answer from the terminal, or uses default
ask() {
  local __var="$1" __prompt="$2" __default="${3:-}" __ans=""
  if [[ $INTERACTIVE -eq 1 ]]; then
    read -rp "$__prompt" __ans </dev/tty || __ans=""
  fi
  printf -v "$__var" '%s' "${__ans:-$__default}"
}

detect_devices() {
  case "$(uname -s)" in
    Darwin) ls /dev/cu.usbmodem* /dev/cu.usbserial* 2>/dev/null || true ;;
    Linux)  ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA* 2>/dev/null || true ;;
  esac
}

describe() {
  local dev="$1"
  if command -v udevadm &>/dev/null; then
    udevadm info --name="$dev" 2>/dev/null | grep -E 'ID_VENDOR=|ID_MODEL=' | head -2 | cut -d= -f2 | tr '\n' ' ' || true
  fi
}

# Raspberry Pi with built-in UART + MAX485 (see README)
PI_AUTO=0
if [[ -z "$SERIAL" && "$(uname -s)" == "Linux" && -e /dev/ttyAMA0 ]] && python3 -c "import RPi.GPIO" 2>/dev/null; then
  echo "Raspberry Pi detected with RPi.GPIO." >&2
  SERIAL="/dev/ttyAMA0"; echo "RS485: $SERIAL (auto)" >&2
  [[ -z "$RS485_GPIO" ]] && RS485_GPIO="26" && echo "RS485 GPIO: pin $RS485_GPIO (auto)" >&2
  PI_AUTO=1
fi

DEVICES=()
while IFS= read -r line; do
  [[ -n "$line" && "$line" != "$SERIAL" && "$line" != "$ARDUINO_SERIAL" ]] && DEVICES+=("$line")
done < <(detect_devices)
[[ $PI_AUTO -eq 1 ]] && { tmp=(); for d in ${DEVICES[@]+"${DEVICES[@]}"}; do [[ "$d" == /dev/ttyAMA* ]] || tmp+=("$d"); done; DEVICES=(${tmp[@]+"${tmp[@]}"}); }

# pick_device VAR "question"  -> lets the user pick one of DEVICES (0 = none)
pick_device() {
  local __var="$1" __q="$2" choice i
  echo "$__q" >&2
  for i in "${!DEVICES[@]}"; do echo "  [$((i+1))] ${DEVICES[$i]}  $(describe "${DEVICES[$i]}")" >&2; done
  ask choice "Choose [1-${#DEVICES[@]}] or 0 for none: " 0
  if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#DEVICES[@]} )); then
    printf -v "$__var" '%s' "${DEVICES[$((choice-1))]}"
    local rest=(); for i in "${!DEVICES[@]}"; do (( i == choice-1 )) || rest+=("${DEVICES[$i]}"); done
    DEVICES=(${rest[@]+"${rest[@]}"})
  fi
}

if [[ ${#DEVICES[@]} -gt 0 && $INTERACTIVE -eq 0 && ( -z "$SERIAL" || -z "$ARDUINO_SERIAL" ) ]]; then
  echo "Not interactive: skipping device prompts (found: ${DEVICES[*]}). Use --serial / --arduino-serial." >&2
elif [[ ${#DEVICES[@]} -gt 0 ]]; then
  if [[ -z "$SERIAL" ]]; then
    if [[ ${#DEVICES[@]} -eq 1 ]]; then
      echo "Single serial device found: ${DEVICES[0]}  $(describe "${DEVICES[0]}")" >&2
      ask role "Is it the [R]S485 display interface or the DHT22 [A]rduino? " R
      if [[ "$role" =~ ^[Aa] ]]; then ARDUINO_SERIAL="${DEVICES[0]}"; else SERIAL="${DEVICES[0]}"; fi
      DEVICES=()
    else
      pick_device SERIAL "Which device is the RS485 display interface?"
    fi
  fi
  if [[ -z "$ARDUINO_SERIAL" && ${#DEVICES[@]} -eq 1 ]]; then
    ask yn "Use ${DEVICES[0]} as the DHT22 Arduino? [Y/n]: " Y
    [[ "$yn" =~ ^[Nn] ]] || ARDUINO_SERIAL="${DEVICES[0]}"
  elif [[ -z "$ARDUINO_SERIAL" && ${#DEVICES[@]} -gt 1 ]]; then
    pick_device ARDUINO_SERIAL "Which device is the DHT22 Arduino?"
  fi
fi

if [[ -z "$SERIAL" ]]; then
  echo "No RS485 interface selected: server tries its default /dev/ttyAMA0, else SIMULATION MODE." >&2
  echo "Pass --serial /dev/... to use a specific device." >&2
fi
[[ -n "$SERIAL" ]] && echo "RS485:   $SERIAL" >&2
[[ -n "$ARDUINO_SERIAL" ]] && echo "Arduino: $ARDUINO_SERIAL" >&2

cd "$SCRIPT_DIR"
ARGS=(--port "$PORT")
[[ -n "$SERIAL" ]] && ARGS+=(--serial "$SERIAL")
[[ -n "$ARDUINO_SERIAL" ]] && ARGS+=(--arduino-serial "$ARDUINO_SERIAL")
[[ -n "$RS485_GPIO" ]] && ARGS+=(--rs485-gpio "$RS485_GPIO")
exec python3 server.py "${ARGS[@]}"
