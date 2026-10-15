"""
v2 run engine (Phase 7, P7.1): deterministic state machine over agent steps.

run(project, base_version, kind): DAG of (step_key, agent, deps) → for each
ready step (concurrency ≤2): build input (slice + retrieval, logged) →
resume-or-run (content-addressed artifacts; kills rerun only missing steps) →
gate → repair(≤2)/degrade/fail → persist step + event. Assemble → immutable
spec version → build report.

Durable: run_steps stores input/output hashes (services.artifacts); kill
mid-run → restart → done steps resolve from the store. Event-sourced:
run_events append-only; SSE streams history + live; finished runs replay.
Budgets (max_llm_calls, max_wall_seconds, max_repairs_per_step) end runs in
explicit degraded/failed states. v1 = in-process worker, all state in
Postgres (MemoryRunStore for tests); the boot sweeper requeues orphaned
`running` run_steps (see services/sweeper.py).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

STEP_ORDER = ["s0", "s1", "s2", "s3", "s4", "s5", "s6"]
# S3 → S4 run sequentially, not parallel: S4's prompt and gate consume S3's
# page roles (guide §7.2 lists ui summary as S4 input). The semaphore stays
# for future independent steps; free-tier quotas prefer sequential anyway.
PARALLEL_OK: set = set()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str).encode()


def input_hash(agent: str, prompt_version: str, payload: dict) -> str:
    return hashlib.sha256(agent.encode() + b"|" + prompt_version.encode()
                          + b"|" + _canonical(payload)).hexdigest()


class RunStore:
    """Persistence seam (MemoryRunStore for tests, SupabaseRunStore live)."""

    def create_run(self, project_id: str, kind: str, inputs: dict) -> str:
        raise NotImplementedError

    def set_status(self, run_id: str, status: str, error: str | None = None) -> None:
        raise NotImplementedError

    def get_run(self, run_id: str) -> dict:
        raise NotImplementedError

    def upsert_step(self, run_id: str, step_key: str, agent: str, status: str,
                    input_hash: str | None = None, output_hash: str | None = None,
                    attempt: int = 1, fallback_reason: str | None = None) -> None:
        raise NotImplementedError

    def get_steps(self, run_id: str) -> list:
        raise NotImplementedError

    def append_event(self, run_id: str, type: str, payload: dict) -> None:
        raise NotImplementedError

    def get_events(self, run_id: str) -> list:
        raise NotImplementedError

    def create_version(self, project_id: str, parent_id: str | None,
                       spec: dict, source: str) -> str:
        raise NotImplementedError

    def get_version(self, version_id: str) -> dict:
        raise NotImplementedError


class MemoryRunStore(RunStore):
    def __init__(self):
        self.runs: dict = {}
        self.steps: dict = {}
        self.events: dict = {}
        self.versions: dict = {}
        self.n = 0

    def _id(self, p: str) -> str:
        self.n += 1
        return f"{p}-{self.n}"

    def create_run(self, project_id, kind, inputs):
        rid = self._id("run")
        self.runs[rid] = {"id": rid, "project_id": project_id, "kind": kind,
                          "status": "queued", "inputs": inputs, "error": None}
        self.steps[rid] = {}
        self.events[rid] = []
        return rid

    def set_status(self, run_id, status, error=None):
        self.runs[run_id]["status"] = status
        if error is not None:
            self.runs[run_id]["error"] = error

    def get_run(self, run_id):
        return dict(self.runs[run_id])

    def upsert_step(self, run_id, step_key, agent, status, input_hash=None,
                    output_hash=None, attempt=1, fallback_reason=None):
        self.steps[run_id][step_key] = {
            "step_key": step_key, "agent": agent, "status": status,
            "input_hash": input_hash, "output_hash": output_hash,
            "attempt": attempt, "fallback_reason": fallback_reason}

    def get_steps(self, run_id):
        return list(self.steps[run_id].values())

    def append_event(self, run_id, type, payload):
        self.events[run_id].append({"type": type, "payload": payload,
                                    "ts": time.time()})

    def get_events(self, run_id):
        return list(self.events[run_id])

    def create_version(self, project_id, parent_id, spec, source):
        from engine.versions import spec_hash
        vid = self._id("v")
        self.versions[vid] = {"id": vid, "project_id": project_id,
                              "parent": parent_id, "spec": spec,
                              "hash": spec_hash(spec), "source": source}
        return vid

    def get_version(self, version_id):
        return dict(self.versions[version_id])


class SupabaseRunStore(RunStore):
    """Postgres-backed store (service key — 006 tables are API-only)."""

    def __init__(self):
        import os
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_SERVICE_KEY required for v2 runs")
        from supabase import create_client
        self.supa = create_client(url, key)

    def create_run(self, project_id, kind, inputs):
        res = self.supa.table("runs").insert(
            {"project_id": project_id, "kind": kind, "status": "queued",
             "budget": inputs.get("budgets", {})}).execute()
        if not res.data:
            raise RuntimeError("runs insert failed")
        return res.data[0]["id"]

    def set_status(self, run_id, status, error=None):
        payload: dict = {"status": status}
        if error is not None:
            payload["error"] = error[:2000]
        if status in ("done", "degraded", "failed", "cancelled"):
            payload["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        res = self.supa.table("runs").update(payload).eq("id", run_id).execute()
        if not res.data:
            raise RuntimeError(f"runs status update failed for {run_id}")

    def get_run(self, run_id):
        res = self.supa.table("runs").select("*").eq("id", run_id).execute()
        if not res.data:
            raise RuntimeError(f"run {run_id} not found")
        return res.data[0]

    def upsert_step(self, run_id, step_key, agent, status, input_hash=None,
                    output_hash=None, attempt=1, fallback_reason=None):
        existing = self.supa.table("run_steps").select("id").eq(
            "run_id", run_id).eq("step_key", step_key).eq("attempt", attempt).execute()
        payload = {"run_id": run_id, "step_key": step_key, "agent": agent,
                   "status": status, "input_hash": input_hash,
                   "output_hash": output_hash, "attempt": attempt,
                   "fallback_reason": fallback_reason[:500] if fallback_reason else None}
        if existing.data:
            self.supa.table("run_steps").update(payload).eq(
                "id", existing.data[0]["id"]).execute()
        else:
            self.supa.table("run_steps").insert(payload).execute()

    def get_steps(self, run_id):
        res = self.supa.table("run_steps").select("*").eq("run_id", run_id).execute()
        return res.data or []

    def append_event(self, run_id, type, payload):
        self.supa.table("run_events").insert(
            {"run_id": run_id, "type": type, "payload": payload}).execute()

    def get_events(self, run_id):
        res = self.supa.table("run_events").select("type,payload,ts").eq(
            "run_id", run_id).order("id").execute()
        return res.data or []

    def create_version(self, project_id, parent_id, spec, source):
        from engine.versions import spec_hash
        res = self.supa.table("project_versions").insert(
            {"project_id": project_id, "parent_id": parent_id, "spec": spec,
             "spec_hash": spec_hash(spec), "source": source}).execute()
        if not res.data:
            raise RuntimeError("project_versions insert failed")
        return res.data[0]["id"]

    def get_version(self, version_id):
        res = self.supa.table("project_versions").select("*").eq(
            "id", version_id).execute()
        if not res.data:
            raise RuntimeError(f"version {version_id} not found")
        return res.data[0]


DEFAULT_BUDGETS = {"max_llm_calls": 40, "max_wall_seconds": 1800,
                   "max_repairs_per_step": 2}


class RunEngine:
    def __init__(self, store: RunStore, budgets: dict | None = None,
                 caller=None, agents_override: dict | None = None):
        self.store = store
        self.budgets = {**DEFAULT_BUDGETS, **(budgets or {})}
        self.caller = caller
        self.agents_override = agents_override or {}
        self.queues: dict[str, list] = {}
        self._llm_calls = 0
        self._t0 = 0.0

    # -- events --
    def emit(self, run_id: str, type: str, payload: dict) -> None:
        try:
            self.store.append_event(run_id, type, payload)
        except Exception as e:
            print(f"run {run_id}: event persist failed ({type}): {e}")
        for q in self.queues.get(run_id, []):
            try:
                q.put_nowait({"type": type, "payload": payload, "ts": time.time()})
            except Exception:
                pass

    def replay(self, run_id: str) -> list:
        return self.store.get_events(run_id)

    # -- inputs --
    def _retrieval(self, run_id: str, stage: str, hint: str) -> dict:
        """Catalog slice + nearest exemplar, logged to run_events (P7.3)."""
        from agents.stages import STAGES
        _ = STAGES  # stages own their catalog needs; engine supplies the hook
        found: dict = {"blocks": [], "exemplars": []}
        try:
            from services import retrieval as R
            import json as _json
            import os as _os
            idx_path = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "..", "evals", "retrieval_index.json")
            idx_path = _os.path.normpath(idx_path)
            if _os.path.exists(idx_path):
                idx = R.index_from_json(open(idx_path).read())
                hits = R.search(idx, hint, top_k=2)
                found["exemplars"] = [{"id": h["id"], "domain": h["domain"],
                                       "score": h["score"]} for h in hits]
        except Exception as e:
            found["error"] = str(e)[:200]
        try:
            from gates.g1_lint import BLOCKS
            found["blocks"] = sorted(BLOCKS.keys())
        except Exception:
            pass
        self.emit(run_id, "retrieval", {"stage": stage, "hint": hint[:120],
                                        "found": found})
        return found

    def _stage_input(self, key: str, ctx: dict, run_id: str) -> tuple[dict, dict]:
        from agents.stages import STAGES
        from agents.prompts import PROMPT_VERSIONS
        st = STAGES[key]
        spec = ctx.get("spec") or {}
        model = spec.get("model") or {}
        entities = model.get("entities") or []
        model_json = json.dumps(model, separators=(",", ":"))
        retrievals = self._retrieval(run_id, key, ctx.get("wish", "")[:200])
        exemplars = "\n".join(
            f"- {e['id']} ({e['domain']})" for e in retrievals.get("exemplars", []))
        page_roles = sorted({r for p in (spec.get("ui") or {}).get("pages", [])
                             for r in (p.get("roles") or [])})
        entity_fields = {e.get("id"): [f.get("id") for f in e.get("fields", [])]
                         for e in entities}
        base: dict = {
            "wish": ctx.get("wish", ""),
            "clean_wish": ctx.get("clean_wish", ""),
            "answers": ctx.get("answers", ""),
            "assumptions": ctx.get("assumptions", []),
            "domains": exemplars,
            "exemplars": exemplars,
            "model_json": model_json,
            "entity_ids": [e.get("id") for e in entities],
            "personas": json.dumps(spec.get("personas") or []),
            "blocks": ", ".join(retrievals.get("blocks", [])),
            "ui_summary": "; ".join(
                f"{p.get('id')}" for p in (spec.get("ui") or {}).get("pages", [])),
            "page_roles": ", ".join(page_roles) or "owner",
            "page_roles_list": page_roles,
            "entity_fields": entity_fields,
            "actions": "",
            "requirements_json": json.dumps(ctx.get("requirements") or []),
            "requirement_ids": [r.get("id") for r in ctx.get("requirements") or []],
            "spec_summary": "",
            "domain": (spec.get("app") or {}).get("domain", ""),
            "locale": (spec.get("app") or {}).get("locale", "en"),
        }
        return base, {"agent": st["agent"],
                      "prompt_version": PROMPT_VERSIONS[key]}

    # -- one step --
    async def _run_simple(self, run_id: str, key: str, ctx: dict) -> dict:
        from agents.base import run_agent
        from agents.stages import STAGES
        st = STAGES[key]
        payload, meta = self._stage_input(key, ctx, run_id)
        ihash = input_hash(meta["agent"], meta["prompt_version"], payload)
        # resume: done + output resolves + same input → skip
        for s in self.store.get_steps(run_id):
            if s.get("step_key") == key and s.get("status") == "done" \
                    and s.get("input_hash") == ihash and s.get("output_hash"):
                try:
                    from services.artifacts import get as _aget
                    if _aget(s["output_hash"]) is not None:
                        self.emit(run_id, "step_skipped",
                                  {"step": key, "reason": "artifact cached"})
                        return {"skipped": True, "output_hash": s["output_hash"]}
                except Exception:
                    pass
        self.store.upsert_step(run_id, key, meta["agent"], "running",
                               input_hash=ihash)
        self.emit(run_id, "step_started", {"step": key, "agent": meta["agent"]})
        try:
            return await self._run_simple_body(run_id, key, ctx, st, meta,
                                               payload, ihash)
        except Exception as e:
            # hygiene: unexpected throws flip the row (never an orphaned running)
            try:
                self.store.upsert_step(run_id, key, meta["agent"], "failed",
                                       input_hash=ihash,
                                       fallback_reason=f"threw: {e}"[:500])
            except Exception:
                pass
            self.emit(run_id, "step_failed", {"step": key, "error": str(e)[:300]})
            return {"failed": True, "reason": f"step {key} threw: {e}"}

    async def _run_simple_body(self, run_id: str, key: str, ctx: dict,
                               st: dict, meta: dict, payload: dict,
                               ihash: str) -> dict:
        from agents.base import run_agent
        tele = {"wish_id": ctx.get("wish_id"), "step_key": key,
                "agent": meta["agent"], "prompt_version": meta["prompt_version"]}
        if key in self.agents_override:
            result = self.agents_override[key](payload, tele)
        else:
            prompt = st["prompt"](payload)
            gate = (lambda o: st["gate"](o, payload)) if st.get("gate") else None
            result = await asyncio.to_thread(
                run_agent, stage=meta["agent"],
                prompt_version=meta["prompt_version"], prompt=prompt,
                output_model=st["model"], fallback_fn=lambda: st["fallback"](payload),
                gate_fn=gate, max_repairs=self.budgets["max_repairs_per_step"],
                temperature=0.2, telemetry_extra=tele, caller=self.caller)
        self._llm_calls += result.llm_calls
        if self._llm_calls > self.budgets["max_llm_calls"]:
            self.store.upsert_step(run_id, key, meta["agent"], "failed",
                                   input_hash=ihash,
                                   fallback_reason="budget: max_llm_calls exceeded")
            self.emit(run_id, "budget_exceeded",
                      {"step": key, "budget": "max_llm_calls"})
            return {"failed": True, "reason": "budget max_llm_calls exceeded"}
        try:
            from services.artifacts import put as _aput
            out_dict = (result.output.model_dump(mode="json", by_alias=True)
                        if hasattr(result.output, "model_dump") else dict(result.output))
            ohash = _aput({"stage": key, "output": out_dict})
        except Exception as e:
            self.store.upsert_step(run_id, key, meta["agent"], "failed",
                                   input_hash=ihash,
                                   fallback_reason=f"artifact store: {e}"[:500])
            self.emit(run_id, "step_failed", {"step": key, "error": f"store: {e}"[:300]})
            return {"failed": True, "reason": f"artifact store failed: {e}"}
        status = "degraded" if result.degraded else "done"
        self.store.upsert_step(run_id, key, meta["agent"], status,
                               input_hash=ihash, output_hash=ohash,
                               fallback_reason=result.fallback_reason)
        self.emit(run_id, "step_done" if status == "done" else "step_degraded",
                  {"step": key, "degraded": result.degraded,
                   "fallback_reason": result.fallback_reason,
                   "llm_calls": result.llm_calls})
        return {"output": out_dict, "output_hash": ohash,
                "degraded": result.degraded,
                "fallback_reason": result.fallback_reason,
                "llm_calls": result.llm_calls}

    def _resolve_stored(self, output_hash: str | None):
        if not output_hash:
            return None
        try:
            from services.artifacts import get as _aget
            return _aget(output_hash)
        except Exception:
            return None

    async def _run_s5(self, run_id: str, ctx: dict) -> dict:
        """Assemble → G0/G1 → Critic → G2 → repair(≤2) → finalize."""
        from agents.stages import assemble_spec, summarize_spec, STAGES
        from agents.base import run_agent
        from agents.schemas import S5CriticOut
        from agents import prompts as P
        from gates.g0_validate import validate as g0
        from gates.g1_lint import lint as g1
        from gates.g2_coverage import check as g2
        agent, pver = "s5-assembler", "s5-v1"
        # resume: done + output resolves → restore spec, skip
        for s in self.store.get_steps(run_id):
            if s.get("step_key") == "s5" and s.get("status") == "done" and s.get("output_hash"):
                stored = self._resolve_stored(s["output_hash"])
                if stored is not None:
                    self.emit(run_id, "step_skipped", {"step": "s5", "reason": "artifact cached"})
                    return {"skipped": True, "output": stored, "output_hash": s["output_hash"]}
        self.store.upsert_step(run_id, "s5", agent, "running")
        self.emit(run_id, "step_started", {"step": "s5", "agent": agent})
        try:
            return await self._run_s5_body(run_id, ctx, agent)
        except Exception as e:
            try:
                self.store.upsert_step(run_id, "s5", agent, "failed",
                                       fallback_reason=f"threw: {e}"[:500])
            except Exception:
                pass
            self.emit(run_id, "step_failed", {"step": "s5", "error": str(e)[:300]})
            return {"failed": True, "reason": f"step s5 threw: {e}"}

    async def _run_s5_body(self, run_id: str, ctx: dict, agent: str) -> dict:
        """Assemble → G0/G1 → Critic → G2 → repair(≤2) → finalize."""
        from agents.stages import assemble_spec, summarize_spec
        from agents.base import run_agent
        from agents.schemas import S5CriticOut
        from agents import prompts as P
        from gates.g0_validate import validate as g0
        from gates.g1_lint import lint as g1
        from gates.g2_coverage import check as g2
        spec = assemble_spec(ctx.get("spec") or {})
        # R44 (trace refs) is exempt pre-critic: the Critic fills trace next,
        # and G2 gates coverage after. Everything else must hold at assembly.
        problems = g0(spec) + [e["message"] for e in g1(spec)["errors"]
                               if e["rule"] != "R44"]
        if problems:
            self.store.upsert_step(run_id, "s5", agent, "failed",
                                   fallback_reason="; ".join(problems)[:500])
            self.emit(run_id, "step_failed", {"step": "s5", "error": "assemble gates failed"})
            return {"failed": True, "reason": "assemble G0/G1 failed"}
        requirements = ctx.get("requirements") or []
        must_ids = [r.get("id") for r in requirements if r.get("priority") == "must"]
        trace: list = []
        repairs = 0
        degraded_reasons: list = []
        while True:
            prompt = P.s5critic_prompt(json.dumps(requirements), summarize_spec(spec))
            tele = {"wish_id": ctx.get("wish_id"), "step_key": "s5",
                    "agent": "s5-critic", "prompt_version": P.PROMPT_VERSIONS["s5critic"]}
            if "s5critic" in self.agents_override:
                result = self.agents_override["s5critic"]({"prompt": prompt}, tele)
            else:
                result = await asyncio.to_thread(
                    run_agent, stage="s5-critic",
                    prompt_version=P.PROMPT_VERSIONS["s5critic"], prompt=prompt,
                    output_model=S5CriticOut,
                    fallback_fn=lambda: {"trace": [], "critiques": [], "unsatisfied": must_ids},
                    max_repairs=self.budgets["max_repairs_per_step"],
                    temperature=0.2, telemetry_extra=tele, caller=self.caller)
            self._llm_calls += result.llm_calls
            out = (result.output.model_dump(mode="json") if hasattr(result.output, "model_dump")
                   else dict(result.output))
            trace = out.get("trace") or []
            g2res = g2(requirements, trace)
            missing = g2res["missing_must"]
            if not missing:
                if result.degraded:
                    degraded_reasons.append(result.fallback_reason or "critic degraded")
                break
            repairs += 1
            if repairs > self.budgets["max_repairs_per_step"]:
                # explicit degrade: unsatisfied musts ship labelled, never silent
                degraded_reasons.append(f"uncovered musts: {','.join(missing)}")
                for mid in missing:
                    trace.append({"requirement": mid, "satisfied_by": []})
                break
            prompt = (prompt + "\n[REPAIR] These MUST requirements lack coverage: "
                      + ", ".join(missing) + ". Map each to real spec elements.")
        spec["trace"] = trace
        try:
            from services.artifacts import put as _aput
            ohash = _aput({"stage": "s5", "output": spec})
        except Exception as e:
            return {"failed": True, "reason": f"artifact store failed: {e}"}
        status = "degraded" if degraded_reasons else "done"
        self.store.upsert_step(run_id, "s5", agent, status, output_hash=ohash,
                               fallback_reason="; ".join(degraded_reasons)[:500] or None)
        self.emit(run_id, "step_done" if status == "done" else "step_degraded",
                  {"step": "s5", "repairs": repairs,
                   "fallback_reason": "; ".join(degraded_reasons)[:500] or None})
        return {"output": spec, "output_hash": ohash, "degraded": bool(degraded_reasons),
                "repairs": repairs, "llm_calls": 0}

    # -- full run --
    async def run(self, *, project_id: str, kind: str, inputs: dict,
                  run_id: str | None = None) -> dict:
        # run_id is supplied when the caller already created the row (router);
        # otherwise the engine creates it. Exactly one row per run, always.
        run_id = run_id or self.store.create_run(project_id, kind, inputs)
        ctx = self._fresh_ctx(inputs)
        return await self._execute(run_id, project_id, kind, inputs, ctx)

    async def resume_run(self, run_id: str) -> dict:
        """Restart path: pick an existing (failed/orphaned) run back up.

        Done steps resolve from the artifact store; only missing steps rerun.
        """
        run = self.store.get_run(run_id)
        if run.get("status") == "running":
            raise RuntimeError(f"run {run_id} is already running")
        project_id = run.get("project_id")
        kind = run.get("kind", "build")
        inputs = run.get("inputs") or {}
        ctx = self._fresh_ctx(inputs)
        return await self._execute(run_id, project_id, kind, inputs, ctx)

    def _fresh_ctx(self, inputs: dict) -> dict:
        ctx: dict = {"wish": inputs.get("wish", ""), "wish_id": inputs.get("wish_id"),
                     "answers": inputs.get("answers", ""),
                     "app": {"name": inputs.get("app_name", "App")},
                     "requirements": inputs.get("requirements") or [],
                     "spec": {}}
        if not ctx["requirements"] and ctx["wish"]:
            ctx["requirements"] = [{"id": "R1", "text": ctx["wish"][:500],
                                    "priority": "must"}]
        return ctx

    async def _execute(self, run_id: str, project_id: str, kind: str,
                       inputs: dict, ctx: dict) -> dict:
        t0 = time.time()
        self._t0 = t0
        self._llm_calls = 0
        self.store.set_status(run_id, "running")
        self.emit(run_id, "run_started", {"kind": kind, "budgets": self.budgets,
                                          "wish": (inputs.get("wish") or "")[:200]})
        if kind == "iterate":
            return await self._run_iterate(run_id, project_id, ctx, inputs)
        order = [k for k in STEP_ORDER if k != "s5"]
        sem = asyncio.Semaphore(2)
        degraded: list = []
        failed: str | None = None

        async def _one(key: str):
            async with sem:
                if time.time() - t0 > self.budgets["max_wall_seconds"]:
                    return {"failed": True, "reason": "budget max_wall_seconds exceeded"}
                return await self._run_simple(run_id, key, ctx)

        # s0 → s1 → s2 → s3 → s4 sequential (S4 reads S3's page roles);
        # s6 after s5. Semaphore caps any future parallel steps at 2.
        for key in ["s0", "s1", "s2", "s3", "s4"]:
            if failed:
                break
            res = await _one(key)
            failed, res = self._absorb(run_id, key, ctx, res, degraded)
        if not failed:
            res = await self._run_s5(run_id, ctx)
            if res.get("failed"):
                failed = res.get("reason")
            else:
                out = res["output"]
                ctx["spec"] = out.get("output", out) if res.get("skipped") else out
                if res.get("degraded"):
                    degraded.append("s5")
        if not failed:
            res = await _one("s6")
            failed, res = self._absorb(run_id, "s6", ctx, res, degraded)
        if failed:
            self.store.set_status(run_id, "failed", failed)
            self.emit(run_id, "run_failed", {"error": failed})
            return {"run_id": run_id, "status": "failed", "error": failed,
                    "llm_calls": self._llm_calls, "steps": self.store.get_steps(run_id)}
        # finalize: version the spec
        ctx["spec"]["seed"] = ctx.get("seed") or {}
        version_id = self.store.create_version(
            project_id, inputs.get("base_version"), ctx["spec"], "generate")
        status = "degraded" if degraded else "done"
        self.store.set_status(run_id, status)
        self.emit(run_id, "run_done",
                  {"version": version_id, "degraded_steps": degraded,
                   "llm_calls": self._llm_calls,
                   "wall_s": round(time.time() - t0, 1)})
        return {"run_id": run_id, "status": status, "version_id": version_id,
                "spec": ctx["spec"], "llm_calls": self._llm_calls,
                "degraded_steps": degraded,
                "steps": self.store.get_steps(run_id)}

    def _absorb(self, run_id: str, key: str, ctx: dict, res: dict, degraded: list):
        """Fold a step result into ctx. Returns (failed_reason|None, res)."""
        if res.get("failed"):
            return res.get("reason", "step failed"), res
        if res.get("skipped"):
            stored = self._resolve_stored(res.get("output_hash"))
            out = (stored or {}).get("output") or {}
            self._apply_slice(ctx, key, out)
            return None, res
        out = res.get("output") or {}
        self._apply_slice(ctx, key, out)
        if res.get("degraded"):
            degraded.append(key)
        return None, res

    def _apply_slice(self, ctx: dict, key: str, out: dict) -> None:
        spec = ctx.setdefault("spec", {})
        if key == "s0":
            ctx["clean_wish"] = out.get("clean_wish", ctx.get("wish", ""))
            ctx["track"] = out.get("track", "business")
        elif key == "s1":
            ctx["assumptions"] = out.get("assumptions", [])
            if out.get("questions"):
                ctx["questions"] = out["questions"]
        elif key == "s2":
            spec["model"] = out.get("model", {})
        elif key == "s3":
            spec["ui"] = out.get("ui", {})
        elif key == "s4":
            spec["access"] = out.get("access", {})
            spec["automations"] = out.get("automations", [])
        elif key == "s6":
            ctx["seed"] = out.get("seed", {})
        app = ctx.setdefault("app", {"name": "App"})
        spec["app"] = {"name": app.get("name", "App"),
                       "tagline": app.get("tagline", ""),
                       "domain": app.get("domain", ""),
                       "locale": app.get("locale", "en"),
                       "currency": app.get("currency", "USD"),
                       "timezone": app.get("timezone", "UTC")}
        spec["personas"] = spec.get("personas", [])
        spec["requirements"] = ctx.get("requirements", [])
        spec["assumptions"] = ctx.get("assumptions", [])
        spec["integrations"] = spec.get("integrations", [])
        spec["trace"] = spec.get("trace", [])

    async def _run_iterate(self, run_id: str, project_id: str, ctx: dict, inputs: dict) -> dict:
        """Chat edit: base version spec + instruction → validated patch → child version."""
        try:
            return await self._run_iterate_body(run_id, project_id, ctx, inputs)
        except Exception as e:
            try:
                self.store.set_status(run_id, "failed", f"iterate threw: {e}"[:500])
            except Exception:
                pass
            self.emit(run_id, "run_failed", {"error": f"iterate threw: {e}"[:300]})
            return {"run_id": run_id, "status": "failed", "error": f"iterate threw: {e}"}

    async def _run_iterate_body(self, run_id: str, project_id: str, ctx: dict, inputs: dict) -> dict:
        from agents.base import run_agent
        from agents.schemas import IterationOut
        from agents import prompts as P
        from engine.patch import apply as _apply
        from gates.g0_validate import validate as g0
        from gates.g1_lint import lint as g1
        base_vid = inputs.get("base_version")
        if not base_vid:
            self.store.set_status(run_id, "failed", "iterate needs base_version")
            return {"run_id": run_id, "status": "failed", "error": "iterate needs base_version"}
        base = self.store.get_version(base_vid)
        spec = dict(base.get("spec") or {})
        instruction = inputs.get("instruction", "")
        self.emit(run_id, "step_started", {"step": "edit", "agent": "edit-agent"})
        tele = {"wish_id": ctx.get("wish_id"), "step_key": "edit",
                "agent": "edit-agent", "prompt_version": P.PROMPT_VERSIONS["edit"]}
        if "edit" in self.agents_override:
            result = self.agents_override["edit"]({"instruction": instruction}, tele)
        else:
            prompt = P.edit_prompt(instruction, json.dumps(spec)[:12000])

            def _no_fallback():
                raise RuntimeError("edit failed validation and has no safe fallback")

            result = await asyncio.to_thread(
                run_agent, stage="edit-agent",
                prompt_version=P.PROMPT_VERSIONS["edit"], prompt=prompt,
                output_model=IterationOut, fallback_fn=_no_fallback,
                max_repairs=self.budgets["max_repairs_per_step"],
                temperature=0.2, telemetry_extra=tele, caller=self.caller)
        self._llm_calls += result.llm_calls
        out = (result.output.model_dump(mode="json") if hasattr(result.output, "model_dump")
               else dict(result.output))
        try:
            patched = _apply(spec, out.get("patch") or [])
        except Exception as e:
            self.store.set_status(run_id, "failed", f"patch rejected: {e}")
            return {"run_id": run_id, "status": "failed", "error": f"patch rejected: {e}"}
        problems = g0(patched) + [e["message"] for e in g1(patched)["errors"]]
        if problems:
            self.store.set_status(run_id, "failed", "; ".join(problems)[:500])
            self.emit(run_id, "run_failed", {"error": "patched spec failed G0/G1"})
            return {"run_id": run_id, "status": "failed",
                    "error": "; ".join(problems)[:500]}
        vid = self.store.create_version(project_id, base_vid, patched, "iterate")
        self.store.set_status(run_id, "done")
        self.emit(run_id, "run_done", {"version": vid, "summary": out.get("summary", "")})
        return {"run_id": run_id, "status": "done", "version_id": vid,
                "spec": patched, "summary": out.get("summary", ""),
                "patch": out.get("patch"), "llm_calls": self._llm_calls}


_engine: RunEngine | None = None


def get_engine() -> RunEngine:
    """Process-global engine (Supabase store) for router endpoints + SSE v2."""
    global _engine
    if _engine is None:
        _engine = RunEngine(SupabaseRunStore())
    return _engine
