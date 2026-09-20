"""
Intara — Planner: wish -> PRD
"""
import json, re, os
from prompts.intara import INTARA_PLANNER_PROMPT
# import lazily to avoid circular
def parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if m: text = m.group(0)
    return json.loads(text)

def mock_prd(prompt: str) -> dict:
    p = prompt.lower()
    # simple keyword match to pick fixture-like PRD, else generic
    if "task" in p:
        return {
            "appName": "TaskOrb",
            "tagline": "Track tasks across the cosmos",
            "tables": [
                {"name": "users", "fields": [{"name": "email", "type": "text"}, {"name": "created_at", "type": "timestamp"}]},
                {"name": "tasks", "fields": [{"name": "title", "type": "text"}, {"name": "due_date", "type": "timestamp"}, {"name": "completed", "type": "boolean"}]}
            ],
            "pages": [
                {"name": "Dashboard", "route": "/", "components": ["TaskList", "TaskCard"]},
                {"name": "TaskDetail", "route": "/tasks/:id", "components": ["TaskForm"]},
                {"name": "Profile", "route": "/profile", "components": ["UserProfile"]}
            ],
            "apis": [
                {"method": "GET", "path": "/api/tasks", "desc": "list tasks"},
                {"method": "POST", "path": "/api/tasks", "desc": "create task"},
                {"method": "PATCH", "path": "/api/tasks/:id", "desc": "update task"},
                {"method": "GET", "path": "/api/users", "desc": "list users"}
            ],
            "auth": True
        }
    if "blog" in p:
        return {
            "appName": "BlogNebula",
            "tagline": "Write across the stars",
            "tables": [
                {"name": "authors", "fields": [{"name": "name", "type": "text"}, {"name": "email", "type": "text"}]},
                {"name": "posts", "fields": [{"name": "title", "type": "text"}, {"name": "body", "type": "text"}, {"name": "published", "type": "boolean"}]},
                {"name": "comments", "fields": [{"name": "body", "type": "text"}, {"name": "created_at", "type": "timestamp"}]}
            ],
            "pages": [
                {"name": "Feed", "route": "/", "components": ["PostList", "PostCard"]},
                {"name": "Post", "route": "/posts/:id", "components": ["PostDetail", "CommentList"]}
            ],
            "apis": [
                {"method": "GET", "path": "/api/posts", "desc": "list posts"},
                {"method": "POST", "path": "/api/posts", "desc": "create post"},
                {"method": "GET", "path": "/api/comments", "desc": "list comments"},
                {"method": "POST", "path": "/api/comments", "desc": "create comment"}
            ],
            "auth": True
        }
    if "ecommerce" in p or "e-commerce" in p or "wishlist" in p or "shop" in p or "product" in p:
        return {
            "appName": "WishMart",
            "tagline": "Shop the Intara way",
            "tables": [
                {"name": "products", "fields": [{"name": "name", "type": "text"}, {"name": "price", "type": "integer"}]},
                {"name": "carts", "fields": [{"name": "quantity", "type": "integer"}, {"name": "created_at", "type": "timestamp"}]},
                {"name": "orders", "fields": [{"name": "total", "type": "integer"}, {"name": "status", "type": "text"}]}
            ],
            "pages": [
                {"name": "Catalog", "route": "/", "components": ["ProductGrid", "ProductCard"]},
                {"name": "Cart", "route": "/cart", "components": ["CartList"]},
                {"name": "Orders", "route": "/orders", "components": ["OrderList"]}
            ],
            "apis": [
                {"method": "GET", "path": "/api/products", "desc": "list products"},
                {"method": "POST", "path": "/api/carts", "desc": "add to cart"},
                {"method": "POST", "path": "/api/orders", "desc": "create order"}
            ],
            "auth": True
        }
    if "booking" in p or "salon" in p or "appointment" in p:
        return {
            "appName": "SalonOrbit",
            "tagline": "Book your shine",
            "tables": [
                {"name": "services", "fields": [{"name": "name", "type": "text"}, {"name": "duration", "type": "integer"}]},
                {"name": "slots", "fields": [{"name": "start_time", "type": "timestamp"}, {"name": "available", "type": "boolean"}]},
                {"name": "appointments", "fields": [{"name": "customer", "type": "text"}, {"name": "created_at", "type": "timestamp"}]}
            ],
            "pages": [
                {"name": "Services", "route": "/", "components": ["ServiceList", "ServiceCard"]},
                {"name": "Booking", "route": "/book", "components": ["SlotPicker", "BookingForm"]}
            ],
            "apis": [
                {"method": "GET", "path": "/api/services", "desc": "list services"},
                {"method": "GET", "path": "/api/slots", "desc": "list slots"},
                {"method": "POST", "path": "/api/appointments", "desc": "create appointment"}
            ],
            "auth": False
        }
    if "forum" in p or "q&a" in p or "question" in p:
        return {
            "appName": "AskIntara",
            "tagline": "Questions drift, answers land",
            "tables": [
                {"name": "questions", "fields": [{"name": "title", "type": "text"}, {"name": "body", "type": "text"}]},
                {"name": "answers", "fields": [{"name": "body", "type": "text"}, {"name": "votes", "type": "integer"}]},
                {"name": "tags", "fields": [{"name": "name", "type": "text"}]}
            ],
            "pages": [
                {"name": "Questions", "route": "/", "components": ["QuestionList", "QuestionCard"]},
                {"name": "Ask", "route": "/ask", "components": ["QuestionForm"]},
                {"name": "QuestionDetail", "route": "/questions/:id", "components": ["AnswerList", "AnswerForm"]}
            ],
            "apis": [
                {"method": "GET", "path": "/api/questions", "desc": "list questions"},
                {"method": "POST", "path": "/api/questions", "desc": "create question"},
                {"method": "POST", "path": "/api/answers", "desc": "create answer"}
            ],
            "auth": True
        }
    # generic fallback: derive tables from prompt heuristics
    words = [w for w in re.findall(r"[a-z]+", p) if len(w) > 3][:4]
    # fallback tables: try extract nouns; simple heuristic
    base = words[0] if words else "items"
    return {
        "appName": "".join(w.capitalize() for w in words[:2]) or "IntaraApp",
        "tagline": f"Intara forged: {prompt[:60]}",
        "tables": [
            {"name": "users", "fields": [{"name": "email", "type": "text"}, {"name": "created_at", "type": "timestamp"}]},
            {"name": base + "s" if not base.endswith("s") else base, "fields": [{"name": "title", "type": "text"}, {"name": "status", "type": "text"}, {"name": "created_at", "type": "timestamp"}]}
        ],
        "pages": [
            {"name": "Dashboard", "route": "/", "components": ["ItemList", "ItemCard"]},
            {"name": "Detail", "route": "/items/:id", "components": ["ItemDetail"]},
        ],
        "apis": [
            {"method": "GET", "path": f"/api/{base}s", "desc": f"list {base}s"},
            {"method": "POST", "path": f"/api/{base}s", "desc": f"create {base}"},
            {"method": "GET", "path": "/api/users", "desc": "list users"},
        ],
        "auth": True
    }

def plan_wish(prompt: str) -> dict:
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        # mocked deterministic, zero cost, for demo/free tier
        return mock_prd(prompt)
    # try real Gemini with guard + retry; import here to avoid hard dep if not installed
    try:
        from main import call_gemini, parse_json as main_parse
        raw = call_gemini(INTARA_PLANNER_PROMPT.format(prompt=prompt))
        try:
            data = main_parse(raw)
            # validate minimal shape
            if "appName" not in data or "tables" not in data:
                raise ValueError("missing keys")
            return data
        except Exception as e:
            # repair pass
            raw2 = call_gemini(f"Fix this to valid JSON with required keys appName,tagline,tables,pages,apis,auth: {raw}")
            try:
                data = main_parse(raw2)
                return data
            except:
                # fallback to mock on repair fail
                print(f"planner repair failed: {e}, falling back to mock")
                return mock_prd(prompt)
    except Exception as e:
        print(f"planner fallback due to: {e}")
        return mock_prd(prompt)
