# Mapping: legacy `ui.py` → modular `ui/` + `core/*`

Цель: **preserve behavior first**. Все сетевые вызовы и бизнес‑правила остаются в `core/*` и существующих “рабочих” модулях (`rqg.py`, `lt.py`, `release_pr_status.py`, `master_analyzer.py`). UI стал тонким и модульным.

## Entry points
- `newui/main.py` → `from ui import ModernJiraApp` (теперь `ui` — пакет `newui/ui/`)

## UI modules
- `newui/ui/app.py`: `ModernJiraApp`
- `newui/ui/controllers.py`: `AppController` (handlers операций)
- `newui/ui/forms.py`: `MainFormPanel` (форма ввода + кнопки)
- `newui/ui/result_panel.py`: `ResultPanel`
- `newui/ui/chat_panel.py`: `ChatPanel` (assistant stub)
- `newui/ui/tech_panel.py`: `TechPanel` (raw snapshot/result)
- `newui/ui/log_panel.py`: `LogPanel`
- `newui/ui/styles.py`: тема/шрифты

## Operations mapping
- Guided cycle / next step / move-if-ready: `ui/controllers.py` → `core/orchestrator.run_release_check`
- LT: `ui/controllers.py` → `lt.run_lt_check_with_target`
- RQG: `ui/controllers.py` → `rqg.run_rqg_check`
- Tasks+PR: `ui/controllers.py` → `release_pr_status.collect_release_tasks_pr_status`
- Master analyze: `ui/controllers.py` → `master_analyzer.MasterServicesAnalyzer`

## Assistant layer (без внешней сети)
- `core/explain.py`: deterministic explain layer
- `core/assistant.py`: `RuleBasedAssistant` (stub)

