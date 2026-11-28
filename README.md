# tg2 — SPbGASU timetable Telegram bot

A Telegram bot that publishes the timetable of SPbGASU group 3-Ab-5 and keeps it up to date on its own, so students do not have to download the CSV file from the university website every week. The bot parses the official CSV export, rebuilds a weekly template and shows classes ordered by time slot.

The project was built after [tg1](../tg1), which solves the same problem for another university. The menu structure, the webhook layer and the keep-alive mechanism were reused, and CSV import was added.

## Features

- Automatic numerator and denominator detection for the current week
- Timetable rebuilt from the university CSV export, no manual editing
- Classes grouped by day and ordered by time slot
- Separate buttons for «Экзамены», «Зачёты» and the full session list from the official SPbGASU session page, with dates, time slots, assessment type, teacher and room (group 3-Аб-5 only)
- Separate run modes: long polling for local work, webhook for hosting
- Automatic redeploy on push so a CSV fix reaches the running service quickly
- Keep-alive mechanism for the free hosting tier
- Scheduled broadcasts driven by GitHub Actions

## Tech stack

| Layer | Technology |
| --- | --- |
| Language | Python 3 |
| Framework | aiogram 3 |
| Web layer | Flask |
| WSGI server | Gunicorn |
| Configuration | python-dotenv |
| HTTP client | requests |
| Data source | CSV export from the university website |
| Hosting | Render, free tier |

## Getting started

### Requirements

- Python 3.11 or newer
- A bot token from [@BotFather](https://t.me/BotFather)

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | yes | Token issued by BotFather |
| `BOT_URL` | webhook mode | Public HTTPS URL of the deployed instance |
| `SERVER_URL` | yes | Base URL used by the schedule updater to fetch the CSV |
| `PING_INTERVAL` | no | Keep-alive interval in seconds |
| `RENDER_EXTERNAL_URL` | no | Injected by Render automatically |

Create a `.env` file in the project root:

```
BOT_TOKEN=123456:ABCDEF...
SERVER_URL=https://your-instance.onrender.com
```

### Installation

```bash
git clone https://github.com/glcskl/tg2.git
cd tg2
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running

Refresh the timetable from the university CSV export:

```bash
python update_schedule.py
```

Refresh the exam session list from the university session page:

```bash
python update_session.py
```

Local development with long polling:

```bash
python bot.py
```

Webhook mode, which is what the hosting platform uses:

```bash
python setup_webhook.py
gunicorn web_app:app
```

## Project structure

```
bot.py              long-polling entry point
web_app.py          Flask application serving the Telegram webhook
setup_webhook.py    registers the webhook URL with Telegram
update_schedule.py  parses the university CSV export into schedule.json
update_session.py   parses the university session page into session.json
broadcast.py        scheduled broadcast sender
keep_alive.py       keep-alive pinger for the free hosting tier
health_check.py     pings /health and appends the result to health.log
scripts/wake.sh     manual wake-up with retries for the Render free tier
tests/              pytest suite for the parser, the web app and the health probe
schedule.json       generated timetable data
session.json        generated exam session data
render.yaml         Render service blueprint
Procfile            process definition for the hosting platform
```

## Deployment

`render.yaml` lets Render provision the web service straight from the blueprint. Four GitHub Actions workflows handle routine maintenance:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `keep-alive.yml` | every 5 minutes | pings `/health` with retries so the free tier does not sleep |
| `render-deploy.yml` | manual | configures the Render service and its `BOT_TOKEN` |
| `redeploy.yml` | manual | triggers an immediate Render deploy without waiting in Actions |
| `broadcast.yml` | manual | sends a scheduled broadcast |

Render autodeploys every push to `main`. For manual wake-up (for example right before testing in Telegram):

```bash
./scripts/wake.sh
```

## Tests and health log

`tests/` uses pytest to cover the CSV parser (`build_schedule`), the Flask routes, the week parity logic and the health probe. `tests.yml` runs the suite on every push, and two more workflows track the deployed service:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `tests.yml` | push, pull request | runs `python -m pytest -q` |
| `health.yml` | daily | pings `/health`, adds the status code and latency to `health.log`, commits it and fails the run when the service is down |

```bash
pip install -r requirements.txt pytest
python -m pytest -q
python health_check.py
```

`health.log` is append-only: `<UTC time>\t<HTTP code>\t<latency>\t<up|down>`.

## Notes

This project is personal and is not affiliated with the university. The timetable is parsed from a public CSV export, so a change on the university side can break parsing until the parser is updated.