#!/usr/bin/env python3
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "2026-08-29_multi_state_decision_impact_attempt1/run.py"
spec = importlib.util.spec_from_file_location("multi_state_impact", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = Path(__file__).parent
module.ROLLOUTS = 300
module.main()
