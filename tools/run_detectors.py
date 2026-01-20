from __future__ import annotations

import argparse
import os
import sqlite3
import sys

import yaml

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from src.pipeline.detectors.duplicate_payment import run as run_duplicate_payment
from src.pipeline.detectors.lengthy_approval import run as run_lengthy_approval
from src.pipeline.detectors.maverick_buying import run as run_maverick_buying
from src.pipeline.ocel.derived_event_object import create_derived_event_object
from src.pipeline.scoring.base_confidence import score_candidates


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCEL detectors.")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")
    parser.add_argument(
        "--config",
        default="configs/pipeline.yaml",
        help="Path to pipeline config",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    conn = sqlite3.connect(args.db)
    try:
        create_derived_event_object(conn)
        detectors = [
            ("duplicate_payment", run_duplicate_payment),
            ("lengthy_approval", run_lengthy_approval),
            ("maverick_buying", run_maverick_buying),
        ]
        for name, runner in detectors:
            candidates = runner(conn, config)
            score_candidates(candidates, config)
            print(f"[{name}] scored candidates: {len(candidates)}")
            for cand in candidates[:5]:
                features = cand.get("features", {})
                anchor = f"{cand['anchor_object_id']} ({cand['anchor_object_type']})"
                reason = features.get("maverick_reason")
                reason_str = f", reason={reason}" if reason else ""
                print(
                    f"  - {cand['candidate_id']} | {cand['type']} | {anchor} | "
                    f"base_conf={cand['base_conf']:.4f}{reason_str}"
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
