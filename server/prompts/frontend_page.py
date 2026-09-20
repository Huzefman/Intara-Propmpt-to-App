"""
Per-page frontend prompt — one page at a time, Sandpack-safe
"""
FRONTEND_PAGE_PROMPT = """You are Intara frontend weaver — build ONE page for Vite React 18 + TypeScript + Tailwind, Sandpack safe (no import.meta).

Context:
- App: __APP_NAME__ — __TAGLINE__
- Table for this page: __TABLE__ fields: __FIELDS__
- Page: __PAGE_NAME__ route: __ROUTE__ components: __COMPONENTS__
- All tables: __ALL_TABLES__
- All pages: __ALL_PAGES__

Return ONLY JSON with path and content for src/pages/__PAGE_NAME__.tsx

Rules:
- Use React useState/useEffect, fetch('/api/__TABLE__') for list, POST for create, Tailwind glass, Space Grotesk, no import.meta
- Include 3 inputs for first 3 fields, Create button, grid
- No markdown
"""
