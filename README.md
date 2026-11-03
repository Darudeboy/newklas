# Blast (newui)

UI для проверки релизных гейтов Jira. Публичная копия: [newklas](https://github.com/Darudeboy/newklas).

## Локальный запуск

```bash
python3 -m venv .venv && source .venv/bin/activate  # опционально
pip install -r requirements.txt
# Создай .env в корне: JIRA_URL, JIRA_TOKEN, при необходимости CONFLUENCE_* и GIGACHAT_*
python3 main.py
```

Макет тёмного UI (без Jira): `python -m ui.preview_dark_ui`

- **Stories** — проверка Story в составе релиза (`consist of` / `is part of`) по правилам из `docs/story_requirements.md`.
- **Release analyze / Deploy plan** — сервисы для деплой-плана берутся из merged PR в ветку `release/<ключ релиза>` (например `release/HRPRELEASE-76202`), а не из master/main. Кнопка Tasks+PR по-прежнему смотрит на master/main.

См. также `docs/RQG.md` (переменные `RQG_PRIMARY`, `RQG_LINK_TYPE`).
