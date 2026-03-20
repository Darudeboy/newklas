# RQG: паритет с кнопкой Jira

## Два источника данных

| Режим | Описание |
|--------|-----------|
| **comalarest** (по умолчанию) | Как UI Jira: JQL `issue in linkedIssues("REL", "...")` и для каждой задачи `GET /rest/comalarest/1.0/requirements/rqgstatus`. |
| **qgm** | `POST/GET /rest/release/1/qgm` с числовым `issueId` (старое поведение). |

## Переменные окружения

| Переменная | Значение | По умолчанию |
|------------|-----------|----------------|
| `RQG_PRIMARY` | `comalarest` или `qgm` | `comalarest` |
| `RQG_LINK_TYPE` | Имя типа связи для `linkedIssues` | `consists of` |
| `RQG_LINKED_MAX` | Лимит задач в JQL-поиске | `5000` |

Если `comalarest` недоступен (403), нет связей по JQL или все вызовы `rqgstatus` вернули ошибку, автоматически используется **qgm**.

## Прочие RQG_* 

Эвристический анализ в [rqg.py](../rqg.py) (ЦО/ИФТ/дистрибутив по связям) настраивается через `RQG_CO_KEYWORDS`, `RQG_IFT_KEYWORDS` и т.д. — это **дополнение** к официальному API, а не замена.
