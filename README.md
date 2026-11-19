# RG Display Server

HTTP server for controlling R&G LED displays over RS485. Features a web UI with a live preview of what's on the display, queue management (drag to reorder, works on phones), override, presets, scheduling, namedays, and DHT22 sensor display. The web UI is self-contained (no CDN), so it works on an offline Pi.

## Quick Start

```bash
# Auto-detect serial devices (interactive)
./start.sh

# Or specify devices directly
./start.sh --serial /dev/cu.usbmodem2101 --arduino-serial /dev/cu.usbmodem2103

# Or run directly (simulation mode if no serial device)
python3 server.py --port 8080
```

On Windows, double-click `start.bat` or run it from a terminal (`start.bat --serial COM3`); see [Windows](#windows).

Open http://localhost:8080 in a browser.

## Requirements

- Python 3.7+ on Linux, macOS or Windows (no other dependencies for simulation mode)
- `pyserial` (`pip install pyserial`) to talk to the display / Arduino
- On Windows also `tzdata` (`pip install tzdata`) so time sync can use named time zones
- On Raspberry Pi with MAX485: `RPi.GPIO` (`pip install RPi.GPIO`)

## Raspberry Pi Setup

Connect MAX485 to the Pi's UART on GPIO 14 (TXD) and 15 (RXD). Tie RE and DE together to a free GPIO pin (e.g. GPIO 26). Enable the UART in `/boot/config.txt`:

```
enable_uart=1
dtoverlay=disable-bt   # frees ttyAMA0 (PL011 UART) from Bluetooth
```

Reboot, then run:

```bash
pip install pyserial RPi.GPIO
./start.sh --serial /dev/ttyAMA0 --rs485-gpio 26
```

## Usage

```bash
python3 server.py [--port PORT] [--serial DEVICE] [--arduino-serial DEVICE]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `8080` | HTTP server port |
| `--bind` | `0.0.0.0` | Address to listen on (`127.0.0.1` = this machine only) |
| `--serial` | `/dev/ttyAMA0` (none on Windows) | RS485 display serial device, e.g. `/dev/ttyUSB0` or `COM3`. Runs in simulation mode if not found, and connects automatically when the device appears (e.g. USB adapter plugged in later or re-plugged). |
| `--arduino-serial` | *(none)* | Serial port for DHT22 temperature/humidity sensor |
| `--rs485-gpio` | *(none)* | BCM GPIO pin tied to MAX485 RE+DE for direction control |
| `--auto` | off | Detect serial devices and ask which is which (what the launchers use) |
| `--list-ports` | | Print the detected serial ports and exit |

## start.sh / start.bat

The launchers run `server.py --auto`, which detects USB serial devices (and the Pi's UART + RPi.GPIO, using GPIO 26 for direction) and asks you to assign each one (RS485 display or DHT22 Arduino). `start.sh` is for Linux and macOS, `start.bat` for Windows. Override detection with `--serial` or `--arduino-serial`. Change the HTTP port with `--port N` or the `PORT` environment variable.

When run without a terminal (e.g. from systemd) it never prompts; pass the devices explicitly there.

## Windows

1. Install Python 3 from python.org (tick "Add python.exe to PATH").
2. `py -m pip install pyserial tzdata`
3. Plug in the USB-RS485 adapter. FTDI and CP210x adapters install their drivers automatically; cheap CH340 ones may need the CH340 driver.
4. Run `start.bat` and pick the COM ports, or pass them: `start.bat --serial COM3 --arduino-serial COM4`. `start.bat --list-ports` shows what's connected.
5. Allow Python through Windows Firewall when asked, if phones on the network should reach the web UI.

To start it automatically, create a Task Scheduler task "At log on" that runs `start.bat` with explicit `--serial` / `--arduino-serial` (there's no terminal to answer prompts).

## Files

| File | Purpose |
|------|---------|
| `server.py` | HTTP server + RS485 display driver + queue logic |
| `webui.html` | Single-page web interface |
| `start.sh` | Launcher for Linux / macOS (device detection via `server.py --auto`) |
| `start.bat` | Launcher for Windows |
| `messages.json` | Persisted message queue (gitignored) |
| `settings.json` | Persisted settings (gitignored) |

Both files are written atomically (temp file + rename), so a power cut during a save can't truncate them. If a file can't be parsed at startup it is renamed to `<name>.corrupt-<timestamp>` and kept, rather than being silently overwritten. Unknown fields in either file are preserved.

## Presets

Each message has a `preset_id` that determines how it renders on the display:

| Preset | Description |
|--------|-------------|
| `single-static` | Single line of static text |
| `custom` | Raw single command: text, font, line, alignment, `pos_x`, `width` (right edge), scroll |
| `scrolling` | Single line of scrolling text |
| `two-static` | Two static lines (separated by `\|\|` in text) |
| `top-bottom-scroll` | Top static line, bottom scrolling line |
| `bus` | Bus route (big font left) + destination (small font right) + scrolling route info |
| `train` | Train station display (from/to + train number) |
| `clock` | Current time (big font) + date + weekday |
| `imieniny` | Polish nameday display (top static, bottom scrolling names) |
| `imieniny-static` | Polish nameday — top "IMIENINY", bottom 2-3 names static |
| `imieniny-scroll` | Single scrolling line "Imieniny: &lt;names&gt;" |
| `do-konca-roku` | Days until end of year — top text, bottom count (checkbox for split rows) |
| `do-konca-roku-scroll` | Single scrolling line with count |
| `dht22` | Temperature and humidity from DHT22 sensor |

## Protocol notes

Frames are `02 | address | length | payload | checksum | 03`, all as ASCII hex characters (see [communication.md](https://github.com/HiszpanInk/rg-screens-things/blob/main/communication.md)). Things confirmed from the original controller's traffic dumps in that repo:

- **Address** = `(display_number << 2) | 3` as two hex chars, left-padded ([issue #1](https://github.com/HiszpanInk/rg-screens-things/issues/1)). The controller addresses 16, 17, 26-29, 40 and 48 this way, so numbers above 31 exist. Address 0 (`03`) is the controller itself; displays reply there.
- **Length** = number of payload bytes. The payload starts with a command: `80` = set text (followed by line, alignment, byte 9, font, x, right edge, scroll, then the text), `00` = status poll.
- Displays **answer**: `80` after each text frame, and `00` + firmware (e.g. `00TLA-2.0a`) to a poll. The server uses this for "Find displays" and to show whether the display actually answers (the header pill says "No reply" if the port is open but the display stays silent).
- The controller never sends a separate clear; it overwrites text windows and periodically resends unchanged static text.
- The display font has a degree sign at byte `0xFF`; typing `°` sends that.
- Byte 9 is `7` here (and `1` in the clear frames, as in the reference script), while the original controller always sends `8`. Its meaning is unknown.

Fonts: 1 small, 2 bold, 3 bold two-line, 4 thin two-line digits, 5 tall two-line digits, 6 bold tall two-line, 7 full height. Text is converted to the display's cp852 charset; typographic quotes, dashes and `…` are replaced with plain look-alikes and anything else unsupported becomes `?`. Text is capped at 243 characters (protocol limit).

## Queue

Messages cycle in order with a configurable duration (`duration_sec`, default 10s). Supports:
- **Random mode**: picks a random visible message instead of sequential (never the same one twice in a row)
- **Scheduling**: per-message time windows (from/to); messages outside their window are skipped
- **Persistence**: saved to `messages.json` on every mutation
- **Hidden messages**: skipped during normal rotation (still playable with "Show now" / skip)
- **Live updates**: editing the message that is on screen repaints it immediately; deleting or hiding it moves on. Dynamic presets (clock, name days, DHT22, days to year end) refresh while shown.
- When nothing is visible (all hidden / outside schedule) the display is blanked.

## Override

A temporary message that replaces the queue ("Show now…" in the web UI). Supports an expiry. Dynamic presets refresh while shown. "Save to queue" copies the current override into the queue.

## Settings

Settings are saved to `settings.json`:

| Field | Default | Description |
|-------|---------|-------------|
| `display_number` | `29` | RS485 display address, as set by the DIP switches (frame address = n×4+3, so 29 → `37 37`) |
| `preset_gap_ms` | `100` | Gap between multi-frame presets (min ~50ms) |
| `keepalive_sec` | `60` | Repaint static content this often (0 = off). Never fires while something scrolls, so animations aren't restarted |
| `queue_running` | `true` | Whether the queue loop is active |
| `random_mode` | `false` | Random message selection |

The old `persistent` message flag never had an effect (every message is saved) and is no longer shown in the UI; it's left untouched in existing files.

## Time

The clock, name-day and schedule logic use the server's clock. A Pi without network time or an RTC boots with a stale clock, so the web UI syncs the time (and time zone) from the browser automatically when they're off by more than a minute or the zone differs. Manual sync is in Settings. The sync lasts until the server restarts.

## Credits

This project would not exist without the protocol analysis and notes shared by [Mitsumi](https://github.com/Mitsumi) and [LirekPL](https://github.com/LirekPL) in the [rg-screens-things](https://github.com/HiszpanInk/rg-screens-things) repository — the definitive resource for understanding R&G display communication. Thanks for the dumps, the docs, and the hardware.
