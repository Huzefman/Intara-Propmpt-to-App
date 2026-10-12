#!/usr/bin/env python3
"""Build the exemplar retrieval index (Phase 5, P5.2).

Reads packages/spec/exemplars/*.json, embeds each spec's text, writes
evals/retrieval_index.json (768-d vectors, versioned, reviewable).
  python scripts/build_retrieval_index.py --fake    # deterministic, no keys
  python scripts/build_retrieval_index.py           # live embedder (needs keys)
Held-out domains are refused (fail-fast) — see services/retrieval.py.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

from services.retrieval import DIM, build_index, index_to_json, tags_of_spec, text_of_spec  # noqa: E402


def bow_embed(texts):
    vecs = []
    for t in texts:
        v = [0.0] * DIM
        for tok in re.findall(r"[a-z]+", (t or "").lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        vecs.append(v)
    return vecs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="deterministic vectors, no keys")
    ap.add_argument("--out", default="evals/retrieval_index.json")
    args = ap.parse_args()
    items = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "packages", "spec", "exemplars", "*.json"))):
        spec = json.load(open(fp))
        domain = (spec.get("app") or {}).get("domain") or "unknown"
        items.append({"id": os.path.basename(fp)[:-5], "domain": domain,
                      "tags": tags_of_spec(spec), "text": text_of_spec(spec)})
    idx = build_index(items, embed_fn=bow_embed if args.fake else None)
    out = os.path.join(ROOT, args.out)
    open(out, "w").write(index_to_json(idx))
    print(f"indexed {len(items)} exemplars -> {args.out} "
          f"({'fake' if args.fake else 'live'} vectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
