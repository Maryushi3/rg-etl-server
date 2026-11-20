#!/usr/bin/env python3
"""RS485 link test: compares ways of driving the port against one display.

    python rs485_test.py                    list ports
    python rs485_test.py COM3 [29]          port-setup tests (A, T, U, S)
    python rs485_test.py COM3 [29] --lines  RTS/DTR line tests (A-F)

Each mode sends a status poll and then the text "MODE <letter>" to the display, then
waits a few seconds. Note which letters appear on the display; the printed lines show
whether the display answered the poll in that mode. Stop the server first: it holds the port.
"""
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial not installed: pip install pyserial")

import server
from server import CMD_POLL, address_bytes, build_frame, make_message, parse_frames

BAUD = 9600
HOLD_SEC = 4

# (letter, rts, dtr, direction): direction None = leave RTS alone while sending,
# "high"/"low" = drive RTS to that level only while transmitting (RTS wired to DE).
LINE_MODES = [
    ("A", False, True, None),   # what server.py does
    ("B", True, True, None),
    ("C", False, False, None),
    ("D", True, False, None),
    ("E", False, True, "high"),
    ("F", True, True, "low"),
]


def show_ports():
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if not ports:
        print("no serial ports found")
    for p in ports:
        vidpid = f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else "-"
        print(f"{p.device}  {vidpid}  {p.description}  [{p.hwid}]")


def tx(ser, data, direction=None):
    if direction:
        ser.rts = direction == "high"
    ser.write(data)
    ser.flush()
    if direction:
        time.sleep(len(data) * 10.0 / BAUD + 0.005)  # USB adapters buffer; wait for the last bit on the wire
        ser.rts = direction != "high"


def rx(ser, wait=0.4):
    """Collect whatever arrives within `wait` s without depending on the port timeout."""
    end, buf = time.monotonic() + wait, b""
    while time.monotonic() < end:
        time.sleep(0.02)
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
    return buf


def summarize(buf, sent=b""):
    if buf is None:
        return "nothing"
    if isinstance(buf, str):
        return "reply " + buf
    if not buf:
        return "nothing"
    parts = []
    if sent and buf.startswith(sent):
        parts.append("ECHO of our frame")
    for addr, data in parse_frames(buf):
        if addr == 3:
            parts.append("reply " + data.decode("cp852", "replace"))
    return ", ".join(parts) or f"junk {buf[:40]!r}"


def open_raw(port, **kw):
    try:
        return serial.Serial(port, BAUD, **kw)
    except serial.SerialException as e:
        sys.exit(f"cannot open {port}: {e} (is the server still running?)")


def poll_and_text(ser, number, letter, direction=None, switch_timeout=False):
    poll = bytes.fromhex(build_frame(address_bytes(number), CMD_POLL))
    ser.reset_input_buffer()
    tx(ser, poll, direction)
    if switch_timeout:  # what Display.query() does right after writing the poll
        old = ser.timeout
        ser.timeout = 0.03
        poll_rx = rx(ser)
        ser.timeout = old
    else:
        poll_rx = rx(ser)
    text = bytes.fromhex(make_message(f"MODE {letter}", 1, 0, 1, 0, 96, 0))
    ser.reset_input_buffer()
    tx(ser, text, direction)
    text_rx = rx(ser)
    return f"poll: {summarize(poll_rx, poll)} | text: {summarize(text_rx, text)}"


def run_lines(port, number):
    ser = open_raw(port, timeout=0.03)
    print(f"opened {port}: {ser.get_settings()}\n")
    try:
        for letter, rts, dtr, direction in LINE_MODES:
            ser.rts, ser.dtr = rts, dtr
            time.sleep(0.3)
            res = poll_and_text(ser, number, letter, direction)
            print(f"{letter} rts={int(rts)} dtr={int(dtr)} dir={direction or '-':4} {res}", flush=True)
            time.sleep(HOLD_SEC)
    finally:
        ser.close()


def run_setup(port, number):
    def raw(letter, label, switch_timeout=False, **kw):
        ser = open_raw(port, **kw)
        try:
            ser.rts = False
            time.sleep(0.3)
            print(f"{letter} {label:34} {poll_and_text(ser, number, letter, switch_timeout=switch_timeout)}",
                  flush=True)
        finally:
            ser.close()
        time.sleep(HOLD_SEC)

    raw("A", "raw, timeout=0.03 (control)", timeout=0.03)
    raw("T", "raw, timeout=2 write_timeout=5", timeout=2, write_timeout=5)
    raw("U", "as T + timeout switch after poll", switch_timeout=True, timeout=2, write_timeout=5)

    d = server.Display(port)
    if not d.open():
        sys.exit(f"server Display could not open {port}")
    try:
        reply = d.query(number)
        res = d.send([make_message("MODE S", 1, 0, 1, 0, 96, 0)])
        print(f"S {'server Display.query + send':34} poll: {summarize(reply)} | text: {res[:3]}", flush=True)
    finally:
        d.close()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print(f"python {sys.version.split()[0]}, pyserial {serial.__version__}, platform {sys.platform}")
    show_ports()
    if not args:
        print("\nusage: python rs485_test.py PORT [DISPLAY_NUMBER] [--lines]")
        return
    port = args[0]
    number = int(args[1]) if len(args) > 1 else 29
    print()
    if "--lines" in sys.argv:
        run_lines(port, number)
    else:
        run_setup(port, number)
    print("\ndone: which MODE letters appeared on the display?")


if __name__ == "__main__":
    main()
