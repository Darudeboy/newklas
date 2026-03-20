# Blast (newui)

UI для проверки релизных гейтов Jira. Публичная копия: [newklas](https://github.com/Darudeboy/newklas).

## Локальный запуск

```bash
python3 -m venv .venv && source .venv/bin/activate  # опционально
pip install -r requirements.txt
# Создай .env в корне: JIRA_URL, JIRA_TOKEN, при необходимости CONFLUENCE_* и GIGACHAT_*
python3 main.py
```

См. также `docs/RQG.md` (переменные `RQG_PRIMARY`, `RQG_LINK_TYPE`).
