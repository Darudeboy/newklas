# Migration checklist (manual)

## 0) Подготовка окружения
- [ ] `pip install -r requirements.txt`
- [ ] `.env` содержит минимум:
  - [ ] `JIRA_TOKEN`
  - [ ] `JIRA_URL` (если отличается от дефолта)
  - [ ] при необходимости: `CONFLUENCE_TOKEN`, `CONFLUENCE_URL`, `CONFLUENCE_TEMPLATE_PAGE_ID`, `CONFLUENCE_SPACE_KEY`, `CONFLUENCE_PARENT_PAGE_TITLE`

## 1) Запуск UI
- [ ] `python3 main.py`
- [ ] В левом блоке отображается статус подключения (зелёный/красный).
- [ ] Приложение стартует **без** `langchain`/`langgraph`.

## 2) Проверка гейтов (без действий)
- [ ] Ввести `release_key` → нажать **Проверить**.
- [ ] В “Tech” видно `snapshot` и `result`.
- [ ] В “Assistant” кнопки summary/blockers/next actions работают.

## 3) Guided cycle
- [ ] Нажать **Guided cycle**.
- [ ] “Следующий шаг” повторно запускает оценку с параметрами из контекста.

## 4) Dry-run
- [ ] Включить `Dry-run` и запустить Guided cycle.
- [ ] Нажать “Выполнить переход (если готов)” — переход **не выполняется**.

## 5) Реальный переход (только если ready)
- [ ] Снять `Dry-run`.
- [ ] Если `ready_for_transition=True`, нажать “Выполнить переход (если готов)”.
- [ ] Проверить в Jira, что статус изменился.

## 6) LT / RQG / Tasks+PR
- [ ] **LT** формирует отчёт.
- [ ] **RQG** формирует отчёт.
- [ ] **Tasks+PR** формирует отчёт.

## 7) Логи
- [ ] Во вкладке “Логи” читается `~/.jira_tool/app.log`.

