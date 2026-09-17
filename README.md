# Бот расписания (tg2)

Telegram-бот по расписанию группы **3-Аб-5** СПбГАСУ (числитель/знаменатель).

Собран по образцу бота `tg` (VSTU): то же меню, webhook на Flask, self-ping
и GitHub Actions keep-alive — поэтому на Render не засыпает.

## Возможности

- `/start` — приветствие и текущая неделя (числитель/знаменатель)
- 📅 Расписание — выбор дня недели, вывод пар по звонкам СПбГАСУ
- Суббота/воскресенье — сразу показывается расписание **следующей** недели

## Запуск локально

```bash
pip install -r requirements.txt
BOT_TOKEN=... python bot.py
```

## Обновление расписания

СПбГАСУ публикует расписание по неделям. Когда появляются новые недели:

```bash
python update_schedule.py   # скачает свежий CSV с doc.spbgasu.ru и соберёт schedule.json
```

## Деплой на Render

- Web Service из репозитория `glcskl/tg2`
- Build: `pip install -r requirements.txt`
- Start: `gunicorn web_app:app`
- Env: `BOT_TOKEN`, `RENDER_EXTERNAL_URL` (= https://<имя>.onrender.com), `PYTHON_VERSION=3.11.0`