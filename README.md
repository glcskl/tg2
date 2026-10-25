# tg2 — SPbGASU timetable Telegram bot

A Telegram bot that publishes the timetable of SPbGASU group 3-Ab-5 and keeps it up to date on its own, so students do not have to download the CSV file from the university website every week. The bot parses the official CSV export, rebuilds a weekly template and shows classes ordered by time slot.

The project was built after [tg1](../tg1), which solves the same problem for another university. The menu structure, the webhook layer and the keep-alive mechanism were reused, and CSV import was added.

## Features

- Automatic numerator and denominator detection for the current week
- Timetable rebuilt from the university CSV export, no manual editing
- Classes grouped by day and ordered by time slot
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
broadcast.py        scheduled broadcast sender
keep_alive.py       keep-alive pinger for the free hosting tier
schedule.json       generated timetable data
render.yaml         Render service blueprint
Procfile            process definition for the hosting platform
```

## Deployment

`render.yaml` lets Render provision the web service straight from the blueprint. Four GitHub Actions workflows handle routine maintenance:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `keep-alive.yml` | every 5 minutes | pings the service so the free tier does not sleep |
| `render-deploy.yml` | push to the default branch | redeploys the service so CSV updates reach users quickly |
| `redeploy.yml` | manual | forces a redeploy when the service has been stopped |
| `broadcast.yml` | manual | sends a scheduled broadcast |

## Notes

This project is personal and is not affiliated with the university. The timetable is parsed from a public CSV export, so a change on the university side can break parsing until the parser is updated.