"""
SchemaGen — PRD -> {tables, prisma, sql}
Deterministic, no LLM needed unless GEMINI_KEY present for polish.
"""
def to_prisma(tables):
    lines = []
    for t in tables:
        model = t["name"].capitalize().replace("_","")
        # singularize naive
        if model.endswith("s"): model = model[:-1]
        lines.append(f"model {model} {{")
        lines.append(f"  id String @id @default(uuid())")
        for f in t["fields"]:
            fname = "".join(part.capitalize() for part in f["name"].split("_"))
            fname = fname[0].lower() + fname[1:]
            typ = {"text":"String", "integer":"Int", "timestamp":"DateTime", "boolean":"Boolean"}[f["type"]]
            if f["type"] == "timestamp":
                lines.append(f"  {fname} {typ} @default(now())" if "created" in f["name"] else f"  {fname} {typ}?")
            else:
                lines.append(f"  {fname} {typ}")
        lines.append(f"  createdAt DateTime @default(now())")
        lines.append("}")
        lines.append("")
    return "\n".join(lines).strip()

def to_sql(tables):
    stmts = []
    for t in tables:
        cols = ["id uuid primary key default gen_random_uuid()"]
        for f in t["fields"]:
            col = f["name"]
            typ = {"text":"text", "integer":"integer", "timestamp":"timestamptz", "boolean":"boolean"}[f["type"]]
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
    return "\n\n".join(stmts)

def generate_schema(prd: dict):
    tables = prd.get("tables", [])
    # sanitize: ensure 1-3 tables, 2-5 fields, allowed types
    allowed = {"text","integer","timestamp","boolean"}
    sane = []
    for t in tables[:3]:
        fields = [f for f in t.get("fields", []) if f.get("type") in allowed][:5]
        if len(fields) < 2:
            # pad
            while len(fields) < 2:
                fields.append({"name": f"field_{len(fields)+1}", "type": "text"})
        sane.append({"name": t["name"].lower().replace(" ","_"), "fields": fields})
    if not sane:
        sane = [{"name": "items", "fields": [{"name":"title","type":"text"},{"name":"created_at","type":"timestamp"}]}]
    return {
        "tables": sane,
        "prisma": to_prisma(sane),
        "sql": to_sql(sane)
    }
