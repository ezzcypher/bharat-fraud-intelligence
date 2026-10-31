"""Formula catalogue: every entry runs on its example; existing formulas equal the source implementation; edge cases."""
import math

import numpy as np
import pytest
from scipy import stats
from sklearn.metrics import matthews_corrcoef

from bfi9 import formulas as FX
from bfi9 import phase8

REQUIRED = {"id", "category", "name", "origin", "source", "problem", "why", "latex", "symbols", "inputs", "run", "code", "dashboard", "limitations", "interview"}


@pytest.mark.parametrize("f", FX.CATALOGUE, ids=[f["id"] for f in FX.CATALOGUE])
def test_entry_complete_and_runs(f):
    assert REQUIRED <= set(f) and f["origin"] in ("existing", "historical", "new") and f["category"] in FX.CATEGORIES
    f["run"](**f["inputs"])


def test_existing_metrics_equal_phase7_on_project_counts():
    m = phase8.evaluation("test")["metrics"]
    me = phase8.p7()["metrics_engine"].classification_metrics({k: m[k] for k in ("TP", "FP", "TN", "FN")})
    for f in FX.CATALOGUE:
        if f["category"] == "Evaluation Metrics" and f["origin"] == "existing" and f["id"] in me:
            assert f["run"](**{k: m[k] for k in ("TP", "FP", "TN", "FN")}) == me[f["id"]]


def test_new_metrics_against_references():
    m = phase8.evaluation("test")["metrics"]
    assert FX.fdr(m["TP"], m["FP"]) == pytest.approx(1 - m["precision"])
    y = np.array([1] * 30 + [0] * 20 + [0] * 940 + [1] * 10); p = np.array([1] * 30 + [1] * 20 + [0] * 940 + [0] * 10)
    assert FX.mcc(30, 20, 940, 10) == pytest.approx(matthews_corrcoef(y, p))
    assert math.isnan(FX.mcc(0, 0, 10, 0)) and math.isnan(FX.fdr(0, 0))
    lo, hi = FX.t_ci_mean([2, 4, 9])
    ref = stats.t.interval(0.95, 2, loc=5, scale=stats.sem([2, 4, 9]))
    assert (lo, hi) == pytest.approx(ref)


def test_cost_and_bayes_match_phase7():
    p7 = phase8.p7()
    cfg = p7["config"].CostConfig("t", c_fp=5, c_fn=100, c_review=2)
    f = {x["id"]: x for x in FX.CATALOGUE}
    assert f["total_cost"]["run"](1713, 1782, 1500, 5, 100, 2) == p7["cost_engine"].simple_total_cost(1713, 1782, 1500, cfg) == 165_900
    assert f["bayes_threshold"]["run"](5, 100, 2) == pytest.approx(p7["cost_engine"].bayes_threshold(cfg))
    assert f["implied_ratio"]["run"](0.12379763346033115) == pytest.approx(p7["cost_engine"].implied_fn_fp_ratio(0.12379763346033115))


def test_bayes_equals_precision():
    m = phase8.evaluation("test")["metrics"]
    f = next(x for x in FX.CATALOGUE if x["id"] == "bayes")
    assert f["run"](m["recall"], m["fpr"], m["prevalence"]) == pytest.approx(m["precision"])


def test_export_records_json_safe():
    import json
    assert json.dumps(FX.export_records()) and all("run" not in r for r in FX.export_records())
