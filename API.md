# API Reference

All endpoints return JSON unless noted. CORS headers are set on all responses (`Access-Control-Allow-Origin: *`).

Errors return a JSON body `{ "error": "..." }` with status `400` (bad JSON / missing `id`), `404` (unknown endpoint or message) or `500`.

Display updates are asynchronous: endpoints that change what's shown (override, skip, next, settings) return immediately and the display loop applies the change within a moment.

## Status & Info

### `GET /api/status`

Current server and display state.

```json
{
  "ok": true,
  "display_connected": true,
  "queue_running": true,
  "queue_position": 2,
  "messages_count": 5,
  "override_active": false,
  "override_message": {},
  "time_synced": true,
  "settings": { ... },
  "dht22_temp": "23.5",
  "dht22_hum": "45",
  "dht22_ok": true,
  "display_port": "/dev/ttyAMA0",
  "display_responding": true,
  "display_firmware": "TLA-2.0a",
  "sensor_port": null,
  "override_expires_at": 0,
  "current": {
    "source": "queue",
    "id": "a1b2c3d4",
    "index": 1,
    "preset_id": "clock",
    "since": 1719000000.0,
    "until": 1719000010.0,
    "parts": [{ "text": "12:34", "font": 3, "line": 0, "align": 0, "x": 2, "w": 34, "scroll": 0 }]
  },
  "held": null,
  "version": 7,
  "server_time": 1719000003.2,
  "utc_offset_min": 120,
  "tz": "Europe/Warsaw"
}
```

- `queue_position`: 1-based position of the message currently shown from the queue.
- `display_connected`: the RS485 port is open. `display_responding`: whether display `display_number` answered the last status poll (polled every 30 s; `null` = not checked yet), `display_firmware` its reported firmware.
- `dht22_ok`: false when the sensor reports an error or hasn't sent a reading for 60 s.
- `current`: what the display is showing (`source` is `queue` or `override`), with the rendered `parts` (text with placeholders filled in). `null` when nothing is shown.
- `held`: `"clear"` or `"test"` after `/api/clear` / `/api/test`, until the next update repaints the display.
- `version`: increments whenever the message list changes (cheap way to know when to refetch `/api/messages`).
- `server_time` / `utc_offset_min` / `tz`: the clock the display uses (after any time sync).

### `GET /api/messages`

Full message queue. Returns `{ "messages": [...], "version": 7 }`.

### `GET /api/settings`

Current settings object.

### `GET /api/override`

Current override state. Returns `{ "active": bool, "message": {...}, "expires_at": number }`.

---

## Messages

### `POST /api/messages`

Create a new message. If no `id` is provided (or it's already taken), a random 8-char ID is generated.

**Body:** message object (see Message Fields below)

**Response:** `201 Created` — the created message object with its `id`.

### `PUT /api/messages?id=<id>`

Update an existing message. The body replaces the message entirely (preserving `id`).

**Query:** `id` (required)

**Response:** the updated message object.

### `DELETE /api/messages?id=<id>`

Delete a message.

**Query:** `id` (required)

**Response:** `{ "ok": true }`

### `POST /api/messages/reorder`

Reorder the message queue. Messages whose IDs are missing from the list are kept, after the listed ones.

**Body:** `{ "ids": ["id1", "id2", ...] }`

**Response:** `{ "ok": true }`

### `GET /api/messages/export`

The whole queue as a download (`messages-YYYY-MM-DD.json`), in the `messages.json` format: `{ "messages": [...] }`.

### `POST /api/messages/import`

Adds messages from a file in the `messages.json` format to the queue, or replaces the queue with them.

**Body:** `{ "messages": [...], "mode": "append" | "replace" }` (`mode` defaults to `append`)

Entries that aren't objects are skipped. A missing, invalid or (when appending) already used `id` gets a new one, so importing the same file twice gives two copies. Errors (400): no `messages` list, an unknown `mode`, or no valid messages in the file.

**Response:** `{ "ok": true, "imported": 5, "skipped": 0, "count": 12 }` (`count` = queue length afterwards)

### `POST /api/skip-to-message?id=<id>`

Jump to a specific message immediately (works for hidden messages and while the queue is paused). Cancels any active override; the queue continues from there.

**Query:** `id` (required)

**Response:** `{ "ok": true, "index": 3 }`

### `POST /api/next`

Advance to the next visible message now (also works while the queue is paused).

**Response:** `{ "ok": true }`

### `POST /api/preview`

Render a message without sending it. Body: a message object, or `{ "message": {...} }`.

**Response:** `{ "parts": [{ "text", "font", "line", "align", "x", "w", "scroll" }, ...], "frames": 2 }`

---

## Override

### `POST /api/override`

Set or update the override message. The override replaces the queue while active.

**Body:**
```json
{
  "active": true,
  "message": { "preset_id": "clock", ... },
  "expires_at": 1719000000
}
```

Instead of `expires_at` (absolute, server clock) you can send `"expires_in": 300` (seconds from now). `0` / missing means no expiry. Sending `"active": false` (or an empty message) ends the override.

**Response:** the updated override object (with the computed `expires_at`).

### `POST /api/cancel-override`

Cancel the active override and resume the queue.

**Response:** `{ "ok": true }`

---

## Display

### `POST /api/clear`

Clear both lines of the display. The display stays blank until the next update (next queue message, or the dynamic content changing).

**Response:** `{ "ok": true }`

### `POST /api/test`

Send a hardcoded test string to the display (body is ignored).

**Response:** `{ "result": "TX: ..." }`

### `POST /api/discover`

Scan the bus for displays: sends a status poll to each address and lists those that answer. Takes about 0.25 s per address (default range 1-63, about 20 s). Needs an RS485 adapter that can also receive.

**Body (optional):** `{ "from": 1, "to": 63 }`

**Response:** `{ "result": "Found: 29 (TLA-2.0a)", "found": [{ "number": 29, "reply": "00TLA-2.0a", "firmware": "TLA-2.0a" }] }` (`409` if a scan is already running)

---

## Time

### `POST /api/time`

Set the clock the server uses for clock/name-day/schedule logic (useful on a Pi without network time). Kept in memory until restart; offsets under 2 s are ignored.

**Body:** `{ "unix_seconds": 1719000000, "tz": "Europe/Warsaw", "tz_offset_min": 120 }` (`tz` and `tz_offset_min` optional; `tz` needs Python 3.9+, otherwise the fixed offset is used)

**Response:** `{ "ok": true }`

---

## System

### `POST /api/poweroff`

Save messages and settings, flush the filesystem, then shut the machine down about 1 s after replying (runs `sudo -n /usr/bin/systemctl poweroff`, so the service user needs passwordless sudo for it). If the command fails, the error is logged to stdout (journald) and the server keeps running.

**Required header:** `X-RG-Confirm: poweroff`. Requests without it get `403`. The header forces a CORS preflight, and the preflight response doesn't allow it, so other web pages can't trigger a shutdown cross-site.

**Response:** `{ "ok": true }`

Wait for the Pi's green LED to stop blinking before unplugging it.

---

## Settings

### `PUT /api/settings`

Update settings. Only provided fields are merged in. Known fields are validated and clamped (`display_number` 0-63, `preset_gap_ms` 10-2000, `keepalive_sec` 0-3600 where 0 disables); invalid values are ignored and reported in an `_errors` list in the response. Unknown fields are stored as-is.

**Body:** (any subset)
```json
{
  "display_number": 29,
  "preset_gap_ms": 100,
  "keepalive_sec": 60,
  "queue_running": true,
  "random_mode": false
}
```

**Response:** the full updated settings object.

---

## Message Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | string | *(auto)* | 8-char unique ID |
| `preset_id` | string | `single-static` | One of the preset names |
| `text` | string | `""` | Main text content |
| `font` | int | `1` | Font (1-7, see README) |
| `line` | int | `0` | Display line (0=top, 1=bottom) |
| `alignment` | int | `0` | 0=left, 1=center, 2=right |
| `pos_x` | int | `0` | Horizontal start position (px, `custom` preset) |
| `width` | int | `96` | Right edge of the text window (px, `custom` preset) |
| `scroll` | int | `0` | Scroll count (0=static, 99=long scroll) |
| `duration_sec` | int | `10` | Seconds to display before next message |
| `persistent` | bool | `true` | Legacy, has no effect (all messages are saved). Kept for compatibility |
| `schedule` | object | `{}` | `{ enabled, from_ts, to_ts }` |
| `hidden` | bool | `false` | Skip in normal queue rotation |

### Preset-specific fields

| Preset | Field | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `two-static` | `_ts_font2` | int | `1` | Bottom line font |
| | `_ts_align2` | int | `0` | Bottom line alignment |
| `bus` | `name` | string | `""` | Route number |
| | `_scroll` | string | `""` | Scrolling route info |
| | `_bus_shift` | int | `0` | Manual X-offset for destination |
| `train` | `name` | string | `""` | Train number |
| | `_train_to` | string | `""` | Destination station |
| | `_train_font_from` | int | `1` | Departure font |
| | `_train_font_to` | int | `1` | Destination font |
| | `_train_align_from` | int | `0` | Departure alignment |
| | `_train_align_to` | int | `2` | Destination alignment |
| | `_train_shift` | int | `0` | Manual X-offset for number |
| `clock` | `_clock_shift` | int | `0` | Manual X-offset for the date/weekday |
| `top-bottom-scroll` | `_tbs_bottom` | string | `""` | Bottom scrolling line |
| | `_tbs_font_top` | int | `1` | Top line font |
| | `_tbs_font_bottom` | int | `1` | Bottom line font |
| | `_tbs_scroll` | int | `99` | Bottom scroll count |
| `imieniny` | `_imieniny_scroll` | int | `99` | Names scroll count |
| `do-konca-roku` | `_dkr_split` | bool | `false` | Bigger "Do końca roku" heading, count on the bottom line |

---

## Web UI

`GET /` or any unmatched path serves `webui.html` — the single-page web interface.
