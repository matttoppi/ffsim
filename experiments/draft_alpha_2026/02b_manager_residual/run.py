#!/usr/bin/env python3
import importlib.util
from pathlib import Path

BASE = Path(__file__).parents[1] / "02_manager_personalization/run.py"
spec = importlib.util.spec_from_file_location("manager_personalization", BASE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.POPULATION_CORRECTED = True
module.OUTPUT_PATH = Path(__file__).with_name("result.json")
module.main()
