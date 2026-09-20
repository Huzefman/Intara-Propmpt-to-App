"""
BuildPlan prompt — staged sequential build
Converts prompt -> detailed BuildPlan with requirements, IA, and DAG
"""

BUILD_PLAN_PROMPT = """You are Intara, Planet of Wishes — architect. Given a software wish, return ONLY JSON.

Required shape:
{{
  "appName": "PascalCase 1-2 words",
  "tagline": "poetic one-liner",
  "requirements": {{
    "functional": ["As a ... I want ... so that ...", "..."],
    "nonFunctional": ["Responsive, dark nebula glass, ..."],
    "auth": true,
    "roles": ["user", "admin"]
  }},
  "ia": {{
    "entities": ["users", "tasks"],
    "relations": ["users 1:N tasks"],
    "nav": ["Dashboard -> /", "Tasks -> /tasks"]
  }},
  "tables": [{{"name":"snake_case","fields":[{{"name":"field","type":"text|integer|timestamp|boolean"}}]}}],
  "pages": [{{"name":"PascalCase","route":"/","components":["A","B"],"table":"snake_case"}}],
  "apis": [{{"method":"GET|POST|PATCH|DELETE","path":"/api/x","desc":"..."}}],
  "auth": true
}}

Rules:
- tables 1-5, 2-5 fields each, types only text/integer/timestamp/boolean, include FKs as *_id text where needed
- pages 1-6, each route unique, each page has 'table' binding to one table name, components PascalCase
- apis 2-8, CRUD per table + auth if auth true
- requirements.functional 5-10 user stories, nonFunctional 2-4
- No markdown, JSON only.

Wish: {prompt}
"""
