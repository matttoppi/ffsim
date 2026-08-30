#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "2026-08-29_multi_state_decision_impact_attempt1/finalize.py"
spec = importlib.util.spec_from_file_location("impact_finalizer", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = Path(__file__).parent
module.main()
conclusion_path = Path(__file__).parent / "conclusion.json"
conclusion = json.loads(conclusion_path.read_text())
conclusion["conclusion"] = (
    "Terminal-first timing and the fixed 10% corrected manager mixture pass "
    "the six-state full 300-rollout cached shadow gate. One-turn route ranking "
    "fails in three of six states and remains diagnostic only."
)
conclusion_path.write_text(
    json.dumps(conclusion, indent=2, sort_keys=True) + "\n"
)
