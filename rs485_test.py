#!/usr/bin/env python3
"""RS485 link test: tries RTS/DTR line settings and direction modes against one display.

    python rs485_test.py              list ports
    python rs485_test.py COM3 [29]    run the test on COM3 against display 29 (default)

Each mode sends a status poll and then the text "MODE <letter>" to the display, then
waits a few seconds. Note which letters appear on the display; the printed lines show
whether the display answered the poll in that mode.
"""
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial not installed: pip install pyserial")

from server import CMD_POLL, address_bytes, build_frame, make_message, parse_frames

BAUD = 9600
HOLD_SEC = 4

# (letter, rts, dtr, direction): direction None = leave RTS alone while sending,
# "high"/"low" = drive RTS to that level only while transmitting (RTS wired to DE).
MODES = [
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


def tx(ser, data, direction):
    if direction:
        ser.rts = direction == "high"
    ser.write(data)
    ser.flush()
    if direction:
        time.sleep(len(data) * 10.0 / BAUD + 0.005)  # USB adapters buffer; wait for the last bit on the wire
        ser.rts = direction != "high"


def rx(ser, wait=0.4):
    end, buf = time.monotonic() + wait, b""
    while time.monotonic() < end:
        buf += ser.read(max(1, ser.in_waiting))
    return buf


def summarize(buf, sent):
    if not buf:
        return "nothing"
    frames = parse_frames(buf)
    parts = []
    if buf.startswith(sent):
        parts.append("ECHO of our frame")
    for addr, data in frames:
        if addr == 3:
            parts.append("reply " + data.decode("cp852", "replace"))
    return ", ".join(parts) or f"junk {buf[:40]!r}"


def main():
    print(f"python {sys.version.split()[0]}, pyserial {serial.__version__}, platform {sys.platform}")
    show_ports()
    if len(sys.argv) < 2:
        print("\nusage: python rs485_test.py PORT [DISPLAY_NUMBER]")
        return
    port = sys.argv[1]
    number = int(sys.argv[2]) if len(sys.argv) > 2 else 29
    try:
        ser = serial.Serial(port, BAUD, bytesize=8, parity="N", stopbits=1, timeout=0.03,
                            xonxoff=False, rtscts=False, dsrdtr=False)
    except serial.SerialException as e:
        sys.exit(f"cannot open {port}: {e} (is the server still running?)")
    print(f"\nopened {port}: {ser.get_settings()}")
    poll = bytes.fromhex(build_frame(address_bytes(number), CMD_POLL))
    try:
        for letter, rts, dtr, direction in MODES:
            ser.rts, ser.dtr = rts, dtr
            time.sleep(0.3)
            ser.reset_input_buffer()
            tx(ser, poll, direction)
            poll_rx = rx(ser)
            text = bytes.fromhex(make_message(f"MODE {letter}", 1, 0, 1, 0, 96, 0))
            ser.reset_input_buffer()
            tx(ser, text, direction)
            text_rx = rx(ser)
            print(f"{letter} rts={int(rts)} dtr={int(dtr)} dir={direction or '-':4}"
                  f" poll: {summarize(poll_rx, poll)} | text: {summarize(text_rx, text)}", flush=True)
            time.sleep(HOLD_SEC)
    finally:
        ser.close()
    print("\ndone: which MODE letters appeared on the display?")


if __name__ == "__main__":
    main()
