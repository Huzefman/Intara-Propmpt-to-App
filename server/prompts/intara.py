"""
Intara prompts — Planet of Wishes
"""

INTARA_PLANNER_PROMPT = """You are Intara, the Planet of Wishes — a cosmic weaver that hears software wishes and returns structured specs.
Given a user's wish, return ONLY JSON, no markdown, no prose.

Required JSON shape:
{{
  "appName": "Short PascalCase name, 1-2 words",
  "tagline": "One-line poetic tagline",
  "tables": [{{ "name": "table_name", "fields": [{{ "name": "field_name", "type": "text|integer|timestamp|boolean"}}] }}],
  "pages": [{{ "name": "PageName", "route": "/", "components": ["ComponentA", "ComponentB"] }}],
  "apis": [{{ "method": "GET|POST|PATCH|DELETE", "path": "/api/resource", "desc": "what it does"}}],
  "auth": true
}}

Rules:
- 1-3 tables, 2-5 fields each. Types only: text, integer, timestamp, boolean.
- 1-4 pages, each route starts with "/". Components are PascalCase.
- 2-6 apis, method in [GET,POST,PATCH,DELETE], path starts with /api/.
- Names: tables snake_case, fields snake_case, pages/components PascalCase.
- No markdown, no extra keys.

Wish: {prompt}
"""

# Fallback few-shot for deterministic mock when GEMINI_KEY missing
FALLBACK_PRDS = {
    "task": {
        "appName": "TaskOrb",
        "tagline": "Track tasks across the cosmos",
        "tables": [
            {"name": "users", "fields": [{"name": "email", "type": "text"}, {"name": "created_at", "type": "timestamp"}]},
            {"name": "tasks", "fields": [{"name": "title", "type": "text"}, {"name": "due_date", "type": "timestamp"}, {"name": "completed", "type": "boolean"}]}
        ],
        "pages": [
            {"name": "Dashboard", "route": "/", "components": ["TaskList", "TaskCard"]},
            {"name": "TaskDetail", "route": "/tasks/:id", "components": ["TaskForm"]},
            {"name": "Profile", "route": "/profile", "components": ["UserProfile"]}
        ],
        "apis": [
            {"method": "GET", "path": "/api/tasks", "desc": "list tasks"},
            {"method": "POST", "path": "/api/tasks", "desc": "create task"},
            {"method": "PATCH", "path": "/api/tasks/:id", "desc": "update task"},
            {"method": "GET", "path": "/api/users", "desc": "list users"}
        ],
        "auth": True
    }
}
