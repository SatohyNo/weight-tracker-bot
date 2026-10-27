# Weight tracker Telegram bot

A standalone Telegram bot for a body-weight diary: log weights, see weekly averages and pace,
get a chart and calorie advice for bulking, cutting or maintenance.
No AI services involved — just Python 3.10+ and a bot token from @BotFather.

> The bot's interface (buttons and replies) is in Russian.

## Features

- **Logging**: send `82.5` (today) or a list, one entry per line:
  ```
  20.10 83.1
  21.10 82,9
  2026-10-22 - 82.7 кг
  ```
  Dates can be `25.10`, `25.10.2026` or `2026-10-22`. A repeated date overwrites the old entry;
  lines the bot can't parse are reported back.
- **Stats**: latest weight, 7-day average and the previous week's average, last week's pace,
  overall pace (linear trend over all data), total change, min and max.
- **Goal**: bulk (+0.25 kg/week), cut (−0.6 kg/week) or maintain (0).
- **Chart**: every weigh-in, the 7-day average line and a dashed line for the ideal pace of the goal.
  Buttons switch between 30 days, 90 days and all time.
- **Calorie advice**, based on the 3-week trend so a single "water" week doesn't throw it off:
  - cut, weight stalls or drops too slowly → eat less;
  - cut, losing faster than 1 kg/week → eat more;
  - bulk, weight stalls → eat more; gaining too fast → eat less;
  - maintenance, weight drifts → correct it.

  The step assumes 1 kg ≈ 7700 kcal, is rounded to 50 kcal and capped at 300 kcal at a time.
  Set your current intake with `/kcal 2500` and the bot names the new target number.
  Advice appears after 5 weigh-ins over 10+ days.
- **History**: last 20 entries with the change from the previous one, delete the last entry, CSV export.
- **Per-user memory**: every Telegram user has their own data in SQLite (`weights.db`), kept across restarts.

Commands: `/start`, `/help`, `/stats`, `/chart`, `/history`, `/advice`, `/goal`,
`/kcal 2500`, `/del 25.10`, `/export`, `/clear`.

## Running

1. Create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`) and copy the token.
2. Install the dependencies:
   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
3. Give the bot its token (never commit it):
   ```sh
   echo "123456:ABC..." > ~/.weight_bot_token && chmod 600 ~/.weight_bot_token
   # or: export BOT_TOKEN="123456:ABC..."
   ```
4. Start it:
   ```sh
   .venv/bin/python bot.py
   ```

The bot answers only while the script is running, so for 24/7 use run it on a server or VPS
(systemd, `screen`/`tmux`, Docker). Example systemd unit (`/etc/systemd/system/weight-bot.service`):
```ini
[Unit]
Description=Weight tracker Telegram bot
After=network-online.target

[Service]
WorkingDirectory=/opt/weight-bot
Environment=BOT_TOKEN=123456:ABC...
ExecStart=/opt/weight-bot/.venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Settings

| What | Where |
|---|---|
| Time zone for "today" | `BOT_TZ` env variable, default `Europe/Moscow` |
| Database path | `WEIGHT_BOT_DB` env variable, default `weights.db` next to the script |
| Goal paces and tolerances | `GOALS` in `stats.py` |
| Max calorie step, trend window, "too fast" threshold on a cut | `MAX_STEP`, `ADVICE_DAYS`, `CUT_TOO_FAST` in `stats.py` |

## Files

- `bot.py` — Telegram side: menu, buttons, commands
- `stats.py` — input parsing, averages, pace, advice
- `chart.py` — the chart (matplotlib)
- `db.py` — SQLite storage

`weights.db` holds users' data and is excluded from git.
