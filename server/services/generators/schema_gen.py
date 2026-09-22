"""
SchemaGen — PRD -> {tables, prisma, sql}
Deterministic, no LLM needed unless GEMINI_KEY present for polish.
"""
def to_prisma(tables, entities=None):
    lines = []
    # Build FK map from entities
    fk_map = {}
    if entities:
        for ent in entities:
            for rel in ent.get("relationships", []):
                if rel.get("type") == "belongs_to":
                    fk_map.setdefault(ent["name"], []).append(rel)
    for t in tables:
        model = t["name"].capitalize().replace("_","")
        if model.endswith("s"): model = model[:-1]
        lines.append(f"model {model} {{")
        lines.append(f"  id String @id @default(uuid())")
        for f in t["fields"]:
            fname = "".join(part.capitalize() for part in f["name"].split("_"))
            fname = fname[0].lower() + fname[1:]
            typ = {"text":"String", "integer":"Int", "timestamp":"DateTime", "boolean":"Boolean", "uuid":"String"}[f["type"]]
            if f["type"] == "uuid":
                lines.append(f"  {fname} String @db.Uuid")
            elif f["type"] == "timestamp":
                lines.append(f"  {fname} {typ} @default(now())" if "created" in f["name"] else f"  {fname} {typ}?")
            else:
                lines.append(f"  {fname} {typ}")
        # FK fields from relationships
        for rel in fk_map.get(t["name"], []):
            fk = rel.get("fk", f"{rel['target']}_id")
            fname = "".join(part.capitalize() for part in fk.split("_"))
            fname = fname[0].lower() + fname[1:]
            target_model = rel["target"].capitalize().replace("_","")
            if target_model.endswith("s"): target_model = target_model[:-1]
            lines.append(f"  {fname} String? @db.Uuid")
            lines.append(f"  {target_model.lower()} {target_model}? @relation(fields: [{fname}], references: [id])")
        lines.append(f"  createdAt DateTime @default(now())")
        # indexes
        for rel in fk_map.get(t["name"], []):
            fk = rel.get("fk", f"{rel['target']}_id")
            lines.append(f"  @@index([{fk}])")
        lines.append("}")
        lines.append("")
    return "\n".join(lines).strip()

def to_sql(tables, entities=None):
    stmts = []
    fk_map = {}
    if entities:
        for ent in entities:
            for rel in ent.get("relationships", []):
                if rel.get("type") == "belongs_to":
                    fk_map.setdefault(ent["name"], []).append(rel)
    for t in tables:
        cols = ["id uuid primary key default gen_random_uuid()"]
        # FK columns first
        for rel in fk_map.get(t["name"], []):
            fk_col = rel.get("fk", f"{rel['target']}_id")
            cols.append(f"{fk_col} uuid references {rel['target']}(id)")
        for f in t["fields"]:
            col = f["name"]
            # skip if already FK (FK already added)
            if any(col == rel.get("fk") for rel in fk_map.get(t["name"], [])):
                continue
            typ = {"text":"text", "integer":"integer", "timestamp":"timestamptz", "boolean":"boolean", "uuid":"uuid"}[f["type"]]
            if f["type"] == "timestamp" and "created" in col:
                cols.append(f"{col} {typ} default now()")
            elif f["type"] == "boolean":
                cols.append(f"{col} {typ} default false")
            elif f["type"] == "integer":
                cols.append(f"{col} {typ} default 0")
            else:
                cols.append(f"{col} {typ} not null" if col in ("email","name","title") else f"{col} {typ}")
        cols.append("created_at timestamptz default now()")
        stmts.append(f"create table if not exists {t['name']} (\n  " + ",\n  ".join(cols) + "\n);")
        # indexes on FKs
        for rel in fk_map.get(t["name"], []):
            fk_col = rel.get("fk", f"{rel['target']}_id")
            stmts.append(f"create index if not exists idx_{t['name']}_{fk_col} on {t['name']}({fk_col});")
    return "\n\n".join(stmts)

def _parse_json(text: str):
    import json, re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    return json.loads(text)


def _schema_conforms(data: dict, prd: dict) -> list[str]:
    """LLM schema output must carry every belongs_to FK column in sql+prisma."""
    problems = []
    want_tables = {t["name"].lower() for t in (prd.get("tables") or [])}
    got_tables = {t.get("name", "").lower() for t in (data.get("tables") or [])}
    for w in want_tables:
        if w not in got_tables:
            problems.append(f"table {w} missing from LLM schema")
    sql = (data.get("sql") or "").lower()
    prisma = (data.get("prisma") or "").lower()
    for ent in prd.get("entities") or []:
        for rel in ent.get("relationships", []) or []:
            if rel.get("type") == "belongs_to" and rel.get("target"):
                fk = (rel.get("fk") or f"{rel['target']}_id").lower()
                if fk not in sql:
                    problems.append(f"FK {fk} missing from LLM sql")
                if fk not in prisma:
                    problems.append(f"FK {fk} missing from LLM prisma")
    return problems


def generate_schema(prd: dict):
    import os
    # LLM-first if entities present (skipped under INTARA_TEMPLATE_ONLY for $0 builds/tests)
    if prd.get("entities") and not os.getenv("INTARA_TEMPLATE_ONLY"):
        try:
            from prompts.schema_v2 import build_schema_prompt
            from services.llm import call_llm
            raw = call_llm(build_schema_prompt(prd), temperature=0.2)
            data = _parse_json(raw)
            if data.get("tables") and data.get("sql") and data.get("prisma"):
                problems = _schema_conforms(data, prd)
                if not problems:
                    return data
                print(f"LLM schema failed contract conformance, template fallback: {problems[:4]}")
        except Exception as e:
            print(f"LLM schema gen failed, template fallback: {e}")

    tables = prd.get("tables", [])
    entities = prd.get("entities")
    # sanitize: 1-5 tables, 2-6 fields, types text/integer/timestamp/boolean/uuid
    allowed = {"text","integer","timestamp","boolean","uuid"}
    sane = []
    for t in tables[:5]:
        fields = [f for f in t.get("fields", []) if f.get("type") in allowed][:6]
        if len(fields) < 2:
            while len(fields) < 2:
                fields.append({"name": f"field_{len(fields)+1}", "type": "text"})
        sane.append({"name": t["name"].lower().replace(" ","_"), "fields": fields})
    if not sane:
        sane = [{"name": "items", "fields": [{"name":"title","type":"text"},{"name":"created_at","type":"timestamp"}]}]
    # Pass entities for FK handling if present
    return {
        "tables": sane,
        "prisma": to_prisma(sane, entities),
        "sql": to_sql(sane, entities)
    }
