from __future__ import annotations


def _escape_jql_string(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def build_fix_version_link_jql(project_key: str, fix_version: str) -> str:
    """JQL для поиска Story/Bug одного проекта с заданным fixVersion."""
    pk = (project_key or "").strip().upper()
    fv = _escape_jql_string((fix_version or "").strip())
    if not pk:
        raise ValueError("project_key is required")
    if not fv:
        raise ValueError("fix_version is required")
    return (
        f"project = {pk} "
        "AND issuetype IN (Bug, Story) "
        f'AND fixVersion = "{fv}"'
    )
