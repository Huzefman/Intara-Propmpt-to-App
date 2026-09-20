"""
Per-table backend prompt — one table at a time
"""
BACKEND_TABLE_PROMPT = """You are Intara backend weaver — build FastAPI for ONE table, SQLite default + Supabase swap via db.py.

Context:
- App: __APP_NAME__
- Table: __TABLE__ fields: __FIELDS__
- All tables: __ALL_TABLES__
- APIs for this table: __APIS__

Return ONLY JSON with models, routes, openapi for table __TABLE__

Rules:
- Pydantic model with Optional id, field types text->str, integer->int, timestamp->datetime, boolean->bool
- FastAPI routes use get_engine+supabase fallback, no markdown
"""
