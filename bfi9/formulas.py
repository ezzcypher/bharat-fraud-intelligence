"""Formula & Solution Explorer catalogue (sections A-K per formula).

origin:
  existing   -> implemented in Phase 4-8 code; `run` CALLS that implementation through the Phase 8 bridge
  historical -> documented in a BFI v1 artefact (report/notebook); reproduced here for teaching, source cited
  new        -> new Phase 9 calculation (implemented in this package)
Educational inputs only feed `run`; nothing here touches the model, threshold or saved results."""
from __future__ import annotations

import json
import math

import numpy as np
from scipy import stats

from . import forecasting, quality

# ------------------------------------------------------------------ new Phase 9 implementations


def fdr(TP: int, FP: int) -> float:
    """False discovery rate = FP / (TP + FP) = 1 - precision; NaN when nothing is flagged."""
    return FP / (TP + FP) if (TP + FP) else float("nan")


def mcc(TP: int, FP: int, TN: int, FN: int) -> float:
    """Matthews correlation; NaN when any marginal is zero (undefined, not 0)."""
    den = math.sqrt((TP + FP) * (TP + FN) * (TN + FP) * (TN + FN))
    return (TP * TN - FP * FN) / den if den else float("nan")


def t_ci_mean(values, level: float = 0.95) -> tuple[float, float]:
    x = np.asarray(values, float)
    if len(x) < 2:
        return (float("nan"), float("nan"))
    h = stats.t.ppf(0.5 + level / 2, len(x) - 1) * x.std(ddof=1) / math.sqrt(len(x))
    return (x.mean() - h, x.mean() + h)


def simple_return(p0: float, p1: float) -> float:
    if p0 <= 0:
        raise ValueError("previous price must be > 0")
    return p1 / p0 - 1


def log_return(p0: float, p1: float) -> float:
    if p0 <= 0 or p1 <= 0:
        raise ValueError("prices must be > 0")
    return math.log(p1 / p0)


# ------------------------------------------------------------------ bridges to existing code


def _p7():
    from . import phase8
    return phase8.p7()


def _metrics(TP, FP, TN, FN):
    return _p7()["metrics_engine"].classification_metrics({"TP": int(TP), "FP": int(FP), "TN": int(TN), "FN": int(FN)})


def _cost(TP, FP, FN, c_fp, c_fn, c_review):
    p7 = _p7()
    cfg = p7["config"].CostConfig("formula_explorer_example", c_fp=float(c_fp), c_fn=float(c_fn), c_review=float(c_review), status="illustrative")
    return p7["cost_engine"].simple_total_cost(int(TP), int(FP), int(FN), cfg)


def _project(key):
    """Real project value (test split, model A) via Phase 8; None if unavailable."""
    try:
        from . import phase8
        e = phase8.evaluation("test")
        return {**(e.get("metrics") or {}), **(e.get("ranking") or {})}.get(key)
    except Exception:
        return None


CM = {"TP": 30, "FP": 20, "TN": 940, "FN": 10}  # small synthetic example (1,000 transactions, 40 positive labels)


def F(id, category, name, origin, source, problem, why, latex, symbols, inputs, run, code, dashboard, limitations, interview, project=None):
    return dict(id=id, category=category, name=name, origin=origin, source=source, problem=problem, why=why, latex=latex, symbols=symbols,
                inputs=inputs, run=run, code=code, dashboard=dashboard, limitations=limitations, interview=interview, project=project)


CATALOGUE = [
    # ---------------- Data quality
    F("missing_rate", "Data Quality", "Missing-value rate", "new", "bfi9/quality.py kpis(); v1 notebook cell 13 (missingness report)",
      "Find incomplete fields before trusting charts or models.", "Silent gaps bias statistics and model inputs.",
      r"\text{Missing\%}=\frac{\#\text{missing cells}}{n\cdot k}\times100", {"n": "rows", "k": "columns"},
      {"missing": 377134, "n": 550000, "k": 1}, lambda missing, n, k: 100 * missing / (n * k),
      "missing_pct = 100 * df.isna().sum().sum() / df.size  # df.size = rows x columns",
      "EDA & Data Quality KPIs; IEEE profile", "Says how much is missing, not why (structural vs random).",
      "Count missing cells over all cells; then ask whether missingness is structural, like loan_type when has_loan = 0."),
    F("duplicate_rate", "Data Quality", "Duplicate rate", "historical", "v1 notebook cells 8 & 26 ('Duplicate rows: 0')",
      "Repeated records inflate counts and leak between splits.", "Duplicates double-count transactions and evaluation rows.",
      r"\text{Dup\%}=\frac{\#\text{duplicate rows}}{n}\times100", {"n": "rows"}, {"duplicates": 0, "n": 550000},
      lambda duplicates, n: 100 * duplicates / n if n else float("nan"), "dup_pct = 100 * df.duplicated().sum() / len(df)",
      "EDA & Data Quality KPIs", "Exact duplicates only; near-duplicates need key-based rules.", "df.duplicated() flags exact repeats after the first."),
    F("prevalence", "Data Quality", "Fraud-label prevalence", "existing", "Phase 7 metrics_engine.classification_metrics ('prevalence'); v1 Phase 2 report",
      "Measure class imbalance.", "Accuracy looks great when positives are rare; prevalence sets the no-skill AP.",
      r"\pi=\frac{TP+FN}{N}", {"π": "share of positive EVALUATION labels (chargeback-derived), not proven crime"}, dict(CM),
      lambda TP, FP, TN, FN: _metrics(TP, FP, TN, FN)["prevalence"], "m = metrics_engine.classification_metrics(counts); m['prevalence']",
      "Executive Overview KPI", "Label-defined; differs between datasets and periods.", "Prevalence is the base rate; AP of a random ranker equals it.",
      lambda: _project("prevalence")),
    F("zscore", "Data Quality", "Standardization (z-score)", "new", "Teaching only - NOT used by the frozen LightGBM pipeline (Phase 4 config: raw numeric inputs)",
      "Put features on a common scale.", "Distance-based models are dominated by large-unit features without it.",
      r"z=\frac{x-\mu}{\sigma}", {"μ": "mean", "σ": "standard deviation"}, {"x": 250.0, "mu": 120.0, "sigma": 60.0},
      lambda x, mu, sigma: (x - mu) / sigma if sigma else float("nan"), "z = (x - x.mean()) / x.std()  # fit mean/std on TRAINING data only",
      "Formula Explorer only", "Trees don't need it; fitting μ, σ on all data leaks test information.", "Standardize with training statistics only; trees are scale-invariant."),
    F("iqr_outlier", "Data Quality", "IQR outlier rule", "historical", "v1 notebook Step 10; bfi9/quality.outliers()",
      "Flag extreme values.", "Extreme amounts can distort means and models.", r"x<Q_1-1.5\,IQR\ \lor\ x>Q_3+1.5\,IQR,\quad IQR=Q_3-Q_1",
      {"Q1, Q3": "25th/75th percentiles"}, {"x": 10000.0, "q1": 763.04, "q3": 8557.5},
      lambda x, q1, q3: {"lower": q1 - 1.5 * (q3 - q1), "upper": q3 + 1.5 * (q3 - q1), "outlier": bool(x < q1 - 1.5 * (q3 - q1) or x > q3 + 1.5 * (q3 - q1))},
      "q1, q3 = s.quantile([.25, .75]); iqr = q3 - q1\nis_out = (s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)", "EDA outlier table",
      "Skewed data flags many 'outliers'; bounds from all rows leak future data.", "IQR is robust to the extremes it is detecting, unlike mean ± 3σ."),
    # ---------------- Classification
    F("threshold_rule", "Classification", "Score → decision", "existing", "Phase 4 BFI_v2_model_config.json threshold; Phase 8 data_access.predictions()",
      "Turn a score into an alert.", "A score alone does not tell an analyst what to do.", r"\hat y_i=\mathbb 1[s_i\ge t]",
      {"s": "uncalibrated model score", "t": "frozen threshold (read from Phase 4 config)"}, {"score": 0.2, "threshold": 0.12379763346033115},
      lambda score, threshold: "ALERT (review)" if score >= threshold else "no alert", "decision = np.where(score >= t, 'ALERT (review)', 'no alert')",
      "every page (decision column)", "Raising t cuts FP and raises FN; t must not be re-tuned on the spent test set.",
      "The inclusive rule s ≥ t; the threshold controls alert volume, not truth."),
    F("risk_band", "Risk Bands", "Risk-band mapping", "existing", "Phase 5 risk_band_config.json; bfi_phase5.risk_band (lower bound inclusive)",
      "Prioritise alerts.", "Four bands are easier to triage than raw scores.", r"\text{band}(s)=\max\{b_j: s\ge \text{min}_j\}",
      {"min_j": "band lower bounds: 0, t/2, t, 0.5"}, {"score": 0.3, "threshold": 0.12379763346033115},
      lambda score, threshold: "Critical" if score >= .5 else "High" if score >= threshold else "Medium" if score >= threshold / 2 else "Low",
      "band = bfi_phase5.risk_band(score, band_config)", "Risk bands chart; investigation", "PROVISIONAL; bands are not probabilities.",
      "Bands are ordinal score ranges for triage, not calibrated risk levels."),
    # ---------------- Evaluation
    *[F(k, "Evaluation Metrics", nm, "existing", "Phase 7 metrics_engine.classification_metrics", pb, wy, lx, sy, dict(CM),
        (lambda key: (lambda TP, FP, TN, FN: _metrics(TP, FP, TN, FN)[key]))(k), f"m = metrics_engine.classification_metrics(counts); m['{k}']",
        "Model Performance table; Overview KPIs", lim, iv, (lambda key: (lambda: _project(key)))(k))
      for k, nm, pb, wy, lx, sy, lim, iv in [
          ("precision", "Precision", "How many alerts carry a positive label?", "Review effort is wasted on false alerts.", r"\frac{TP}{TP+FP}", {"TP": "alert ∧ label 1", "FP": "alert ∧ label 0"},
           "Undefined (NaN) with no alerts; depends on prevalence.", "Of what we flagged, how much was right."),
          ("recall", "Recall (TPR)", "How many positive labels were caught?", "Missed fraud is the costliest error.", r"\frac{TP}{TP+FN}", {"FN": "no alert ∧ label 1"},
           "Ignores false alerts; trivially 1 if everything is flagged.", "Of the positives, how many we caught."),
          ("specificity", "Specificity (TNR)", "How many negatives were left alone?", "Customer friction comes from flagged legitimate payments.", r"\frac{TN}{TN+FP}", {"TN": "no alert ∧ label 0"},
           "Near 1 whenever negatives dominate.", "Share of legitimate transactions not flagged."),
          ("f1", "F1 score", "One number balancing precision and recall.", "Optimising one alone is easy and useless.", r"2\frac{PR}{P+R}", {"P": "precision", "R": "recall"},
           "Ignores TN and costs; equal weights may not match the business.", "Harmonic mean punishes imbalance between P and R."),
          ("accuracy", "Accuracy", "Share of correct decisions.", "Shows why it misleads under imbalance.", r"\frac{TP+TN}{N}", {"N": "all transactions"},
           "A never-alert model scores 1 − π.", "With 3.5% positives, 96.5% accuracy is free."),
          ("balanced_accuracy", "Balanced accuracy", "Accuracy that weights both classes equally.", "Removes the majority-class illusion.", r"\frac{TPR+TNR}{2}", {},
           "Ignores precision.", "Average of recall and specificity."),
          ("fpr", "False-positive rate", "Share of negatives wrongly flagged.", "Drives customer friction and ROC.", r"\frac{FP}{FP+TN}", {}, "Small FPR can still mean many FPs.", "1 − specificity."),
          ("fnr", "False-negative rate", "Share of positives missed.", "Missed-fraud exposure.", r"\frac{FN}{FN+TP}", {}, "Label-defined misses only.", "1 − recall.")]],
    F("fdr", "Evaluation Metrics", "False discovery rate", "new", "bfi9/formulas.fdr (= 1 − Phase 7 precision; tested)",
      "Share of alerts that are false.", "Tells reviewers how much of their queue is noise.", r"FDR=\frac{FP}{TP+FP}=1-\text{Precision}", {}, {"TP": 30, "FP": 20},
      fdr, "fdr = FP / (TP + FP) if (TP + FP) else float('nan')", "Formula Explorer; Model Performance", "Undefined with no alerts.", "FDR is the complement of precision.",
      lambda: (1 - _project("precision")) if _project("precision") is not None else None),
    F("mcc", "Evaluation Metrics", "Matthews correlation coefficient", "new", "bfi9/formulas.mcc", "One balanced score using all four cells.",
      "Robust summary for imbalanced binary problems.", r"\frac{TP\,TN-FP\,FN}{\sqrt{(TP+FP)(TP+FN)(TN+FP)(TN+FN)}}", {"range": "−1 … 1; 0 = no better than chance"},
      dict(CM), mcc, "den = sqrt((TP+FP)*(TP+FN)*(TN+FP)*(TN+FN)); mcc = (TP*TN - FP*FN)/den if den else nan",
      "Formula Explorer", "Zero marginals make it undefined (NaN, not 0).", "A correlation between predictions and labels; 0 means chance-level."),
    F("average_precision", "Evaluation Metrics", "Average precision", "existing", "Phase 7 metrics_engine.ranking_metrics (sklearn average_precision_score)",
      "Rank quality when positives are rare.", "Threshold-free summary focused on the positive class.", r"AP=\sum_k (R_k-R_{k-1})P_k", {"P_k, R_k": "precision/recall at the k-th threshold"},
      {"prevalence": 0.0348}, lambda prevalence: {"no_skill_AP": prevalence}, "ap = metrics_engine.ranking_metrics(y, s)['average_precision']",
      "Overview KPI; PR curve", "Step-wise (no interpolation); depends on prevalence.", "Area under the step PR curve; compare to π.", lambda: _project("average_precision")),
    F("roc_auc", "Evaluation Metrics", "ROC-AUC", "existing", "Phase 7 metrics_engine.ranking_metrics (sklearn roc_auc_score)",
      "Ranking discrimination.", "Threshold-free view of separation.", r"AUC=P(s_+>s_-)", {}, {"pairs_correct": 905, "pairs_total": 1000},
      lambda pairs_correct, pairs_total: pairs_correct / pairs_total, "auc = metrics_engine.ranking_metrics(y, s)['roc_auc']", "ROC curve; Overview",
      "Not calibration, not profit; can look high when precision is low.", "Chance a random positive outranks a random negative.", lambda: _project("roc_auc")),
    F("wilson", "Statistics & Probability", "Wilson interval (proportion)", "existing", "Phase 7 metrics_engine.wilson_interval",
      "Uncertainty for a rate.", "A normal interval misbehaves near 0/1 and small n.", r"\frac{\hat p+\frac{z^2}{2n}\pm z\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}}{1+\frac{z^2}{n}}",
      {"z": "1.96 for 95%"}, {"k": 1713, "n": 3495}, lambda k, n: _p7()["metrics_engine"].wilson_interval(int(k), int(n)), "lo, hi = metrics_engine.wilson_interval(k, n, 0.95)",
      "Model Performance (wilson_95)", "Assumes independent rows; clustered fraud makes it too narrow.", "Score interval that stays inside [0,1] and works for small n."),
    F("brier", "Statistics & Probability", "Brier score", "existing", "Phase 7 metrics_engine.brier_score", "Probability-style error of scores.",
      "Mixes calibration and discrimination.", r"\frac1n\sum (s_i-y_i)^2", {}, {"s": 0.8, "y": 1}, lambda s, y: (s - y) ** 2, "metrics_engine.brier_score(y, s)",
      "Model Performance calibration note", "Low Brier does not prove calibration.", "Mean squared error of the score against the 0/1 label."),
    # ---------------- Costs
    F("total_cost", "Costs & Decisions", "Total illustrative cost (Phase 7)", "existing", "Phase 7 cost_engine.simple_total_cost / cost_from_outcomes",
      "Translate errors into an assumed cost.", "Metrics ignore that misses and false alerts cost different amounts.",
      r"C=FP\,C_{FP}+FN\,C_{FN}+(TP+FP)\,C_{rev}+TP\,C_{int}", {"C_FP": "friction per false alert (excl. review)", "C_FN": "loss per missed fraud", "C_rev": "per review"},
      {"TP": 1713, "FP": 1782, "FN": 1500, "c_fp": 5.0, "c_fn": 100.0, "c_review": 2.0}, _cost,
      "cost_engine.simple_total_cost(TP, FP, FN, CostConfig(name, c_fp=5, c_fn=100, c_review=2))", "Cost & Decision Simulator",
      "Illustrative units (CU), not money; assumes every alert reviewed.", "Weighted error count; the weights are business assumptions."),
    F("break_even", "Costs & Decisions", "Break-even missed-fraud cost", "existing", "Phase 7 sensitivity_analysis.break_even_fn_cost",
      "When is screening worth it?", "Shows how high C_FN must be before alerts pay for themselves.", r"C_{FN}^*=\frac{A}{\text{caught}}", {"A": "all non-FN costs"},
      {"other_costs": 15900.0, "caught": 1713}, lambda other_costs, caught: other_costs / caught if caught else float("nan"),
      "cost_adapter.break_even('illustrative_baseline')", "Cost simulator", "Depends on the other assumed costs.", "Cost per caught fraud at which screening breaks even."),
    F("bayes_threshold", "Costs & Decisions", "Expected-cost (Bayes) threshold", "existing", "Phase 7 cost_engine.bayes_threshold",
      "Cost-optimal cut-off IF scores were calibrated.", "Links costs to a threshold.", r"p^*=\frac{C_{rev}+C_{FP}}{C_{FN}+C_{FP}-C_{int}}", {},
      {"c_fp": 5.0, "c_fn": 100.0, "c_review": 2.0}, lambda c_fp, c_fn, c_review: (c_review + c_fp) / (c_fn + c_fp),
      "cost_engine.bayes_threshold(cfg)", "Cost simulator note", "Invalid without calibration (not established).", "Flag when expected loss of passing exceeds expected cost of acting."),
    F("implied_ratio", "Costs & Decisions", "Implied C_FN / C_FP", "existing", "Phase 7 cost_engine.implied_fn_fp_ratio", "What cost ratio does the frozen threshold imply?",
      "Makes the hidden assumption explicit.", r"r=\frac1t-1", {}, {"threshold": 0.12379763346033115}, lambda threshold: 1 / threshold - 1,
      "cost_engine.implied_fn_fp_ratio(t)", "Cost simulator", "Assumes calibration and no review cost.", "Threshold t is optimal when C_FN/C_FP = 1/t − 1."),
    # ---------------- Statistics
    F("mean_var", "Statistics & Probability", "Mean, sample variance, std", "existing", "Phase 8 stats_teaching.describe (ddof=1)",
      "Summarise a numeric field.", "Centre and spread drive every comparison.", r"\bar x=\tfrac1n\sum x_i,\ s^2=\tfrac1{n-1}\sum(x_i-\bar x)^2", {"n−1": "Bessel's correction"},
      {"a": 2.0, "b": 4.0, "c": 9.0}, lambda a, b, c: {"mean": np.mean([a, b, c]), "var": np.var([a, b, c], ddof=1), "std": np.std([a, b, c], ddof=1)},
      "stats_teaching.describe(values)", "Score statistics", "Skewed scores: median is more typical than the mean.", "n−1 makes the variance unbiased."),
    F("t_ci", "Statistics & Probability", "t confidence interval (mean)", "new", "bfi9/formulas.t_ci_mean", "Uncertainty of a mean.", "A point estimate hides sampling error.",
      r"\bar x\pm t_{1-\alpha/2,n-1}\frac{s}{\sqrt n}", {}, {"a": 2.0, "b": 4.0, "c": 9.0}, lambda a, b, c: t_ci_mean([a, b, c]),
      "t_ci_mean(values, 0.95)", "Formula Explorer", "Independence assumed; prefer cluster bootstrap for transactions.", "Mean ± t-quantile × standard error."),
    F("conditional", "Statistics & Probability", "Conditional probability by band", "existing", "Phase 8 stats_teaching.band_table (evaluation mode)",
      "Label rate inside a group.", "Turns counts into group-level rates.", r"P(A\mid B)=\frac{P(A\cap B)}{P(B)}", {}, {"both": 150, "group": 1000},
      lambda both, group: both / group if group else float("nan"), "t['fraud_labels'] / t['transactions']", "Risk analytics (evaluation mode)",
      "Small groups give unstable rates.", "Rate among the group, not among everyone."),
    F("bayes", "Statistics & Probability", "Bayes' theorem (alert)", "existing", "Phase 8 metrics_adapter.bayes_view", "Probability-like reading of an alert.",
      "Shows why rare fraud makes false alerts common.", r"P(F\mid A)=\frac{TPR\,\pi}{TPR\,\pi+FPR(1-\pi)}", {}, {"tpr": 0.533, "fpr": 0.02, "pi": 0.0348},
      lambda tpr, fpr, pi: tpr * pi / (tpr * pi + fpr * (1 - pi)), "metrics_adapter.bayes_view('test')", "Overview / analyst answers",
      "Population-level; not the probability for one live alert.", "Equals precision on the same split (a built-in check)."),
    F("pearson", "Statistics & Probability", "Pearson correlation", "historical", "v1 notebook Step 12 (target correlation); bfi9/quality.correlations",
      "Linear association between two numeric fields.", "Screens redundant or related features.", r"r=\frac{\sum(x-\bar x)(y-\bar y)}{\sqrt{\sum(x-\bar x)^2\sum(y-\bar y)^2}}",
      {"range": "−1 … 1"}, {"x1": 1.0, "x2": 2.0, "x3": 3.0, "y1": 2.0, "y2": 4.1, "y3": 5.9},
      lambda x1, x2, x3, y1, y2, y3: float(np.corrcoef([x1, x2, x3], [y1, y2, y3])[0, 1]), "df[cols].corr(method='pearson')",
      "EDA correlation heatmap", "Linear only; correlation is not causation.", "v1's top |r| with is_fraud was 0.06: almost no linear signal."),
    # ---------------- Explainability
    F("shap_additivity", "Explainability", "TreeSHAP additivity (log-odds)", "existing", "Phase 5 bfi_phase5 (LightGBM pred_contrib); Phase 8 explain()",
      "Split one score into feature contributions.", "Investigators need reasons, not just a number.", r"f(x)=\phi_0+\sum_j\phi_j,\quad s=\sigma(f(x))",
      {"f(x)": "raw log-odds", "φ0": "base value", "σ": "logistic function"}, {"base": -3.2, "sum_contrib": 2.5},
      lambda base, sum_contrib: {"log_odds": base + sum_contrib, "score": 1 / (1 + math.exp(-(base + sum_contrib)))},
      "contrib = booster.predict(X, pred_contrib=True)  # last column = base\nscore = 1/(1+exp(-contrib.sum(axis=1)))", "Investigation; Explainability",
      "Correlated features share credit; not causal; says nothing about availability.", "Contributions add up exactly to the model's log-odds."),
    # ---------------- Historical v1 formulas (all phases)
    F("class_weight", "Classification", "Class-weight ratio (v1 Phase 2)", "historical", "v1 Phase 2 report §11 'Class-weight ratio'; BFI_Phase2_Summary.csv",
      "Counter class imbalance in training.", "Without weighting the learner can ignore rare positives.", r"w=\frac{\#\text{negatives}}{\#\text{positives}}", {},
      {"neg": 545127, "pos": 4873}, lambda neg, pos: neg / pos if pos else float("nan"), "scale_pos_weight = (y == 0).sum() / (y == 1).sum()",
      "Report Comparison", "Reweighting distorts score calibration.", "v1 used ≈111.9:1 as LightGBM scale_pos_weight."),
    F("relative_ap", "Evaluation Metrics", "Relative AP improvement (v1 Phase 2)", "historical", "v1 Phase 2 report §11; summary CSV (≈13.0%)",
      "Compare two models' AP.", "Absolute AP differences look tiny at low prevalence.", r"\frac{AP_{new}-AP_{old}}{AP_{old}}\times100", {},
      {"ap_old": 0.015473, "ap_new": 0.01749}, lambda ap_old, ap_new: quality.pct_change(ap_old, ap_new), "100 * (ap_new - ap_old) / ap_old",
      "Report Comparison", "Not computable from a zero baseline.", "v1 reduced model: +13% relative AP, still near no-skill."),
    F("cyclic_hour", "Data Quality", "Cyclic hour encoding (v1 Phase 3)", "historical", "v1 notebook Step 11 (hour_sin, hour_cos)",
      "Make 23:00 close to 00:00.", "Raw hour treats midnight neighbours as far apart.", r"(\sin\tfrac{2\pi h}{24},\ \cos\tfrac{2\pi h}{24})", {"h": "hour 0–23"},
      {"hour": 23}, lambda hour: {"sin": math.sin(2 * math.pi * hour / 24), "cos": math.cos(2 * math.pi * hour / 24)},
      "df['hour_sin'] = np.sin(2*np.pi*df.transaction_hour/24)", "EDA (cleaned columns)", "Needs both sin and cos to be unambiguous.", "Maps the clock onto a circle."),
    # ---------------- Global intelligence
    F("pct_change", "Global Scam Intelligence", "Percentage change (zero-safe)", "new", "bfi9/quality.pct_change",
      "Change in reported incidents.", "Raw counts hide relative growth.", r"\%\Delta=\frac{N_t-N_{t-1}}{N_{t-1}}\times100", {}, {"prev": 0.0, "curr": 4.0},
      lambda prev, curr: quality.pct_change(prev, curr) if prev else "Not calculable from zero baseline", "pct_change(prev, curr)  # None when prev == 0",
      "Global Threat Trends", "More reports ≠ more fraud (coverage changes).", "Never divide by a zero baseline; say so instead."),
    # ---------------- Market
    F("simple_return", "Stock-Market Impact", "Simple return", "new", "bfi9/formulas.simple_return; intelligence/event_study.py", "Daily price change.",
      "Comparable across price levels.", r"R_t=\frac{P_t}{P_{t-1}}-1", {}, {"p0": 100.0, "p1": 97.0}, simple_return, "r = close.pct_change()",
      "Market Impact", "Adjust for splits/dividends.", "Relative change in price."),
    F("log_return", "Stock-Market Impact", "Log return", "new", "bfi9/formulas.log_return", "Additive multi-day returns.", "Sums over time correctly.",
      r"r_t=\ln\frac{P_t}{P_{t-1}}", {}, {"p0": 100.0, "p1": 97.0}, log_return, "r = np.log(close).diff()", "Market Impact", "Prices must be > 0.", "Log returns add across days."),
    F("abnormal_return", "Stock-Market Impact", "Benchmark-adjusted & market-model abnormal return", "new", "intelligence/event_study.py",
      "Separate a stock's move from the market's.", "A drop on a market-wide down day is not company-specific.",
      r"AR_t=R_{i,t}-(\hat\alpha+\hat\beta R_{m,t})", {"α, β": "OLS on the estimation window"}, {"r_i": -0.05, "r_m": -0.01, "alpha": 0.0, "beta": 1.2},
      lambda r_i, r_m, alpha, beta: r_i - (alpha + beta * r_m), "ar = r_i - (alpha + beta * r_m)", "Market Impact", "Confounding news; not causal.",
      "Residual return after the market explains what it can."),
    F("car", "Stock-Market Impact", "Cumulative abnormal return", "new", "intelligence/event_study.py", "Total abnormal move over an event window.",
      "Single days miss slow reactions.", r"CAR[t_1,t_2]=\sum_{t=t_1}^{t_2}AR_t", {}, {"ar1": -0.01, "ar2": -0.03, "ar3": 0.005},
      lambda ar1, ar2, ar3: ar1 + ar2 + ar3, "car = ar.loc[t1:t2].sum()", "Market Impact", "Window choice matters; association only.", "Sum of abnormal returns over the window."),
    # ---------------- Forecasting / monitoring
    F("seasonal_naive", "Forecasting & Monitoring", "Seasonal-naive (7-day) forecast", "new", "bfi9/forecasting.predict", "Baseline for daily volume.",
      "Any model must beat a simple baseline.", r"\hat y_{T+h}=y_{T+h-7\lceil h/7\rceil}", {}, {"d1": 3000.0, "d2": 3200.0, "d3": 3100.0, "d4": 2900.0, "d5": 3050.0, "d6": 3300.0, "d7": 3400.0},
      lambda d1, d2, d3, d4, d5, d6, d7: list(forecasting.predict(np.array([d1, d2, d3, d4, d5, d6, d7]), "seasonal_naive_7", 7)),
      "forecasting.predict(history, 'seasonal_naive_7', h)", "Forecasting page", "Relative days only; no calendar effects.", "Repeat last week's pattern."),
    F("mae_mape", "Forecasting & Monitoring", "MAE / MAPE", "new", "bfi9/forecasting.backtest", "Forecast error.", "Needed to compare methods honestly.",
      r"MAE=\tfrac1h\sum|y-\hat y|,\ MAPE=\tfrac{100}h\sum\tfrac{|y-\hat y|}{y}", {}, {"y": 3000.0, "yhat": 2850.0},
      lambda y, yhat: {"AE": abs(y - yhat), "APE_pct": 100 * abs(y - yhat) / y if y else float("nan")}, "np.mean(np.abs(err)); np.mean(np.abs(err)/actual)*100",
      "Forecasting backtest table", "MAPE explodes near zero.", "MAE in units; MAPE in percent."),
    F("psi", "Forecasting & Monitoring", "Population Stability Index", "new", "bfi9/forecasting.psi", "Detect score-distribution drift.",
      "Shifts can silently degrade a frozen model.", r"PSI=\sum_b (a_b-e_b)\ln\frac{a_b}{e_b}", {"e, a": "reference / current bin shares"},
      {"e1": 0.5, "e2": 0.5, "a1": 0.6, "a2": 0.4}, lambda e1, e2, a1, a2: (a1 - e1) * math.log(a1 / e1) + (a2 - e2) * math.log(a2 / e2),
      "forecasting.psi(val_scores, test_scores)", "Forecasting › drift readiness", "Rule-of-thumb cut-offs only; bins matter.", "Symmetric KL-style distance between binned distributions."),
]

CATEGORIES = ["Data Quality", "Classification", "Evaluation Metrics", "Costs & Decisions", "Risk Bands", "Statistics & Probability", "Explainability",
              "Global Scam Intelligence", "Stock-Market Impact", "Forecasting & Monitoring"]


def export_records() -> list[dict]:
    """JSON-safe catalogue (callables dropped) for CSV/JSON deliverables and the traceability matrix."""
    return [{k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in f.items() if k not in ("run", "project")} for f in CATALOGUE]
