"""Test setup: make the Phase 9 package importable. The sandbox-only Phase 5 hash override is applied ONLY when
BFI_DEV_P5_SHA is set (never in Colab), so the Colab run verifies the real Phase 5 release."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if os.environ.get("BFI_DEV_P5_SHA"):
    from bfi9 import phase8
    phase8.load().settings.EXPECTED_SHA["BFI_v2_Phase5_Explainability.zip"] = os.environ["BFI_DEV_P5_SHA"]

REAL = os.environ.get("BFI_ROOT", "/content") == "/content"  # True only in the real Colab runtime

# Public CI (BFI_PUBLIC_CI=1 in .github/workflows/tests.yml): the tests listed in requires_licensed_artifacts.txt need the
# licensed IEEE-CIS data and the private frozen-model bundle, which are not redistributed. They are DESELECTED, not
# skipped or edited: pytest prints "N deselected", and package_meta/CI_DESELECTED_TESTS.csv records why each one is listed.
LICENSED_ONLY = Path(__file__).with_name("requires_licensed_artifacts.txt")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("BFI_PUBLIC_CI") != "1":
        return
    listed = {l.strip() for l in LICENSED_ONLY.read_text().splitlines() if l.strip() and not l.startswith("#")}
    drop = [i for i in items if i.nodeid in listed]
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = [i for i in items if i.nodeid not in listed]
