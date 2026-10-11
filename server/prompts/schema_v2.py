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

    # Contract: exact FK columns the rest of the pipeline (mock seeds, backend
    # models, SQLite DDL) already assumes. Output is REJECTED without them.
    try:
        from services.contract import table_fks
        fk_lines = []
        for t in tables:
            for fk in table_fks(t["name"], entities):
                fk_lines.append(f"- {t['name']}.{fk['col']} uuid references {fk['ref_table']}(id)")
        fk_block = "\n".join(fk_lines) if fk_lines else "- (no belongs_to relationships)"
    except Exception:
        fk_block = "- (unavailable)"

    return f"""You are Intara schema weaver — generate SQL + Prisma with FKs, indexes, RLS.

App: {app_spec.get('appName')}
Entities:
{entities_str}

{example}

Return ONLY JSON: {{"tables": [{{"name": "...", "fields": [...]}}], "prisma": "...full prisma schema...", "sql": "...full migration SQL..."}}
REQUIRED FK columns (output is rejected if any is missing from BOTH sql and prisma):
{fk_block}
Rules:
- Include FK columns (author_id uuid references users(id)) for belongs_to relationships
- Add indexes on FKs and frequently filtered fields
- Generate RLS policies per table (enable RLS, owner can read/write own rows)
- SQL: CREATE TABLE with proper types (text, integer, timestamp, boolean, uuid), FKs, indexes
- Prisma: model with @id, @relation, @@index
- tables[] must include every input table (same names); fields keep input names verbatim
 - No markdown, JSON only
"""


def build_schema_game_prompt(app_spec: dict) -> str:
    """Scores-only schema for games — no FKs, no RLS owner policies, no indexes
    beyond the PK. Board/turn state is client state, never DDL."""
    tables = app_spec.get("tables") or [{"name": "scores", "fields": [
        {"name": "player", "type": "text"}, {"name": "wins", "type": "integer"},
        {"name": "losses", "type": "integer"}, {"name": "draws", "type": "integer"}]}]
    lines = "\n".join(f"- {t['name']}: fields {t.get('fields')}" for t in tables)
    return f"""You are Intara schema weaver — generate a MINIMAL game schema (SQL + Prisma).

App: {app_spec.get('appName')}
Tables:
{lines}

Return ONLY JSON: {{"tables": [{{"name": "...", "fields": [...]}}], "prisma": "...full prisma schema...", "sql": "...full migration SQL..."}}
Rules:
- One row per player semantics: player text not null; wins/losses/draws integer default 0
- No FK columns, no @@index, no RLS policies (scores are shared/arcade data)
- SQL: CREATE TABLE with proper types (text, integer, timestamp, boolean, uuid)
- Prisma: model with @id
- tables[] must include every input table (same names); fields keep input names verbatim
- No markdown, JSON only
"""
