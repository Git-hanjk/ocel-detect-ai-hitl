#!/usr/bin/env python3
"""
Scaffold project folder schema under the existing `Karma/` directory.

Usage:
  python Karma/tools/scaffold.py
  python Karma/tools/scaffold.py --with-templates
  python Karma/tools/scaffold.py --force

Options:
  --with-templates : also create starter SPEC/config/prompt/schema templates (only if missing)
  --force          : overwrite template files if they already exist
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable


# ---------- Template contents (minimal placeholders) ----------

SPEC_MD = """# SPEC — OCEL(P2P) → KG → Anomaly → HITL (with LLM verify/explain)

> This is the canonical spec. Keep it in sync with the implementation.
> (Place the full SPEC content here. You can paste the latest agreed version.)
"""

PIPELINE_YAML = """# Pipeline configuration (starter)
weights:
  wS: 0.45
  wR: 0.20
  wI: 0.25
  wQ: 0.10

llm:
  alpha: 0.7

thresholds:
  lengthy_approval:
    method: "percentile"
    p: 0.95
"""

LLM_YAML = """# LLM configuration (starter)
model: "gpt-5.2-thinking"
temperature: 0.2
max_tokens: 800
"""

SCHEMA_YAML = """# Schema alignment mapping (starter)
# Map raw activity/object/qualifier labels to canonical labels if needed.
activities: {}
object_types: {}
qualifiers: {}
"""

VERIFY_PROMPT = """You are a verifier.

Task: Determine whether the anomaly rule is satisfied by the provided evidence.
Constraints:
- Use ONLY the evidence provided.
- If evidence is insufficient, output verdict=uncertain.

Return STRICT JSON matching the provided schema.
"""

EXPLAIN_PROMPT = """You are an explainer for a human reviewer.

Task: Explain why this case is anomalous using ONLY the evidence provided.
Return STRICT JSON matching the provided schema.
"""

VERIFY_SCHEMA = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["verdict", "v_conf", "explanation", "evidence_used", "possible_false_positive", "next_questions"],
  "properties": {
    "verdict": { "type": "string", "enum": ["confirm", "uncertain", "reject"] },
    "v_conf": { "type": "number", "minimum": 0, "maximum": 1 },
    "explanation": { "type": "string" },
    "evidence_used": { "type": "array", "items": { "type": "string" } },
    "possible_false_positive": { "type": "array", "items": { "type": "string" } },
    "next_questions": { "type": "array", "items": { "type": "string" } }
  },
  "additionalProperties": false
}
"""

EXPLAIN_SCHEMA = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["one_liner", "why_anomalous", "evidence_summary", "what_to_check_next", "possible_normal_reasons"],
  "properties": {
    "one_liner": { "type": "string" },
    "why_anomalous": { "type": "string" },
    "evidence_summary": { "type": "string" },
    "what_to_check_next": { "type": "array", "items": { "type": "string" } },
    "possible_normal_reasons": { "type": "array", "items": { "type": "string" } }
  },
  "additionalProperties": false
}
"""


# ---------- Helpers ----------

def ensure_dirs(base: Path, rel_dirs: Iterable[str]) -> None:
    for d in rel_dirs:
        (base / d).mkdir(parents=True, exist_ok=True)


def touch_if_missing(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def write_template(path: Path, content: str, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-templates", action="store_true", help="Create starter template files (if missing).")
    parser.add_argument("--force", action="store_true", help="Overwrite templates if they exist.")
    args = parser.parse_args()

    # This script is intended to live in Karma/tools/scaffold.py
    script_path = Path(__file__).resolve()
    karma_root = script_path.parents[1]  # .../Karma
    if karma_root.name.lower() != "karma":
        raise RuntimeError(f"Expected to be inside a `Karma/` directory. Found: {karma_root}")

    # 1) Directories
    rel_dirs = [
        "data/raw",
        "data/derived/graph",
        "data/derived/features",
        "data/derived/candidates",
        "docs",
        "configs",
        "prompts",
        "schemas",
        "src/app/api",
        "src/app/core",
        "src/app/services",
        "src/app/utils",
        "src/pipeline/ocel",
        "src/pipeline/kg",
        "src/pipeline/features",
        "src/pipeline/detectors",
        "src/pipeline/scoring",
        "src/pipeline/registry",
        "frontend/src/pages",
        "frontend/src/components",
        "frontend/src/api",
        "frontend/src/state",
        "tests",
        "tools",
    ]
    ensure_dirs(karma_root, rel_dirs)

    # 2) Minimal Python package markers
    for pkg in [
        "src",
        "src/app",
        "src/app/api",
        "src/app/core",
        "src/app/services",
        "src/app/utils",
        "src/pipeline",
        "src/pipeline/ocel",
        "src/pipeline/kg",
        "src/pipeline/features",
        "src/pipeline/detectors",
        "src/pipeline/scoring",
        "src/pipeline/registry",
    ]:
        touch_if_missing(karma_root / pkg / "__init__.py")

    # 3) Template files (optional)
    if args.with_templates:
        write_template(karma_root / "docs" / "SPEC.md", SPEC_MD, force=args.force)
        write_template(karma_root / "configs" / "pipeline.yaml", PIPELINE_YAML, force=args.force)
        write_template(karma_root / "configs" / "llm.yaml", LLM_YAML, force=args.force)
        write_template(karma_root / "configs" / "schema.yaml", SCHEMA_YAML, force=args.force)
        write_template(karma_root / "prompts" / "verify_rule.jinja", VERIFY_PROMPT, force=args.force)
        write_template(karma_root / "prompts" / "explain_case.jinja", EXPLAIN_PROMPT, force=args.force)
        write_template(karma_root / "schemas" / "llm_verify.schema.json", VERIFY_SCHEMA, force=args.force)
        write_template(karma_root / "schemas" / "llm_explain.schema.json", EXPLAIN_SCHEMA, force=args.force)

    print("✅ Scaffold complete under:", karma_root)
    if args.with_templates:
        print("✅ Templates written (use --force to overwrite).")
    else:
        print("ℹ️  Templates not written. Run with --with-templates if you want starter files.")


if __name__ == "__main__":
    main()
