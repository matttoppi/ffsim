#!/usr/bin/env python3
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "2026-08-29_vona_impact_attempt1/run.py"
spec = importlib.util.spec_from_file_location("vona_impact", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.EXPERIMENT = Path(__file__).parent
module.main()
