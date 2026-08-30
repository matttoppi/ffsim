#!/usr/bin/env python3
import importlib.util
from pathlib import Path

BASE = Path(__file__).parents[1] / "05_pooled_exact_survival/run.py"
spec = importlib.util.spec_from_file_location("pooled_exact_survival", BASE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.KEY_LENGTH = 4
module.EXPERIMENT = "position-aware exact rank-gap-round survival"
module.POOLING_LIMITATION = (
    "scoring format, team count, and manager identity are intentionally pooled"
)
module.OUTPUT_PATH = Path(__file__).with_name("result.json")
module.main()
