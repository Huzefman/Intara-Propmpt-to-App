"""
Enhanced schema prompt — FKs, indexes, RLS
"""

def build_schema_prompt(app_spec: dict) -> str:
    entities = app_spec.get("entities", [])
    tables = app_spec.get("tables", [])
    # Use entities if available, else tables
    source = entities if entities else [{"name": t["name"], "fields": t["fields"], "relationships": []} for t in tables]

    example = """
Example with FK:
-- recipes
create table if not exists recipes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  author_id uuid references users(id),
  category_id uuid references categories(id),
  created_at timestamptz default now()
);
create index if not exists idx_recipes_author_id on recipes(author_id);
"""

    entities_str = "\n".join([f"- {e['name']}: fields {e.get('fields')} relationships {e.get('relationships')} businessRules {e.get('businessRules')}" for e in source])

    return f"""You are Intara schema weaver — generate SQL + Prisma with FKs, indexes, RLS.

App: {app_spec.get('appName')}
Entities:
{entities_str}

{example}

Return ONLY JSON: {{"tables": [{{"name": "...", "fields": [...]}}], "prisma": "...full prisma schema...", "sql": "...full migration SQL..."}}
Rules:
- Include FK columns (author_id uuid references users(id)) for belongs_to relationships
- Add indexes on FKs and frequently filtered fields
- Generate RLS policies per table (enable RLS, owner can read/write own rows)
- SQL: CREATE TABLE with proper types (text, integer, timestamp, boolean, uuid), FKs, indexes
- Prisma: model with @id, @relation, @@index
- No markdown, JSON only
"""
