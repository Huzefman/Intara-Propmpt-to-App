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

    prompt = """You are Intara backend weaver — build FastAPI for ONE table, SQLite default + Supabase swap via db.py.

App: __APP_NAME__
Entity: __ENTITY__ fields: __FIELDS__ relationships: __RELS__ businessRules: __RULES__
APIs for this table: __APIS__
Auth required: __AUTH__
All entities: __ALL_ENTITIES__

__EXAMPLE__

Return ONLY JSON with files and openapi for table __TABLE_NAME__
Rules:
- Pydantic model with Optional id, field validators from businessRules
- FastAPI routes use get_engine+supabase fallback, proper HTTP codes
- Include GET /api/__TABLE_NAME__ (list), GET /api/__TABLE_NAME__/:id, POST, PATCH /:id, DELETE /:id
- No markdown, JSON only
"""
    prompt = prompt.replace("__APP_NAME__", str(app_spec.get('appName'))).replace("__ENTITY__", str(entity['name'])).replace("__FIELDS__", str(entity.get('fields'))).replace("__RELS__", str(relationships)).replace("__RULES__", str(business_rules)).replace("__APIS__", str(apis)).replace("__AUTH__", str(auth_required)).replace("__ALL_ENTITIES__", str(app_spec.get('entities'))).replace("__EXAMPLE__", example).replace("__TABLE_NAME__", table['name'])
    return prompt
