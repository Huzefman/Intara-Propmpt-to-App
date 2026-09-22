"""
Rich per-table backend prompt — includes relationships, validation, auth
"""

def build_backend_table_prompt(table: dict, app_spec: dict) -> str:
    """Builds the LLM prompt for one backend table."""
    # Find entity
    entity = next((e for e in app_spec.get("entities", []) if e["name"] == table["name"]), table)
    relationships = entity.get("relationships", [])
    business_rules = entity.get("businessRules", [])
    apis = [a for a in app_spec.get("apis", []) if table["name"] in a["path"]]
    auth_required = any(a.get("auth") for a in apis) if apis else app_spec.get("auth", False)

    example = """
Example (tasks table):
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
class Task(BaseModel):
    id: Optional[str] = None
    title: str
    due_date: Optional[datetime] = None
    completed: bool = False
    user_id: Optional[str] = None
    @field_validator('title')
    def title_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('title is required')
        return v

@app.get("/api/tasks")
def list_tasks():
    if supabase:
        return supabase.table("tasks").select("*").execute().data or []
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text("select * from tasks")).mappings().all()]
"""

    try:
        from services.contract import table_routes, table_fks
        _matrix = table_routes(table["name"])
        matrix_block = "Required routes (ALL six, {id} form — output is rejected if any is missing):\n" + "\n".join(
            f"- {r['method']} {r['path']}" for r in _matrix)
        _fks = table_fks(table["name"], app_spec.get("entities"))
        fk_block = ("FK columns (model + SQL, both): " + ", ".join(
            f"{fk['col']} Optional[str] references {fk['ref_table']}(id)" for fk in _fks)) if _fks else "No FKs for this table."
    except Exception:
        matrix_block = ("Required routes: GET /api/__TABLE_NAME__ (list), POST, GET /api/__TABLE_NAME__/{id}, "
                        "PUT /api/__TABLE_NAME__/{id}, PATCH /api/__TABLE_NAME__/{id}, DELETE /api/__TABLE_NAME__/{id}")
        fk_block = "Include belongs_to FK columns in model and SQL."

    prompt = """You are Intara backend weaver — build FastAPI for ONE table, SQLite default + Supabase swap via db.py.

App: __APP_NAME__
Entity: __ENTITY__ fields: __FIELDS__ relationships: __RELS__ businessRules: __RULES__
APIs for this table: __APIS__
Auth required: __AUTH__
All entities: __ALL_ENTITIES__

__MATRIX_BLOCK__
__FK_BLOCK__

Layout (mandatory — deviation is rejected):
- Put routes INLINE in server/main.py (one file serves all tables); NEVER emit server/routers/ stubs
- Import as `from server.db import get_engine, init_db, supabase`, run from backend/ via `uvicorn server.main:app`
- ids are strings (uuid hex); create assigns one when missing; read-after-write happens AFTER commit
- openapi paths use {id}, never :id

__EXAMPLE__

Return ONLY JSON with files (server/main.py, server/models.py) and openapi for table __TABLE_NAME__
Rules:
- Pydantic model with Optional id + Optional FK cols, field validators from businessRules
- FastAPI routes use get_engine+supabase fallback, proper HTTP codes (404 on missing id, 400 on empty update)
- Full-file content for every file; no stubs: no `return []`, no SELECT 1, no TODO, no bare `...`
- No markdown, JSON only
"""
    prompt = prompt.replace("__APP_NAME__", str(app_spec.get('appName'))).replace("__ENTITY__", str(entity['name'])).replace("__FIELDS__", str(entity.get('fields'))).replace("__RELS__", str(relationships)).replace("__RULES__", str(business_rules)).replace("__APIS__", str(apis)).replace("__AUTH__", str(auth_required)).replace("__ALL_ENTITIES__", str(app_spec.get('entities'))).replace("__EXAMPLE__", example).replace("__TABLE_NAME__", table['name']).replace("__MATRIX_BLOCK__", matrix_block).replace("__FK_BLOCK__", fk_block)
    return prompt
