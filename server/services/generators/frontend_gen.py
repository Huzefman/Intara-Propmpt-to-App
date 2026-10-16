"""
FrontendGen v2 — distinct functional pages with LLM-first + template fallback
"""
import re as _re

from utils.json_parse import parse_json as _parse_json, is_quota_error


def page_ident(name: str) -> str:
    """Page/component identifier safe for filenames, imports and JSX.

    'Daily Attendance' -> 'DailyAttendance'. Display labels and routes keep
    the raw name; only code positions use this (R: spaced identifiers crash
    bundlers — the exact HR-tool preview outage).
    """
    parts = _re.split(r"[^0-9A-Za-z]+", str(name or ""))
    ident = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if ident and ident[0].isdigit():
        ident = "Page" + ident
    return ident or "Page"


def normalize_frag(frag: dict) -> dict:
    """Rewrite an LLM (or template) frag's page paths to slugged identifiers
    plus its default-export name, so mixed trees always bundle."""
    for f in (frag.get("files") or []):
        path = f.get("path") or ""
        m = _re.match(r"^(src/pages/)(.+)\.tsx$", path)
        if not m:
            continue
        slug = page_ident(m.group(2))
        if slug == m.group(2):
            continue
        f["path"] = f"{m.group(1)}{slug}.tsx"
        content = f.get("content") or ""
        content = _re.sub(r"export\s+default\s+function\s+[A-Za-z][\w ]*\b",
                          f"export default function {slug}", content, count=1)
        f["content"] = content
    return frag


CSV_LIB_TS = """export function toCsv(rows: any[]): string {
  if (!rows.length) return "";
  const cols: string[] = Array.from(new Set(rows.flatMap((r: any) => Object.keys(r || {}))));
  const esc = (v: any) => {
    const s = v == null ? "" : String(v);
    return /[",\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return [cols.join(","), ...rows.map((r: any) => cols.map((c) => esc(r[c])).join(","))].join("\\n");
}

export function downloadCsv(filename: string, rows: any[]) {
  const blob = new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
"""

CSV_IMPORT_LINE = "import { downloadCsv } from '../lib/csv'\n"

CSV_BUTTON_SNIPPET = """<button onClick={() => downloadCsv("__TABLE__.csv", filtered)} className="btn-ghost" style={{ fontSize: 11 }}>Export CSV</button>"""


UPLOAD_LIB_TS = """// Attachments: Supabase Storage when the host sets window.__INTARA_ENV__
// ({ SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_BUCKET }), otherwise local-only
// Data URLs persisted per record id. Sandpack-safe: no import.meta.
function env(): { url: string; key: string; bucket: string } {
  const w = window as any;
  const e = (w && w.__INTARA_ENV__) || {};
  return {
    url: e.SUPABASE_URL || "",
    key: e.SUPABASE_ANON_KEY || "",
    bucket: e.SUPABASE_BUCKET || "__BUCKET__",
  };
}

async function supabaseUpload(file: File): Promise<string | null> {
  try {
    const { url, key, bucket } = env();
    if (!url || !key) return null;
    const { createClient } = await import("@supabase/supabase-js");
    const sb = createClient(url, key);
    const safe = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
    const path = Date.now() + "-" + safe;
    const up = await sb.storage.from(bucket).upload(path, file);
    if (up.error) return null;
    const pub = sb.storage.from(bucket).getPublicUrl(path);
    return (pub.data && pub.data.publicUrl) || null;
  } catch {
    return null;
  }
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => reject(new Error("read failed"));
    r.readAsDataURL(file);
  });
}

export async function uploadAttachment(file: File): Promise<string> {
  const remote = await supabaseUpload(file);
  if (remote) return remote;
  return readAsDataUrl(file);
}

export function loadLocalAttachments(recordId: string): string[] {
  try {
    const raw = localStorage.getItem("intara-attachments-" + recordId);
    const parsed = JSON.parse(raw || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    const empty: string[] = [];
    return empty;
  }
}

export function saveLocalAttachments(recordId: string, urls: string[]) {
  try {
    localStorage.setItem("intara-attachments-" + recordId, JSON.stringify(urls));
  } catch {}
}
"""

UPLOAD_IMPORT_LINE = "import { uploadAttachment, loadLocalAttachments, saveLocalAttachments } from '../lib/upload'\n"

UPLOAD_STATE_SNIPPET = """  const [uploadUrls, setUploadUrls] = useState<string[]>([])
  useEffect(() => { if (id) setUploadUrls(loadLocalAttachments(String(id))) }, [id])
"""

UPLOAD_SECTION_SNIPPET = """<div className="glass" style={{ padding: 14, marginTop: 16 }}>
  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>Attachments</div>
  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
    <label className="btn-ghost" style={{ fontSize: 11, cursor: 'pointer', padding: '8px 12px' }}>Choose file
      <input type="file" style={{ display: 'none' }} onChange={async (e:any) => {
        const f = e.target.files && e.target.files[0];
        if (!f || !id) return;
        const url = await uploadAttachment(f);
        const next = [...uploadUrls, url];
        setUploadUrls(next);
        saveLocalAttachments(String(id), next);
      }} />
    </label>
    <span style={{ fontSize: 11, color: 'var(--intara-dim)' }}>{uploadUrls.length ? uploadUrls.length + ' attached' : 'images or documents'}</span>
  </div>
  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
    {uploadUrls.map((u:string, i:number) => (
      u.startsWith('data:image/') || /\\.(png|jpe?g|gif|webp|svg)(\\?|$)/i.test(u)
        ? <img key={i} src={u} alt={'attachment ' + (i+1)} style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)' }} />
        : <a key={i} href={u} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: 'var(--intara-nebula-light)' }}>file {i+1}</a>
    ))}
  </div>
</div>"""


def _upload_target_tables(prd: dict):
    """Tables whose detail pages get Attachments. None = feature off;
    '*' = all detail pages; otherwise a set of table names from unit configs."""
    comp = (prd.get("_components") or {})
    units = [u for u in comp.get("units", []) if u.get("component") == "file-upload"]
    if not units:
        return None
    tables = set()
    for u in units:
        ent = (u.get("config") or {}).get("entity")
        if not ent:
            return "*"
        tables.add(ent)
    return tables or "*"


def _upload_bucket_name(prd: dict) -> str:
    comp = (prd.get("_components") or {})
    for u in comp.get("units", []):
        if u.get("component") == "file-upload":
            bucket = (u.get("config") or {}).get("bucket")
            if bucket:
                return str(bucket)
    return "uploads"


def _csv_export_tables(prd: dict):
    """Tables whose list pages get CSV export. None = feature off;
    '*' = all list pages; otherwise a set of table names from unit configs."""
    comp = (prd.get("_components") or {})
    units = [u for u in comp.get("units", []) if u.get("component") == "csv-export"]
    if not units:
        return None
    tables = set()
    for u in units:
        ent = (u.get("config") or {}).get("entity")
        if not ent:
            return "*"
        tables.add(ent)
    return tables or "*"


def generate_frontend_page_llm(page: dict, app_spec: dict, notes: list | None = None) -> dict | None:
    """Try LLM generation for one page. Returns {path, content} (crud) or
    {files: [...]} (game: page + src/game/logic.ts), or None on failure.
    Failure reasons are appended to notes (when given) for fallback_reason."""
    def _note(msg: str):
        try:
            if notes is not None:
                notes.append(msg[:200])
        except Exception:
            pass

    try:
        from services.validator import validate_tsx

        is_game = str(app_spec.get("appKind") or "").lower() in ("interactive", "game")
        if is_game:
            from prompts.frontend_page_v2 import build_frontend_game_prompt
            from services.llm import call_llm
            prompt = build_frontend_game_prompt(page, app_spec)
            raw = call_llm(prompt, temperature=0.3, json_mode=True)
            data = _parse_json(raw)
            files = data.get("files", [])
            if not files:
                return None
            page_file = next((f for f in files if (f.get("path") or "").startswith("src/pages/")), None)
            logic_file = next((f for f in files if (f.get("path") or "") in ("src/game/logic.ts", "src/game/logic.js", "src/game/engine.ts")), None)
            if not page_file or not page_file.get("content"):
                _note("game response missing page file")
                return None
            if validate_tsx(page_file["content"], page_file.get("path", "")):
                _note("game page failed validation")
                return None
            out = [page_file]
            if logic_file and logic_file.get("content"):
                import re as _re
                if not _re.search(r"^\s*import\s", logic_file["content"], _re.M):
                    out.append(logic_file)
            return {"files": out}

        from prompts.frontend_page_v2 import build_frontend_page_prompt
        from services.llm import call_llm

        prompt = build_frontend_page_prompt(page, app_spec)
        raw = call_llm(prompt, temperature=0.3, json_mode=True)
        data = _parse_json(raw)
        content = data.get("content", "")
        if not content:
            _note("empty content in LLM response")
            return None
        errors = validate_tsx(content, data.get("path", f"src/pages/{page['name']}.tsx"))
        if errors:
            repair_prompt = f"Fix these TypeScript errors in the component:\n{errors}\n\nOriginal code:\n{content}"
            try:
                raw2 = call_llm(repair_prompt, temperature=0.1, json_mode=True)
                data2 = _parse_json(raw2)
                content2 = data2.get("content", content)
                if not validate_tsx(content2, data2.get("path", data.get("path", f"src/pages/{page['name']}.tsx"))):
                    content = content2
                else:
                    _note(f"validation failed after repair: {errors[0][:120]}")
                    return None
            except Exception as e:
                _note(f"repair failed: {e}"[:200])
                return None
        return {"path": data.get("path", f"src/pages/{page['name']}.tsx"), "content": content}
    except Exception as e:
        print(f"LLM frontend page {page.get('name')} failed: {e}")
        try:
            if notes is not None:
                notes.append(str(e)[:200])
        except Exception:
            pass
        return None


# --- deterministic game templates (phase 3: $0 path for interactive appKinds) ---
# src/game/logic.ts is byte-compatible with the gate harness canonical API
# (calcWinner/isDraw/legalMoves/applyMove/bestMove — gates execute it standalone).

GAME_LOGIC_TS = """export type Cell = "X" | "O" | null;

export function calcWinner(b: Cell[]): "X" | "O" | null {
  const lines = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  for (const line of lines) {
    const a = line[0], c = line[1], d = line[2];
    if (b[a] && b[a] === b[c] && b[a] === b[d]) return b[a];
  }
  return null;
}

export function isDraw(b: Cell[]): boolean {
  return b.every((v) => v !== null) && calcWinner(b) === null;
}

export function legalMoves(b: Cell[]): number[] {
  const out: number[] = [];
  b.forEach((v, i) => { if (v === null) out.push(i); });
  return out;
}

export function applyMove(b: Cell[], i: number, p: "X" | "O"): Cell[] {
  if (b[i] !== null) throw new Error("occupied cell " + i);
  const nb = b.slice();
  nb[i] = p;
  return nb;
}

function minimax(b: Cell[], turn: "X" | "O", me: "X" | "O", depth: number): number {
  const w = calcWinner(b);
  if (w === me) return 10 - depth;
  if (w) return depth - 10;
  if (isDraw(b)) return 0;
  const moves = legalMoves(b);
  let best = turn === me ? -Infinity : Infinity;
  for (const m of moves) {
    const nb = b.slice();
    nb[m] = turn;
    const s = minimax(nb, turn === "X" ? "O" : "X", me, depth + 1);
    best = turn === me ? Math.max(best, s) : Math.min(best, s);
  }
  return best;
}

export function bestMove(b: Cell[], me: "X" | "O"): number {
  let bi = -1;
  let bs = -Infinity;
  for (const m of legalMoves(b)) {
    const nb = b.slice();
    nb[m] = me;
    const s = minimax(nb, me === "X" ? "O" : "X", me, 0);
    if (s > bs) { bs = s; bi = m; }
  }
  return bi;
}
"""

GAME_BOARD_PAGE = """import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { calcWinner, isDraw, applyMove, bestMove, legalMoves } from '../game/logic'
import type { Cell } from '../game/logic'

type Mode = '2P' | 'AI'

export default function __PAGE__() {
  const [board, setBoard] = useState<Cell[]>(Array(9).fill(null))
  const [turn, setTurn] = useState<"X" | "O">("X")
  const [mode, setMode] = useState<Mode>("2P")
  const [scores, setScores] = useState<any[]>([])
  const winner = calcWinner(board)
  const draw = !winner && isDraw(board)

  const loadScores = () => {
    import('../api').then((m) => (m.listScores ? m.listScores() : [])).then((d: any) => setScores(Array.isArray(d) ? d : [])).catch(() => {})
  }
  useEffect(() => { loadScores() }, [])

  const persist = (w: "X" | "O" | "draw") => {
    try {
      const key = "intara-scores";
      const local = JSON.parse(localStorage.getItem(key) || "{}");
      local[w] = (local[w] || 0) + 1;
      localStorage.setItem(key, JSON.stringify(local));
    } catch {}
    import('../api').then((m) => {
      if (!m.createScores) return;
      m.createScores({ player: w === "draw" ? "draws" : w, wins: w === "X" ? 1 : 0, losses: w === "O" ? 1 : 0, draws: w === "draw" ? 1 : 0 }).catch(() => {});
    }).catch(() => {});
    loadScores();
  }

  const done = (nb: Cell[]) => {
    const w = calcWinner(nb);
    if (w || isDraw(nb)) persist(w || "draw");
  }

  const play = (i: number) => {
    if (winner || draw || board[i] !== null) return;
    let nb: Cell[];
    try { nb = applyMove(board, i, turn); } catch { return; }
    if (mode === "2P") {
      setBoard(nb); setTurn(turn === "X" ? "O" : "X"); done(nb);
      return;
    }
    // vs AI: human is X, AI answers as O
    setBoard(nb); done(nb);
    if (calcWinner(nb) || isDraw(nb)) return;
    const reply = bestMove(nb, "O");
    if (reply >= 0) {
      try {
        const nb2 = applyMove(nb, reply, "O");
        setBoard(nb2); done(nb2);
        return;
      } catch {}
    }
    setBoard(nb);
  }

  const reset = () => { setBoard(Array(9).fill(null)); setTurn("X"); };

  const status = winner ? ("Winner: " + winner) : draw ? "Draw — rematch?" : ("Turn: " + turn + (mode === "AI" && turn === "O" ? " (thinking…)" : ""));

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
        <div>
          <h2 style={{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em' }}>__APP__</h2>
          <p style={{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}>{status}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setMode(mode === "2P" ? "AI" : "2P")} className="btn-ghost" style={{ fontSize: 11 }}>{mode === "2P" ? "vs AI" : "2 players"}</button>
          <button onClick={reset} className="btn-ghost" style={{ fontSize: 11 }}>Rematch</button>
        </div>
      </div>
      <div className="glass" style={{ padding: 16, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, maxWidth: 420 }}>
        {board.map((cell, i) => (
          <button key={i} onClick={() => play(i)} aria-label={"cell " + i} style={{ aspectRatio: '1', fontSize: 32, fontWeight: 600, fontFamily: 'Space Grotesk', borderRadius: 14, border: '1px solid rgba(255,255,255,0.06)', background: cell ? 'rgba(139,92,246,0.12)' : 'rgba(255,255,255,0.03)', color: cell === "X" ? 'var(--intara-nebula-light)' : '#FBBF24', cursor: 'pointer' }}>{cell || ""}</button>
        ))}
      </div>
      <div className="glass" style={{ padding: 14, marginTop: 12, maxWidth: 420 }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>Scoreboard</div>
        {scores.length ? scores.slice(0, 6).map((s: any) => (
          <div key={s.id || s.player} style={{ display: 'flex', gap: 8, fontSize: 12, padding: '4px 0' }}>
            <span style={{ fontWeight: 600 }}>{s.player}</span>
            <span style={{ color: 'var(--intara-faint)' }}>{s.wins || 0}W · {s.losses || 0}L · {s.draws || 0}D</span>
          </div>
        )) : <div style={{ fontSize: 11, color: 'var(--intara-faint)' }}>No scores yet — finish a game.</div>}
        <Link to="/scores" style={{ fontSize: 11, color: 'var(--intara-nebula-light)', textDecoration: 'none' }}>All scores →</Link>
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--intara-dim)' }}>Moves left: {legalMoves(board).length}</div>
    </div>
  )
}
"""

GAME_SCORES_PAGE = """import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

export default function __PAGE__() {
  const [scores, setScores] = useState<any[]>([])
  useEffect(() => {
    import('../api').then((m) => (m.listScores ? m.listScores() : [])).then((d: any) => setScores(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])
  return (
    <div>
      <Link to="/" style={{ fontSize: 12, color: 'var(--intara-faint)', textDecoration: 'none' }}>← Back to game</Link>
      <h2 style={{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 600, marginTop: 8 }}>Scores</h2>
      <div style={{ display: 'grid', gap: 10, marginTop: 16 }}>
        {scores.length ? scores.map((s: any) => (
          <div key={s.id || s.player} className="glass" style={{ padding: 14, display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{s.player}</span>
            <span style={{ fontSize: 12, color: 'var(--intara-faint)' }}>{s.wins || 0}W · {s.losses || 0}L · {s.draws || 0}D</span>
          </div>
        )) : (
          <div className="glass" style={{ padding: 32, textAlign: 'center', color: 'var(--intara-faint)' }}>No scores yet — play your first game.</div>
        )}
      </div>
    </div>
  )
}
"""


def _game_template_files(page: dict, app_name: str) -> list[dict]:
    """Deterministic page set for game feature pages (template fallback)."""
    feature = str(page.get("feature") or "").lower()
    name = page.get("name", "Game")
    out = [{"path": "src/game/logic.ts", "content": GAME_LOGIC_TS}]
    if feature == "scores" or "score" in name.lower():
        out.append({"path": f"src/pages/{page_ident(name)}.tsx",
                    "content": GAME_SCORES_PAGE.replace("__PAGE__", page_ident(name))})
    else:
        out.append({"path": f"src/pages/{page_ident(name)}.tsx",
                    "content": GAME_BOARD_PAGE.replace("__PAGE__", page_ident(name)).replace("__APP__", app_name)})
    return out


def generate_frontend(prd: dict):
    from services.contract import build_contract as _bc, client_fns as _cf
    tables = prd.get("tables", [])
    pages = prd.get("pages", [])
    app_name = prd.get("appName", "IntaraApp")
    _contract = _bc(prd)
    files = []
    # api.ts — canonical client from the contract: full CRUD per table, {id} interpolated.
    # Pages must use these fns (never raw fetch) so client/server/mock cannot drift.
    api_lines = [
        "// Intara Frontend — API client (mock vs real) — Sandpack safe",
        "// Canonical: one fn per contract route. Pages import these; do not raw-fetch /api.",
        "const MODE = 'mock'",
        "const API_URL = ''",
        "function baseFetch(path: string, init?: RequestInit) {",
        "  const url = MODE === 'mock' ? path : `${API_URL}${path}`",
        "  return fetch(url, init)",
        "}",
        "const _json = { 'Content-Type': 'application/json' }",
    ]
    from services.contract import ROUTE_FN_KEYS
    if _contract.get("appKind") in ("interactive", "game"):
        # Minimal client: exactly one fn per declared contract route (no CRUD bulk).
        for r in _contract.get("routes", []):
            key = ROUTE_FN_KEYS.get(r.get("method", ""))
            if not key:
                continue
            for t in _contract["tables"]:
                if t.get("name") != r.get("table"):
                    continue
                fn = _cf(t["name"])[key]
                base = f"/api/{t['name']}"
                if key == "list":
                    api_lines.append(f"export const {fn} = () => baseFetch('{base}').then(r => r.json())")
                elif key == "create":
                    api_lines.append(f"export const {fn} = (body:any) => baseFetch('{base}', {{method:'POST', headers:_json, body: JSON.stringify(body)}}).then(r => r.json())")
                elif key == "get":
                    api_lines.append(f"export const {fn} = (id:string) => baseFetch(`{base}/${{id}}`).then(r => r.json())")
                elif key in ("put", "patch"):
                    api_lines.append(f"export const {fn} = (id:string, body:any) => baseFetch(`{base}/${{id}}`, {{method:'{key.upper()}', headers:_json, body: JSON.stringify(body)}}).then(r => r.json())")
                elif key == "delete":
                    api_lines.append(f"export const {fn} = (id:string) => baseFetch(`{base}/${{id}}`, {{method:'DELETE'}}).then(r => r.json())")
    else:
        for t in _contract["tables"]:
            fns = _cf(t["name"])
            base = f"/api/{t['name']}"
            api_lines.append(f"export const {fns['list']} = () => baseFetch('{base}').then(r => r.json())")
            api_lines.append(f"export const {fns['create']} = (body:any) => baseFetch('{base}', {{method:'POST', headers:_json, body: JSON.stringify(body)}}).then(r => r.json())")
            api_lines.append(f"export const {fns['get']} = (id:string) => baseFetch(`{base}/${{id}}`).then(r => r.json())")
            api_lines.append(f"export const {fns['put']} = (id:string, body:any) => baseFetch(`{base}/${{id}}`, {{method:'PUT', headers:_json, body: JSON.stringify(body)}}).then(r => r.json())")
            api_lines.append(f"export const {fns['patch']} = (id:string, body:any) => baseFetch(`{base}/${{id}}`, {{method:'PATCH', headers:_json, body: JSON.stringify(body)}}).then(r => r.json())")
            api_lines.append(f"export const {fns['delete']} = (id:string) => baseFetch(`{base}/${{id}}`, {{method:'DELETE'}}).then(r => r.json())")
    api_lines.append("// Preview mock auto-installed via src/mock/server.ts when VITE_API_MODE=mock")
    files.append({"path": "src/api.ts", "content": "\n".join(api_lines)})

    types = ["// Intara — Types"]
    for t in tables:
        fname = t["name"].capitalize().replace("_","")
        if fname.endswith("s"): fname = fname[:-1]
        types.append(f"export type {fname} = {{ id: string; " + "; ".join(f"{f['name']}: { {'text':'string','integer':'number','timestamp':'string','boolean':'boolean','uuid':'string'}[f['type']]}" for f in t["fields"]) + " }")
    files.append({"path": "src/types.ts", "content": "\n".join(types)})

    # helper to guess table
    used_tables = set()
    def guess_table(page, idx):
        candidates = [page["name"].lower()] + [c.lower() for c in page.get("components", [])]
        for t in tables:
            if t["name"] in used_tables: continue
            tname = t["name"].lower()
            t_sing = tname[:-1] if tname.endswith("s") else tname
            for cand in candidates:
                if tname in cand or t_sing in cand or cand in tname:
                    used_tables.add(t["name"])
                    return t["name"]
        for t in tables:
            tname = t["name"].lower()
            t_sing = tname[:-1] if tname.endswith("s") else tname
            for cand in candidates:
                if tname in cand or t_sing in cand or cand in tname:
                    return t["name"]
        for t in tables:
            if t["name"] not in used_tables:
                used_tables.add(t["name"])
                return t["name"]
        return tables[idx % len(tables)]["name"] if tables else "items"

    if not pages:
        pages = [{"name":"Dashboard","route":"/","components":["ItemList"]}]

    import os as _os
    _template_only = bool(_os.getenv("INTARA_TEMPLATE_ONLY"))
    _csv_tables = _csv_export_tables(prd)
    _csv_emitted = False
    _upload_tables = _upload_target_tables(prd)
    _upload_emitted = False
    _upload_bucket = _upload_bucket_name(prd)
    _fallbacks: list = []
    for idx, p in enumerate(pages[:6]):
        # LLM-first: try one LLM call per page (skipped under INTARA_TEMPLATE_ONLY).
        # Game pages may return {files:[page, logic]} — extend instead of append.
        _notes: list = []
        llm_result = None if _template_only else generate_frontend_page_llm(p, prd, _notes)
        if llm_result:
            if isinstance(llm_result.get("files"), list):
                seen_here = {f["path"] for f in files}
                files.extend([f for f in llm_result["files"] if f.get("path") not in seen_here])
            else:
                files.append(llm_result)
            # still need to mark table as used for guessing
            guess_table(p, idx)
            continue
        if _notes:
            _fallbacks.append({"page": p.get("name"), "reason": _notes[-1]})
        elif _template_only:
            _fallbacks.append({"page": p.get("name"), "reason": "template_only_mode"})
        # Template fallback: game feature pages render the deterministic board,
        # crud pages use the extracted list/detail templates below.
        if str(prd.get("appKind") or "").lower() in ("interactive", "game"):
            for gf in _game_template_files(p, app_name):
                if gf["path"] not in {f["path"] for f in files}:
                    files.append(gf)
            continue
        comp_imports = ", ".join(p.get("components", [])[:2])
        table_guess = guess_table(p, idx)
        # Explicit plan binding wins over guessing (kills Analytics→wrong-table drift)
        bound = p.get("table")
        if isinstance(bound, str) and any(t["name"] == bound for t in tables):
            used_tables.add(bound)
            table_guess = bound
        tfields = next((t["fields"] for t in tables if t["name"] == table_guess), tables[0]["fields"] if tables else [{"name":"title","type":"text"}])
        fns = _cf(table_guess)
        # Determine page type by route and name (RR uses :id, specs may say {id})
        is_detail = ":id" in p["route"] or "{id}" in p["route"]
        is_dashboard = p["route"] == "/" or "dashboard" in p["name"].lower()

        # Build inputs with proper types
        inputs = []
        for f in tfields[:4]:
            fname = f["name"]
            ftype = f["type"]
            if ftype == "boolean":
                inputs.append(f'        <label style={{{{ display:"flex", alignItems:"center", gap:6, fontSize:12 }}}}><input type="checkbox" checked={{!!form.{fname}}} onChange={{e=>setForm((s:any)=>({{...s, {fname}: e.target.checked}}))}} /> {fname}</label>')
            elif ftype == "integer":
                inputs.append(f'        <input type="number" placeholder="{fname}" value={{form.{fname} || ""}} onChange={{e=>setForm((s:any)=>({{...s, {fname}: Number(e.target.value)}}))}} style={{{{ flex:1, minWidth:120, padding:"10px 12px", borderRadius:10, border:"1px solid rgba(255,255,255,0.06)", background:"rgba(255,255,255,0.03)", color:"var(--intara-text)" }}}} />')
            elif ftype == "timestamp":
                inputs.append(f'        <input type="date" value={{form.{fname} ? String(form.{fname}).slice(0,10) : ""}} onChange={{e=>setForm((s:any)=>({{...s, {fname}: e.target.value}}))}} style={{{{ flex:1, minWidth:120, padding:"10px 12px", borderRadius:10, border:"1px solid rgba(255,255,255,0.06)", background:"rgba(255,255,255,0.03)", color:"var(--intara-text)" }}}} />')
            else:
                inputs.append(f'        <input placeholder="{fname}" value={{form.{fname} || ""}} onChange={{e=>setForm((s:any)=>({{...s, {fname}: e.target.value}}))}} style={{{{ flex:1, minWidth:120, padding:"10px 12px", borderRadius:10, border:"1px solid rgba(255,255,255,0.06)", background:"rgba(255,255,255,0.03)", color:"var(--intara-text)" }}}} />')
        form_inputs = "\n".join(inputs)

        # Determine page template
        if is_detail:
            # Detail page: fetch single item by ID from URL, show edit / delete
            page_content = f"""import {{ useState, useEffect }} from 'react'
import {{ useParams, Link }} from 'react-router-dom'
__UPLOAD_IMPORT__import {{ {fns['get']}, {fns['patch']}, {fns['delete']}, {fns['list']} }} from '../api'

export default function {page_ident(p["name"])}() {{
  const {{ id }} = useParams()
  const [item, setItem] = useState<any>(null)
  const [form, setForm] = useState<any>({{}})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
__UPLOAD_STATE__

  const load = async () => {{
    setLoading(true)
    try {{
      const data = await {fns['get']}(String(id))
      if (data && !data.error) {{
        setItem(data)
        setForm(data)
      }} else {{
        // fallback to list and find
        const list = await {fns['list']}()
        const found = Array.isArray(list) ? list.find((x:any)=>String(x.id)===String(id)) : null
        if (found) {{ setItem(found); setForm(found) }}
      }}
    }} catch {{}}
    setLoading(false)
  }}
  useEffect(() => {{ if(id) load() }}, [id])

  const save = async () => {{
    setSaving(true)
    await {fns['patch']}(String(id), form)
    setSaving(false)
    load()
  }}
  const remove = async () => {{
    if (!confirm('Delete this {table_guess}?')) return
    await {fns['delete']}(String(id))
    window.location.href = '/'
  }}

  if (loading) return <div className="glass" style={{{{ padding: 24, textAlign: 'center' }}}}>Loading {table_guess}…</div>
  if (!item) return <div className="glass" style={{{{ padding: 24, textAlign: 'center' }}}}>Not found <Link to="/">Back to {p["name"]}</Link></div>

  return (
    <div style={{{{ maxWidth: 640, margin: '0 auto' }}}}>
      <Link to="/" style={{{{ fontSize: 12, color: 'var(--intara-faint)', textDecoration: 'none' }}}}>← Back</Link>
      <h2 style={{{{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 600, marginTop: 8 }}}}>{p["name"]} — {app_name}</h2>
      <p style={{{{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}}}>Editing {table_guess} #{{id}} • {", ".join([f['name'] for f in tfields[:3]])}</p>
      
      <div className="glass" style={{{{ padding: 16, marginTop: 16, display: 'grid', gap: 12 }}}}>
{form_inputs}
        <div style={{{{ display: 'flex', gap: 8, marginTop: 8 }}}}>
          <button onClick={{save}} disabled={{saving}} className="btn-primary" style={{{{ flex: 1 }}}}>{{saving ? 'Saving…' : 'Save changes'}}</button>
          <button onClick={{remove}} className="btn-ghost" style={{{{ color: '#F87171', borderColor: 'rgba(248,113,113,0.2)' }}}}>Delete</button>
        </div>
      </div>

      <div className="glass" style={{{{ padding: 14, marginTop: 16 }}}}>
        <div style={{{{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}}}>Current data</div>
        <pre className="code-block" style={{{{ background: 'transparent', border: 'none', padding: 0 }}}}>{{JSON.stringify(item, null, 2)}}</pre>
      </div>
__UPLOAD_SECTION__
    </div>
  )
}}
"""
        else:
            # List/Dashboard page with search, stats, and cards
            # Build field displays based on types
            field_displays = []
            for f in tfields[:4]:
                fname = f["name"]
                if f["type"] == "boolean":
                    field_displays.append(f'<span style={{{{ padding:"3px 8px", borderRadius:999, fontSize:11, background: item.{fname} ? "rgba(16,185,129,0.12)" : "rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.06)", color: item.{fname} ? "#10B981" : "var(--intara-faint)"}}}}>{{item.{fname} ? "✓ " : ""}}{fname}</span>')
                elif f["type"] == "timestamp":
                    field_displays.append(f'<span style={{{{ fontSize:11, color:"var(--intara-faint)" }}}}>{{item.{fname} ? new Date(item.{fname}).toLocaleDateString() : ""}}</span>')
                elif f["type"] == "integer":
                    field_displays.append(f'<span style={{{{ fontSize:11, fontWeight:600, color:"var(--intara-nebula-light)"}}}}>{{item.{fname} ?? 0}}</span>')
                else:
                    # for title/name/email fields, show prominently
                    if fname in ["title","name","email"]:
                        continue
                    field_displays.append(f'<span style={{{{ fontSize:11, color:"var(--intara-faint)"}}}}>{{item.{fname} || ""}}</span>')
            # title field display
            title_field = next((f["name"] for f in tfields if f["name"] in ["title","name","email"]), tfields[0]["name"])
            field_displays_str = " ".join(field_displays)

            # Stats for dashboard
            stats_section = ""
            if is_dashboard:
                stats_section = f"""
      <div style={{{{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}}}>
        <div className="glass" style={{{{ padding: 14, textAlign: 'center' }}}}>
          <div style={{{{ fontSize: 20, fontWeight: 600 }}}}>{{items.length}}</div>
          <div style={{{{ fontSize: 11, color: 'var(--intara-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}}}>Total {table_guess}</div>
        </div>
        <div className="glass" style={{{{ padding: 14, textAlign: 'center' }}}}>
          <div style={{{{ fontSize: 20, fontWeight: 600, color: 'var(--intara-nebula-light)' }}}}>{{items.filter((x:any)=>x.completed || x.published || x.status==='active').length}}</div>
          <div style={{{{ fontSize: 11, color: 'var(--intara-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}}}>Active</div>
        </div>
        <div className="glass" style={{{{ padding: 14, textAlign: 'center' }}}}>
          <div style={{{{ fontSize: 20, fontWeight: 600 }}}}>{{new Set(items.map((x:any)=>x.title||x.name)).size}}</div>
          <div style={{{{ fontSize: 11, color: 'var(--intara-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}}}>Unique</div>
        </div>
      </div>"""

            detail_bits = " · ".join(f"{fn}: {{item.{fn}}}" for fn in [f["name"] for f in tfields[1:2]])
            req_field = next((f["name"] for f in tfields if f["type"] == "text"), tfields[0]["name"] if tfields else "title")
            page_content = f"""import {{ useState, useEffect, useMemo }} from 'react'
import {{ Link }} from 'react-router-dom'
__CSV_IMPORT__import {{ {fns['list']}, {fns['create']}, {fns['patch']} }} from '../api'

export default function {page_ident(p["name"])}() {{
  const [items, setItems] = useState<any[]>([])
  const [form, setForm] = useState<any>({{}})
  const [q, setQ] = useState("")
  const [filter, setFilter] = useState("all")

  const load = () => {fns['list']}().then(d => setItems(Array.isArray(d) ? d : [])).catch(()=>{{}})
  useEffect(() => {{ load() }}, [])

  const create = async () => {{
    if (!form.{req_field}?.trim?.()) return
    await {fns['create']}(form)
    setForm({{}}); load()
  }}

  const toggle = async (id:any, field:string, value:any) => {{
    await {fns['patch']}(id, {{ [field]: value }})
    load()
  }}

  const filtered = useMemo(() => {{
    let out = items
    if (q) out = out.filter(x => Object.values(x).join(' ').toLowerCase().includes(q.toLowerCase()))
    if (filter === 'active') out = out.filter(x => x.completed || x.published === true || x.status === 'active')
    if (filter === 'done') out = out.filter(x => x.completed === true)
    return out
  }}, [items, q, filter])

  return (
    <div>
      <div style={{{{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}}}>
        <div>
          <h2 style={{{{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em' }}}}>{p["name"]} — {app_name}</h2>
          <p style={{{{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}}}>Manage {table_guess} • {", ".join([f['name'] for f in tfields[:4]])}</p>
        </div>
        <Link to="{p["route"]}" style={{{{ fontSize: 11, padding: '6px 10px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.06)', textDecoration: 'none', color: 'var(--intara-faint)' }}}}>{p["route"]}</Link>
      </div>
{stats_section}
      <div className="glass" style={{{{ padding: 14, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}}}>
        <input placeholder="Search {table_guess}…" value={{q}} onChange={{e=>setQ(e.target.value)}} style={{{{ flex: 1, minWidth: 160, padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)' }}}} />
        <select value={{filter}} onChange={{e=>setFilter(e.target.value)}} style={{{{ padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)', fontSize: 12 }}}}>
          <option value="all">All</option>
          <option value="active">Active</option>
          <option value="done">Done</option>
        </select>
__CSV_BUTTON__
      </div>

      <div className="glass" style={{{{ padding: 14, marginTop: 12, display: 'grid', gap: 10 }}}}>
        <div style={{{{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 2 }}}}>Create new {table_guess[:-1] if table_guess.endswith('s') else table_guess}</div>
        <div style={{{{ display:'flex', gap:8, flexWrap:'wrap' }}}}>
{form_inputs}
          <button onClick={{create}} className="btn-primary" style={{{{ whiteSpace: 'nowrap' }}}} >Add {table_guess[:-1] if table_guess.endswith('s') else table_guess}</button>
        </div>
      </div>

      <div style={{{{ display: 'grid', gap: 10, marginTop: 16 }}}}>
        {{filtered.length ? filtered.map((item:any) => (
          <div key={{item.id}} className="glass" style={{{{ padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}}}>
            <div style={{{{ flex: 1, minWidth: 0 }}}}>
              <div style={{{{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}}}>
                <Link to={{`/{table_guess}/${{item.id}}`}} style={{{{ fontWeight: 600, fontSize: 13, color: 'var(--intara-text)', textDecoration: 'none' }}}}>{{item.{title_field} || item.name || item.email || 'Untitled'}}</Link>
                {field_displays_str}
              </div>
              <div style={{{{ fontSize: 11, color: 'var(--intara-dim)', marginTop: 4 }}}}>{{item.id ? `#${{String(item.id).slice(0,8)}}` : ''}} {detail_bits}</div>
            </div>
            <div style={{{{ display: 'flex', gap: 6, alignItems: 'center' }}}}>
              {{item.completed !== undefined && (
                <button onClick={{()=>toggle(item.id, 'completed', !item.completed)}} style={{{{ padding: '6px 10px', borderRadius: 999, fontSize: 11, border: '1px solid rgba(255,255,255,0.06)', background: item.completed ? 'rgba(16,185,129,0.12)' : 'transparent', color: item.completed ? '#10B981' : 'var(--intara-faint)'}}}}>{{item.completed ? 'Done' : 'Todo'}}</button>
              )}}
              <Link to={{`/{table_guess}/${{item.id}}`}} className="btn-ghost" style={{{{ padding: '6px 10px', fontSize: 11, textDecoration: 'none' }}}}>View</Link>
            </div>
          </div>
        )) : (
          <div className="glass" style={{{{ padding: 32, textAlign: 'center', color: 'var(--intara-faint)' }}}}>
            <div style={{{{ fontSize: 13, fontWeight: 500 }}}}>No {table_guess} yet</div>
            <div style={{{{ fontSize: 11, marginTop: 4 }}}}>Create your first {table_guess[:-1] if table_guess.endswith('s') else table_guess} above — it saves instantly to IndexedDB</div>
          </div>
        )}}
      </div>
    </div>
  )
}}
"""
        page_content = page_content.replace("__NAME__", p["name"]).replace("__TABLE__", table_guess).replace("__APP__", app_name).replace("__ROUTE__", p["route"]).replace("__COMPS__", comp_imports).replace("__INPUTS__", form_inputs)
        csv_on = _csv_tables == "*" or (isinstance(_csv_tables, set) and table_guess in _csv_tables)
        if csv_on:
            page_content = page_content.replace("__CSV_IMPORT__", CSV_IMPORT_LINE).replace(
                "__CSV_BUTTON__", CSV_BUTTON_SNIPPET.replace("__TABLE__", table_guess))
            _csv_emitted = True
        else:
            page_content = page_content.replace("__CSV_IMPORT__", "").replace("__CSV_BUTTON__", "")
        upload_on = is_detail and (_upload_tables == "*" or (isinstance(_upload_tables, set) and table_guess in _upload_tables))
        if upload_on:
            page_content = page_content.replace("__UPLOAD_IMPORT__", UPLOAD_IMPORT_LINE).replace(
                "__UPLOAD_STATE__", UPLOAD_STATE_SNIPPET).replace("__UPLOAD_SECTION__", UPLOAD_SECTION_SNIPPET)
            _upload_emitted = True
        else:
            page_content = page_content.replace("__UPLOAD_IMPORT__", "").replace(
                "__UPLOAD_STATE__", "").replace("__UPLOAD_SECTION__", "")
        files.append({"path": f"src/pages/{page_ident(p['name'])}.tsx", "content": page_content})

    # components for each table - more functional
    for t in tables[:3]:
        cname = t["name"].capitalize().replace("_","")
        if cname.endswith("s"): cname = cname[:-1]
        cname = cname + "Card"
        # Build a proper card that shows all fields nicely, not just JSON
        field_rows = "\n".join([f'      <div style={{{{ fontSize: 11 }}}}><span style={{{{ color: "var(--intara-faint)" }}}}>{f["name"]}:</span> <span style={{{{ color: "var(--intara-text)", fontWeight: 500 }}}}>{{String(item.{f["name"]} ?? "")}}</span></div>' for f in t["fields"][:4]])
        files.append({"path": f"src/components/{cname}.tsx", "content": f"""export function {cname}({{ item, onSelect }}: {{ item: any, onSelect?: (id:any)=>void }}) {{
  return (
    <div className="glass" style={{{{ padding: 14, cursor: onSelect ? 'pointer' : 'default' }}}} onClick={{()=> onSelect?.(item.id)}}>
      <div style={{{{ fontWeight: 600, fontSize: 13 }}}}>{{item.title || item.name || item.email || '{t['name']}'}} </div>
      <div style={{{{ display: 'grid', gap: 4, marginTop: 8 }}}}>
{field_rows}
      </div>
    </div>
  )
}}
""" })

    # App.tsx starter — premium minimal with nav, Sandpack safe
    routes_str = "\n".join(f'        <Route path="{p["route"]}" element={{<{page_ident(p["name"])} />}} />' for p in pages[:4])
    imports_str = ", ".join(page_ident(p["name"]) for p in pages[:4])
    nav_links = "\n".join(f'          <Link to="{p["route"]}" style={{{{ padding:"8px 14px", borderRadius:999, textDecoration:"none", fontSize:12, fontWeight:500, color:"var(--intara-muted)", border:"1px solid transparent" }}}}>{p["name"]}</Link>' for p in pages[:4])
    files.append({"path": "src/App.tsx", "content": f"""import {{ BrowserRouter, Routes, Route, Link }} from 'react-router-dom'
import {{ useEffect }} from 'react'
import {{ {imports_str} }} from './pages'

export default function App() {{
  useEffect(() => {{
    // Trial: IndexedDB mock — no backend needed
    import('./mock/server').then(m => m.installMockServer())
    import('./mock/seed').then(m => m.seedPreview())
  }}, [])
  return (
    <BrowserRouter>
      <div style={{{{ minHeight:"100vh", background:"#07070B", color:"#F8FAFC", fontFamily:"Inter, system-ui, sans-serif" }}}}>
        <nav style={{{{ display:"flex", gap:8, padding:"16px 20px", borderBottom:"1px solid rgba(255,255,255,0.06)", position:"sticky", top:0, background:"rgba(7,7,11,0.8)", backdropFilter:"blur(16px)", zIndex:10 }}}}>
          <span style={{{{ fontFamily:"Space Grotesk", fontWeight:500, letterSpacing:"-0.02em", marginRight:12 }}}}>{app_name}</span>
{nav_links}
        </nav>
        <main style={{{{ maxWidth:820, margin:"0 auto", padding:"24px 20px" }}}}>
          <Routes>
{routes_str}
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}}
""" })
    # src/pages/index.ts barrel
    files.append({"path": "src/pages/index.ts", "content": "\n".join([f"export {{ default as {page_ident(p['name'])} }} from './{page_ident(p['name'])}'" for p in pages[:4]])})

    if _csv_emitted:
        files.append({"path": "src/lib/csv.ts", "content": CSV_LIB_TS})

    # Guarantee: csv-export selected ⇒ helper exists even when every page came
    # from the LLM path (which never emits it). Button wiring is enforced by
    # check_csv_export and fixed by gate repair.
    if _csv_export_tables(prd) is not None and "src/lib/csv.ts" not in {f["path"] for f in files}:
        files.append({"path": "src/lib/csv.ts", "content": CSV_LIB_TS})

    # Guarantee: file-upload selected ⇒ upload helper exists (bucket from unit
    # config, default "uploads"), even on all-LLM page sets.
    if _upload_target_tables(prd) is not None and "src/lib/upload.ts" not in {f["path"] for f in files}:
        files.append({"path": "src/lib/upload.ts",
                      "content": UPLOAD_LIB_TS.replace("__BUCKET__", _upload_bucket_name(prd))})

    # Normalize every returned page (template or LLM): spaced identifiers
    # crash bundlers, so slug paths + default-export names uniformly.
    files = [normalize_frag({"files": [f]})["files"][0] if f.get("path", "").startswith("src/pages/") else f for f in files]
    # ensure at least 3 files
    n_pages = len([p for p in pages[:6]])
    if _fallbacks:
        _meta = {"source": "mixed" if len(_fallbacks) < n_pages else "template",
                 "fallback_reason": "; ".join(f"{f['page']}: {f['reason']}" for f in _fallbacks)[:500],
                 "fallbacks": _fallbacks}
    else:
        _meta = {"source": "template" if _template_only else "llm", "fallback_reason": None, "fallbacks": []}
    return {"files": files, "_meta": _meta}
