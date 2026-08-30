#!/usr/bin/env python3
import importlib.util
import os
from pathlib import Path

os.environ["FFSIM_HIERARCHICAL_SURVIVAL_MANIFEST"] = str(
    Path.home()
    / ".cache/ffsim/historical_sleeper/hdvn/"
    "rank20-survival-final-20260829/rank20-survival.manifest.json"
)
SOURCE = Path(__file__).parents[1] / "2026-08-29_alpha_shadow_audit/collect.py"
spec = importlib.util.spec_from_file_location("shadow_collect", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = Path(__file__).parent
module.main()
