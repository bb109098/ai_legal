"""Shared test configuration: put the three engine directories on sys.path exactly the way
run_scrutiny_pipeline.py does, and provide a loader for the pre-fix (baseline) modules so
regression tests can prove benchmark behaviour is unchanged."""
import os
import sys
import subprocess
import importlib.util
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in [os.path.join(ROOT, "engines", "engine_c"), os.path.join(ROOT, "engines", "engine_b"),
          os.path.join(ROOT, "engines", "engine_a"), os.path.join(ROOT, "data"), ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Commit the fixes were developed against (pre-fix behaviour reference).
BASELINE_COMMIT = os.environ.get("AI_LEGAL_BASELINE_COMMIT", "a8f583b")


def load_baseline_module(rel_path: str, module_name: str):
    """Imports the pre-fix version of a repository file from git, or skips the test."""
    try:
        src = subprocess.run(["git", "-C", ROOT, "show", f"{BASELINE_COMMIT}:{rel_path}"],
                             check=True, capture_output=True).stdout
    except Exception:
        pytest.skip(f"baseline {BASELINE_COMMIT}:{rel_path} unavailable (no git history)")
    tmp_dir = tempfile.mkdtemp(prefix="ai_legal_baseline_")
    path = os.path.join(tmp_dir, f"{module_name}.py")
    with open(path, "wb") as fh:
        fh.write(src)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def benchmark_extractions():
    import json
    with open(os.path.join(ROOT, "data", "batch_audit_results.json"), encoding="utf-8") as fh:
        return json.load(fh)
