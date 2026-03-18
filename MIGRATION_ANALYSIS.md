# Анализ и маппинг: automatic-main 2 → newui

## 1. Краткий анализ текущего состояния

### Входные точки
- **main.py** — единственный вход: создаёт `ModernJiraApp()` из `ui`, запускает `mainloop()`. CLI как отдельного entrypoint нет (всё через GUI).
- **ui.py** (~3200 строк) — основной слой: CustomTkinter, JiraService, вызовы release_flow, LT, RQG, PR status, переходы по workflow, история, опционально AI-агент и master_analyzer.

### Зависимости main → ui
- `ui.ModernJiraApp` — единственная зависимость.

### Модули, используемые из ui.py
| Модуль | Назначение |
|--------|------------|
| config | JiraConfig, Confluence env, TEAM_NAME, validate_config |
| service | JiraService (все вызовы Jira) |
| history | OperationHistory (история операций в память + файл) |
| lt | run_lt_check_with_target (проверка LT метрики) |
| rqg | run_rqg_check (RQG по qgm + analyze_rqg_for_release) |
| release_pr_status | collect_release_tasks_pr_status, format_release_tasks_pr_report |
| release_flow | evaluate_release_gates, format_release_gate_report |
| release_flow_config | get_release_flow_profile |
| arch | JIRA_TOKEN (для master_analyzer), ArchitectureFieldFixer не вызывается из ui |
| onboarding | show_onboarding_if_needed (stub) |
| master_analyzer | MasterServicesAnalyzer, ConfluenceDeployPlanGenerator (файл не в списке — опционально) |

### Где что находится

| Область | Файл(ы) | Функции/классы |
|--------|---------|-----------------|
| **Jira API** | service.py | JiraService: get_issue_details, get_linked_issues, get_available_transitions, transition_issue, transition_issue_by_id, get_issue_comments, get_issue_remote_links, get_field_name_map, get_sber_test_report, get_qgm_status, get_dev_status_prs, get_issue_id, search_issues, create_issue_link, delete_issue_link, collect_release_related_issues |
| **Confluence** | bt3.py | JiraConfluenceSync (Confluence + Jira для страницы БТ/FR); config.py — CONFLUENCE_* |
| **Сбор данных по релизу** | release_flow.py (внутри evaluate_release_gates) | Получение release, linked issues, sber_test_report, field_name_map, qgm; release_pr_status — PR по задачам; rqg — RQG по Story |
| **Проверки (гейты)** | release_flow.py | _has_distribution_link, _is_distribution_registered, _is_ift_recommended, _evaluate_story, _evaluate_bug, _evaluate_manual_subtasks, _extract_rqg_comment_signals, логика rqg_gate, dist_gate, recommendation_gate, nt_gate, dt_gate, story_quality, bug_quality |
| **Профиль workflow** | release_flow_config.py | get_release_flow_profile, load_release_flow_profiles, resolve_profile_name |
| **Решение и переход** | release_flow.py | _next_transition, _resolve_transition_id, ready_for_transition; ui.py и агент вызывают transition_issue / transition_issue_by_id |
| **Вопросы / UI** | ui.py | Поля ввода, кнопки (Guided cycle, следующий шаг, подтверждение ручных чеков), отображение отчёта format_release_gate_report |
| **LT** | lt.py | JiraTaskAnalyzer (собственные requests), run_lt_check_with_target, format_analysis_report |
| **RQG** | rqg.py | analyze_rqg_for_release, trigger_rqg_button, run_rqg_check (используют jira_service) |
| **PR status** | release_pr_status.py | collect_release_tasks_pr_status, format_release_tasks_pr_report |

---

## 2. Mapping: старый файл/функция → новый файл/функция

| Старый файл | Старая функция/класс | Новый файл | Новое имя/примечание |
|-------------|----------------------|------------|----------------------|
| config.py | JiraConfig | core/jira_client.py или core/config.py | JiraConfig можно оставить в config.py в корне или перенести в core |
| service.py | JiraService | core/jira_client.py | JiraClient (alias JiraService для совместимости) |
| config.py | CONFLUENCE_*, validate_config | config.py (корень) + core/confluence_client.py | Confluence env в config; ConfluenceClient — тонкая обёртка |
| bt3.py | JiraConfluenceSync (Confluence часть) | core/confluence_client.py | ConfluenceClient: get_page, update_page, create_page (минимальный интерфейс или TODO) |
| release_flow.py | Сбор: get_issue_details, get_linked_issues, sber_test_report, field_name_map, qgm, comments | core/snapshot_builder.py | build_release_snapshot(jira_client, release_key) → ReleaseSnapshot |
| release_flow.py | _norm, _value_to_text, _has_meaningful_value, _extract_issue_*, _find_*, _flatten_*, _get_linked_issue_keys | core/rules.py (helpers) + core/snapshot_builder.py (при необходимости) | В rules — чистые функции над snapshot/issue |
| release_flow.py | _has_distribution_link, _is_distribution_registered, _is_ift_recommended, _is_recommendation_*, _evaluate_story, _evaluate_bug, _evaluate_manual_subtasks, _distribution_from_related_issues, _extract_rqg_comment_signals, _next_transition, _resolve_transition_id, _is_qgm_technical_error | core/rules.py | evaluate_gates(snapshot, profile) → список гейтов + next_status, next_transition_id, ready_for_transition |
| release_flow.py | evaluate_release_gates | core/orchestrator.py | run_release_check(release_key, profile_name, manual_confirmations, jira_client) → тот же dict |
| release_flow.py | format_release_gate_report | core/orchestrator.py или core/rules.py | format_release_gate_report(result) — оставить сигнатуру |
| release_flow_config.py | get_release_flow_profile, load_release_flow_profiles, resolve_profile_name | core/release_flow_config.py или внутри core/orchestrator | get_release_flow_profile(project_key, requested_profile) |
| — | — | core/types.py | ReleaseSnapshot, RuleResult, ReleaseDecision, RecommendationState, SubtaskState, BugState (и при необходимости PsiState) |
| ui.py | Обработчики кнопок Guided cycle, следующий шаг, подтверждение, переход | ui.py | Тонкий слой: ввод → orchestrator.run_release_check / run_release_action → отображение |
| main.py | main() | main.py | Тонкий: запуск UI (или в будущем CLI) |

Дополнительно:
- **release_pr_status**, **rqg**, **lt**: пока остаются отдельными модулями в корне (или копируются в newui и вызываются из orchestrator/ui). Не разбивать на core без необходимости.
- **history**, **onboarding**: остаются в корне newui (history.py, onboarding.py).
- **arch**, **bt3**: в newui не переносим в первый заход (или bt3 → core/confluence_client минимально).

---

## 3. План миграции (5–10 шагов)

1. **Создать core/types.py** — dataclass-модели для snapshot и результата проверок (ReleaseSnapshot, RuleResult, ReleaseDecision и т.д.).
2. **Создать core/jira_client.py** — перенести JiraService из service.py, сохранить интерфейс (можно alias JiraService = JiraClient).
3. **Создать core/confluence_client.py** — минимальный модуль: заглушка или тонкая обёртка над Confluence (из bt3 при необходимости).
4. **Создать core/release_flow_config.py** — скопировать release_flow_config.py в core без изменений логики.
5. **Создать core/snapshot_builder.py** — вынести сбор данных: вызовы jira (release, linked, sber_test, field_name_map, qgm, comments), формирование структуры для правил (ReleaseSnapshot или сырой dict для совместимости).
6. **Создать core/rules.py** — перенести чистые проверки из release_flow.py (все _has_*, _is_*, _evaluate_*), работающие на snapshot/issue + profile; выход — список гейтов, next_status, next_transition_id, ready_for_transition.
7. **Создать core/orchestrator.py** — run_release_check (snapshot_builder + rules + учёт manual_confirmations, возврат того же dict что evaluate_release_gates), run_release_action (transition по id/имени); format_release_gate_report вызывать или реэкспортировать.
8. **Обновить main.py** — оставить только запуск UI (и при необходимости CLI), без бизнес-логики.
9. **Обновить ui.py** — заменить прямые вызовы evaluate_release_gates и transition на orchestrator.run_release_check и orchestrator.run_release_action; оставить отображение и ввод в ui.
10. **Скопировать config.py, history.py, onboarding.py, release_pr_status.py, rqg.py, lt.py** в newui и поправить импорты (из core.* где нужно).

---

## 4. Checklist ручной проверки после миграции

- [ ] Запуск приложения: `python main.py` — открывается окно CustomTkinter.
- [ ] Подключение к Jira: настройка URL/токен, проверка соединения (если есть кнопка).
- [ ] Guided cycle: ввод ключа релиза, запуск проверки гейтов — отчёт совпадает с текущим (те же гейты, те же сообщения).
- [ ] Подтверждение ручного чека: confirm_manual_check для release_key и check_id — гейты пересчитываются, переход разблокируется при необходимости.
- [ ] Переход по workflow: "перевести на следующий этап" / move_release_if_ready — релиз переводится в следующий статус, отчёт обновляется.
- [ ] Проверка LT: вызов run_lt_check_with_target из UI — отчёт по LT без ошибок.
- [ ] Проверка RQG: вызов run_rqg_check из UI — отчёт RQG без ошибок.
- [ ] Отчёт по задачам и PR: collect_release_tasks_pr_status, вывод в UI — без ошибок.
- [ ] История операций: добавление и сохранение в файл после действий — без ошибок.
- [ ] Dry-run: при dry_run=True переход не выполняется в Jira, сообщение о готовности к переходу отображается.

---

## 5. Расположение и запуск

- Структура создана в **рабочей директории проекта** `agent/newui/` (путь `~/Python/newui` на Mac при необходимости создайте вручную и скопируйте туда содержимое `newui/` или клонируйте репозиторий в этот путь).
- Зависимости: `pip install -r requirements.txt` (atlassian-python-api, requests, python-dotenv, customtkinter).
- Запуск: из каталога `newui` выполнить `python main.py`.
- Переменные окружения: `.env` с `JIRA_URL`, `JIRA_TOKEN` и при необходимости `RELEASE_FLOW_*`, `CONFLUENCE_*` по аналогии со старым проектом.
