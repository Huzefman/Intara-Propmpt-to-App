"""
Scaffold generator — makes generated projects runnable without extra config.
Frontend: Vite + React 18 + TS + Tailwind + Router + Supabase + Dexie (preview)
Backend: FastAPI + SQLite (default) + Supabase adapter when env set
"""

def frontend_scaffold(app_name: str):
    slug = app_name.lower().replace(" ", "-")
    files = {}

    # package.json — runnable
    files["package.json"] = """{
  "name": "%s",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.0",
    "@supabase/supabase-js": "^2.45.0",
    "dexie": "^4.0.8"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.4.2",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
""" % slug

    files["vite.config.ts"] = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: { port: 5174 }
})
"""

    files["tsconfig.json"] = """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
"""

    files["index.html"] = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{app_name} — Intara</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""

    files["src/main.tsx"] = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
"""

    files["src/index.css"] = """@tailwind base;
@tailwind components;
@tailwind utilities;
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #0a0a12; color: #f8fafc; }
"""

    files["src/vite-env.d.ts"] = """/// <reference types="vite/client" />
"""

    files[".env.example"] = """VITE_API_MODE=mock
# mock = in-browser IndexedDB (Sandpack trial, no server)
# supabase = real Supabase
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_URL=http://localhost:8000
"""

    files["tailwind.config.js"] = """export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: []
}
"""

    files["postcss.config.js"] = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""

    return files


def backend_scaffold(app_name: str, tables, ddl: str = ""):
    """Single canonical db.py at server/db.py (imported as `from server.db import ...`
    with cwd=backend/). init_db executes real CREATE TABLE DDL — no stubs."""
    files = {}

    db_py = f'''"""
DB adapter — SQLite default, Supabase when env set.
Single canonical module: import as `from server.db import ...` with cwd=backend/.
"""
import os
from sqlalchemy import create_engine, text

SUPA_URL = os.getenv("SUPABASE_URL", "")
SUPA_KEY = os.getenv("SUPABASE_KEY", "")

# SQLite fallback (no config needed) — lives next to backend/ cwd
engine = create_engine("sqlite:///./app.db", connect_args={{"check_same_thread": False}})

DDL = """{ddl}"""

def get_engine():
    return engine

def init_db():
    if DDL.strip():
        with engine.begin() as conn:
            for stmt in DDL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))

# Supabase client when configured
supabase = None
if SUPA_URL and SUPA_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPA_URL, SUPA_KEY)
    except Exception as e:
        print(f"supabase init failed: {{e}}")
'''
    files["server/db.py"] = db_py

    files[".env.example"] = """SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
GEMINI_API_KEY=your_gemini_key
# Leave empty to use SQLite local DB (no Supabase needed for trial)
# Backend auto-falls back to SQLite if no Supabase
"""
    files["server/__init__.py"] = ""

    # Supabase Storage bucket for the file-upload component. SQLite ignores it
    # (uploads fall back to Data URLs); apply once in the Supabase SQL editor
    # when going live, then set window.__INTARA_ENV__ in the frontend entry.
    files["storage.sql"] = """-- Intara file uploads (Supabase Storage). Run once in the SQL editor.
insert into storage.buckets (id, name, public)
values ('uploads', 'uploads', true)
on conflict (id) do nothing;

drop policy if exists "uploads public read" on storage.objects;
create policy "uploads public read"
  on storage.objects for select using (bucket_id = 'uploads');

drop policy if exists "uploads anyone can add" on storage.objects;
create policy "uploads anyone can add"
  on storage.objects for insert with check (bucket_id = 'uploads');
"""

    files["README_BACKEND.md"] = f"""# {app_name} Backend

Run without Supabase (SQLite):

```bash
cd backend
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8000
```

With Supabase: set `SUPABASE_URL` and `SUPABASE_KEY` in `.env`, then same command — db.py swaps to Supabase.

File uploads: run `storage.sql` once in the Supabase SQL editor to create the
`uploads` bucket, then expose the project credentials to the frontend via
`window.__INTARA_ENV__ = {{ SUPABASE_URL, SUPABASE_ANON_KEY }}`. Without it,
uploads persist as local Data URLs per record.
"""

    return files
