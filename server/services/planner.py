"""
Intara — Planner: wish -> PRD
"""
import re, os
from prompts.intara import INTARA_PLANNER_PROMPT
from utils.json_parse import parse_json, is_quota_error

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
    if "recipe" in p:
        return {
            "appName": "RecipeVault",
            "tagline": "Your personal recipe collection",
            "tables": [
                {"name": "users", "fields": [{"name": "email", "type": "text"}, {"name": "created_at", "type": "timestamp"}]},
                {"name": "recipes", "fields": [{"name": "title", "type": "text"}, {"name": "prep_time", "type": "integer"}, {"name": "difficulty", "type": "text"}]},
                {"name": "favorites", "fields": [{"name": "user_id", "type": "uuid"}, {"name": "recipe_id", "type": "uuid"}]},
                {"name": "reviews", "fields": [{"name": "rating", "type": "integer"}, {"name": "comment", "type": "text"}]}
            ],
            "pages": [
                {"name": "Catalog", "route": "/", "components": ["SearchBar", "RecipeGrid", "CategoryFilter"], "table": "recipes"},
                {"name": "RecipeDetail", "route": "/recipes/:id", "components": ["RecipeDetail", "ReviewList"], "table": "recipes"},
                {"name": "Favorites", "route": "/favorites", "components": ["FavoritesList"], "table": "favorites"},
                {"name": "Profile", "route": "/profile", "components": ["UserProfile"], "table": "users"}
            ],
            "apis": [
                {"method": "GET", "path": "/api/recipes", "desc": "list recipes"},
                {"method": "POST", "path": "/api/recipes", "desc": "create recipe"},
                {"method": "GET", "path": "/api/favorites", "desc": "list favorites"},
                {"method": "POST", "path": "/api/favorites", "desc": "save favorite"},
                {"method": "GET", "path": "/api/reviews", "desc": "list reviews"}
            ],
            "auth": True
        }
    if "library" in p:
        return {
            "appName": "LibraVault",
            "tagline": "Your curated library, beautifully organized",
            "tables": [
                {"name": "users", "fields": [{"name": "email", "type": "text"}, {"name": "membership_id", "type": "text"}]},
                {"name": "books", "fields": [{"name": "title", "type": "text"}, {"name": "author", "type": "text"}, {"name": "isbn", "type": "text"}, {"name": "available", "type": "boolean"}]},
                {"name": "loans", "fields": [{"name": "user_id", "type": "uuid"}, {"name": "book_id", "type": "uuid"}, {"name": "due_date", "type": "timestamp"}, {"name": "returned", "type": "boolean"}]},
                {"name": "categories", "fields": [{"name": "name", "type": "text"}]}
            ],
            "pages": [
                {"name": "Catalog", "route": "/", "components": ["SearchBar", "BookGrid", "CategoryFilter"], "table": "books"},
                {"name": "BookDetail", "route": "/books/:id", "components": ["BookDetail", "LoanButton"], "table": "books"},
                {"name": "MyLoans", "route": "/loans", "components": ["LoanList"], "table": "loans"},
                {"name": "Members", "route": "/members", "components": ["MemberList"], "table": "users"}
            ],
            "apis": [
                {"method": "GET", "path": "/api/books", "desc": "list books"},
                {"method": "POST", "path": "/api/books", "desc": "add book"},
                {"method": "POST", "path": "/api/loans", "desc": "loan a book"},
                {"method": "GET", "path": "/api/loans", "desc": "list loans"},
                {"method": "GET", "path": "/api/users", "desc": "list members"}
            ],
            "auth": True
        }
    if "hr" in p or "human resource" in p or "employee" in p:
        return {
            "appName": "PeoplePulse",
            "tagline": "HR that puts people first",
            "tables": [
                {"name": "employees", "fields": [{"name": "name", "type": "text"}, {"name": "email", "type": "text"}, {"name": "department", "type": "text"}, {"name": "role", "type": "text"}]},
                {"name": "departments", "fields": [{"name": "name", "type": "text"}, {"name": "head", "type": "text"}]},
                {"name": "leaves", "fields": [{"name": "employee_id", "type": "uuid"}, {"name": "start_date", "type": "timestamp"}, {"name": "end_date", "type": "timestamp"}, {"name": "status", "type": "text"}]},
                {"name": "attendance", "fields": [{"name": "employee_id", "type": "uuid"}, {"name": "date", "type": "timestamp"}, {"name": "present", "type": "boolean"}]}
            ],
            "pages": [
                {"name": "Directory", "route": "/", "components": ["EmployeeGrid", "SearchBar"], "table": "employees"},
                {"name": "Departments", "route": "/departments", "components": ["DepartmentList"], "table": "departments"},
                {"name": "Leaves", "route": "/leaves", "components": ["LeaveCalendar"], "table": "leaves"},
                {"name": "Attendance", "route": "/attendance", "components": ["AttendanceTable"], "table": "attendance"}
            ],
            "apis": [
                {"method": "GET", "path": "/api/employees", "desc": "list employees"},
                {"method": "POST", "path": "/api/employees", "desc": "add employee"},
                {"method": "GET", "path": "/api/leaves", "desc": "list leaves"},
                {"method": "POST", "path": "/api/leaves", "desc": "request leave"},
                {"method": "GET", "path": "/api/attendance", "desc": "list attendance"}
            ],
            "auth": True
        }
    # generic fallback: prompt-aware, more distinct than SimpleGame
    words = [w for w in re.findall(r"[a-z]+", p) if len(w) > 3]
    # filter common stop words
    stop = {"with","from","that","this","have","will","your","about","into","over","under","while","where","when","what","which","their","there","would","could","should"}
    keywords = [w for w in words if w not in stop][:6]
    if len(keywords) >= 2:
        app_name = "".join(w.capitalize() for w in keywords[:2])
        base = keywords[1] if len(keywords) > 1 else keywords[0]
        base2 = keywords[2] if len(keywords) > 2 else "items"
    else:
        base = keywords[0] if keywords else "items"
        app_name = "".join(w.capitalize() for w in keywords[:2]) or "IntaraApp"
        base2 = "items"
    # ensure tables are distinct and not just users+base
    t1 = base + "s" if not base.endswith("s") else base
    t2 = base2 + "s" if not base2.endswith("s") else base2
    if t1 == t2:
        t2 = "details"
    # pick fields based on keywords
    fields_map = {
        "game": [{"name":"title","type":"text"},{"name":"score","type":"integer"},{"name":"level","type":"integer"}],
        "spell": [{"name":"name","type":"text"},{"name":"power","type":"integer"},{"name":"element","type":"text"}],
        "fitness": [{"name":"name","type":"text"},{"name":"duration","type":"integer"},{"name":"calories","type":"integer"}],
        "market": [{"name":"name","type":"text"},{"name":"price","type":"integer"},{"name":"stock","type":"integer"}],
        "shop": [{"name":"name","type":"text"},{"name":"price","type":"integer"},{"name":"stock","type":"integer"}],
    }
    def fields_for(base_word):
        for k, v in fields_map.items():
            if k in base_word:
                return v
        return [{"name":"title","type":"text"},{"name":"status","type":"text"},{"name":"created_at","type":"timestamp"}]

    return {
        "appName": app_name[:20],
        "tagline": f"Intara forged: {prompt[:60]}",
        "tables": [
            {"name": "users", "fields": [{"name": "email", "type": "text"}, {"name": "created_at", "type": "timestamp"}]},
            {"name": t1, "fields": fields_for(t1)},
            {"name": t2, "fields": fields_for(t2)},
        ][:3],
        "pages": [
            {"name": "Dashboard", "route": "/", "components": [f"{t1.capitalize()}List", f"{t1.capitalize()}Card"], "table": t1},
            {"name": "Explore", "route": f"/{t1}", "components": [f"{t1.capitalize()}Grid"], "table": t1},
            {"name": "Detail", "route": f"/{t1}/:id", "components": [f"{t1.capitalize()}Detail"], "table": t1},
        ][:3],
        "apis": [
            {"method": "GET", "path": f"/api/{t1}", "desc": f"list {t1}"},
            {"method": "POST", "path": f"/api/{t1}", "desc": f"create {t1}"},
            {"method": "GET", "path": f"/api/{t2}", "desc": f"list {t2}"},
            {"method": "GET", "path": "/api/users", "desc": "list users"},
        ],
        "auth": True
    }

def _is_quota(e: Exception) -> bool:
    return is_quota_error(e)

def plan_wish(prompt: str) -> dict:
    try:
        from services.llm import has_any_llm
        has_llm = has_any_llm()
    except Exception:
        has_llm = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("NVIDIA_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))
    if not has_llm:
        data = mock_prd(prompt)
        data["_meta"] = {"source": "mock", "reason": "no_key"}
        return data
    try:
        from services.llm import call_llm, call_llm_with_meta
        from main import parse_json as main_parse
        raw, meta = call_llm_with_meta(INTARA_PLANNER_PROMPT.format(prompt=prompt))
        call_gemini = call_llm  # alias for repair
        try:
            data = main_parse(raw)
            if "appName" not in data or "tables" not in data:
                raise ValueError("missing keys")
            data["_meta"] = meta
            return data
        except Exception as e:
            if _is_quota(e):
                raise
            raw2, meta2 = call_llm_with_meta(f"Fix this to valid JSON with required keys appName,tagline,tables,pages,apis,auth: {raw}")
            try:
                data = main_parse(raw2)
                data["_meta"] = {**meta2, "repaired": True}
                return data
            except Exception as e2:
                if _is_quota(e2):
                    raise
                print(f"planner repair failed: {e}, falling back to mock")
                data = mock_prd(prompt)
                data["_meta"] = {"source": "mock", "reason": "repair_failed"}
                return data
    except Exception as e:
        if _is_quota(e):
            # All providers exhausted (chain tried OR→Gemini→Groq→Nvidia→DeepSeek):
            # degrade to mock with warning instead of 500/429 so the app keeps working.
            print(f"planner all-providers exhausted, mock fallback with warning: {e}")
            data = mock_prd(prompt)
            data["_meta"] = {"source": "mock", "reason": "all_exhausted", "warning": f"All LLM quotas exhausted. Using mock for now. Retry in ~60s. Prompt: {prompt[:40]}"}
            return data
        print(f"planner fallback due to: {e}")
        data = mock_prd(prompt)
        data["_meta"] = {"source": "mock", "reason": str(e)[:120]}
        return data
