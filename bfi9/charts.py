"""Plotly figures on one light/dark template. Rules: one y-axis, thin marks, legend for >=2 series,
hover on every mark, categorical colours in fixed order, status colours only for risk bands (with labels)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .ui import BAND, STATUS, TOKENS, theme

CAT = {"light": ["#0f8a63", "#2a78d6", "#eb6834", "#6250d6", "#eda100", "#e87ba4"],
       "dark": ["#239e73", "#3987e5", "#d95926", "#9085e9", "#c98500", "#d55181"]}  # validated adjacent pairs, both modes


SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIV = {"light": ["#256abf", "#86b6ef", "#f0efec", "#ef9a9a", "#d03b3b"], "dark": ["#3987e5", "#1c5cab", "#383835", "#a33a3a", "#e66767"]}


def template() -> go.layout.Template:
    t, m = TOKENS[theme()], theme()
    return go.layout.Template(layout=dict(
        paper_bgcolor=t["surface"], plot_bgcolor=t["chart"], font=dict(color=t["text"], size=12, family="Inter, system-ui, sans-serif"),
        colorway=CAT[m], hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["border"], font=dict(color=t["text"])),
        xaxis=dict(gridcolor=t["grid"], zerolinecolor=t["grid"], linecolor=t["border"], tickcolor=t["border"], automargin="height+left+right"),
        yaxis=dict(gridcolor=t["grid"], zerolinecolor=t["grid"], linecolor=t["border"], tickcolor=t["border"], automargin=True),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.0, yanchor="bottom", x=0),
        margin=dict(l=48, r=16, t=72, b=40), title=dict(font=dict(size=14), x=0, xanchor="left", y=0.98, yanchor="top")))


def _fin(fig, title: str, x: str = "", y: str = "", h: int = 320) -> go.Figure:
    fig.update_layout(template=template(), title=title, height=h, xaxis_title=x, yaxis_title=y, bargap=0.15)
    return fig


def score_hist(scores, threshold: float, title="Model score distribution", log_y=True) -> go.Figure:
    fig = go.Figure(go.Histogram(x=scores, xbins=dict(start=0, end=1, size=0.02), marker_color=CAT[theme()][0],
                                 marker_line_width=1, marker_line_color=TOKENS[theme()]["chart"], hovertemplate="score %{x}<br>%{y:,} transactions<extra></extra>"))
    fig.add_vline(x=threshold, line_dash="dash", line_color=TOKENS[theme()]["text"], annotation_text=f"frozen threshold {threshold:.4f}", annotation_position="top")
    fig = _fin(fig, title, "model score (uncalibrated)", "transactions" + (" (log scale)" if log_y else ""))
    if log_y:
        fig.update_yaxes(type="log")
    return fig


def grouped_hist(df: pd.DataFrame, col: str, by: str, title: str, bins=50, x="", log_y=False) -> go.Figure:
    fig = go.Figure()
    for i, (k, g) in enumerate(df.groupby(by)):
        fig.add_trace(go.Histogram(x=g[col], name=f"{by}={k}", nbinsx=bins, histnorm="percent", opacity=.75, marker_color=CAT[theme()][i % len(CAT[theme()])],
                                   hovertemplate=f"{by}={k}<br>%{{x}}<br>%{{y:.2f}}% of group<extra></extra>"))
    fig.update_layout(barmode="overlay")
    fig = _fin(fig, title, x or col, "% of group")
    if log_y:
        fig.update_yaxes(type="log")
    return fig


def curve(x, y, name: str, title: str, xl: str, yl: str, ref=None, ref_name="no-skill") -> go.Figure:
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", name=name, line=dict(width=2, color=CAT[theme()][0]),
                               hovertemplate=f"{xl} %{{x:.3f}}<br>{yl} %{{y:.3f}}<extra></extra>"))
    if ref is not None:
        fig.add_trace(go.Scatter(x=ref[0], y=ref[1], mode="lines", name=ref_name, line=dict(width=1.5, dash="dot", color=TOKENS[theme()]["muted"])))
    fig = _fin(fig, title, xl, yl)
    fig.update_xaxes(range=[0, 1]); fig.update_yaxes(range=[0, 1.02])
    return fig


def confusion(m: dict, title="Confusion matrix (frozen threshold)") -> go.Figure:
    z = np.array([[m["TN"], m["FP"]], [m["FN"], m["TP"]]])
    lz = np.log10(z + 1)
    fig = go.Figure(go.Heatmap(z=lz, x=["no alert", "alert"], y=["label 0", "label 1"], colorscale=[[0, SEQ[1]], [1, SEQ[5]]], showscale=False,
                               customdata=z, hovertemplate="%{y} / %{x}<br>%{customdata:,} transactions<extra></extra>"))
    names = [["TN", "FP"], ["FN", "TP"]]
    for i in range(2):
        for j in range(2):  # text colour flips with cell darkness so labels stay readable in both themes
            dark = lz[i, j] > (lz.min() + lz.max()) / 2
            fig.add_annotation(x=j, y=i, text=f"<b>{names[i][j]}</b><br>{z[i, j]:,}", showarrow=False, font=dict(color="#ffffff" if dark else "#0d366b", size=13))
    return _fin(fig, title, "model decision", "evaluation label", 300)


def band_bar(counts: pd.Series, title="Transactions by risk band") -> go.Figure:
    order = [b for b in BAND if b in counts.index]
    fig = go.Figure(go.Bar(x=[f"{BAND[b][1]} {b}" for b in order], y=[counts[b] for b in order], marker_color=[STATUS[BAND[b][0]] for b in order],
                           text=[f"{counts[b]:,}" for b in order], textposition="outside", hovertemplate="%{x}<br>%{y:,} transactions<extra></extra>"))
    return _fin(fig, title, "risk band (provisional, Phase 5)", "transactions")


def hbar(labels, values, title: str, xl: str, color=None, text_fmt="{:,.3f}", h=None) -> go.Figure:
    fig = go.Figure(go.Bar(y=list(labels)[::-1], x=list(values)[::-1], orientation="h", marker_color=color or CAT[theme()][0],
                           text=[text_fmt.format(v) for v in list(values)[::-1]], textposition=["inside" if float(v) >= 0.6 * max([float(x) for x in values] + [0]) > 0 else "outside" for v in list(values)[::-1]],
                           insidetextanchor="end", insidetextfont=dict(color="#ffffff"), hovertemplate="%{y}<br>%{x:,.4f}<extra></extra>"))
    fig = _fin(fig, title, xl, "", h or max(280, 24 * len(labels) + 80))
    vmax = max([float(v) for v in values] + [0])
    return fig.update_xaxes(range=[0, vmax * 1.18 or 1]).update_traces(cliponaxis=False)  # headroom for outside labels


def contributions(df: pd.DataFrame, title="Feature contributions (log-odds)") -> go.Figure:
    """Diverging bars: positive pushes the score up (red pole), negative down (blue pole)."""
    d = df.sort_values("contribution")
    col = [DIV[theme()][-1] if v > 0 else DIV[theme()][0] for v in d["contribution"]]
    fig = go.Figure(go.Bar(y=d["feature"], x=d["contribution"], orientation="h", marker_color=col, text=[f"{v:+.3f}" for v in d["contribution"]],
                           textposition="outside", hovertemplate="%{y}<br>contribution %{x:+.4f}<extra></extra>"))
    fig = _fin(fig, title, "contribution to model log-odds (not causal)", "", max(280, 26 * len(d) + 80))
    lo, hi = min(float(d["contribution"].min()), 0.0), max(float(d["contribution"].max()), 0.0)
    pad = 0.22 * (hi - lo) or 0.1  # headroom so outside value labels stay inside the plot
    return fig.update_xaxes(range=[lo - pad if lo < 0 else 0, hi + pad]).update_traces(cliponaxis=False)


def bar(x, y, title: str, xl: str, yl: str, color_idx=0, text=True) -> go.Figure:
    fig = go.Figure(go.Bar(x=list(x), y=list(y), marker_color=CAT[theme()][color_idx], text=[f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.3g}" for v in y] if text else None,
                           textposition="outside", cliponaxis=False, hovertemplate="%{x}<br>%{y:,.4g}<extra></extra>"))
    fig = _fin(fig, title, xl, yl)
    if max((len(str(v)) for v in x), default=0) > 10:
        fig.update_xaxes(tickangle=-30)  # labels end at the tick: no right-edge clipping
    vmax = max([float(v) for v in y] + [0])
    return fig.update_yaxes(range=[0, vmax * 1.15 or 1]) if vmax > 0 else fig


def grouped_bar(df: pd.DataFrame, x: str, ys: list[str], title: str, yl: str) -> go.Figure:
    fig = go.Figure([go.Bar(x=df[x], y=df[c], name=c, marker_color=CAT[theme()][i % len(CAT[theme()])], hovertemplate=f"{c}<br>%{{x}}: %{{y:,.4g}}<extra></extra>")
                     for i, c in enumerate(ys)])
    fig.update_layout(barmode="group")
    return _fin(fig, title, x, yl)


def lines(df: pd.DataFrame, x: str, ys: list[str], title: str, yl: str, band=None) -> go.Figure:
    fig = go.Figure()
    if band is not None:  # (lower, upper) uncertainty band
        fig.add_trace(go.Scatter(x=list(df[x]) + list(df[x])[::-1], y=list(band[1]) + list(band[0])[::-1], fill="toself", line=dict(width=0),
                                 fillcolor="rgba(57,135,229,0.15)", name="interval", hoverinfo="skip"))
    for i, c in enumerate(ys):
        fig.add_trace(go.Scatter(x=df[x], y=df[c], mode="lines", name=c, line=dict(width=2, color=CAT[theme()][i % len(CAT[theme()])]),
                                 hovertemplate=f"{c}<br>{x} %{{x}}: %{{y:,.4g}}<extra></extra>"))
    return _fin(fig, title, x, yl)


def heatmap(mat: pd.DataFrame, title: str, diverging=True, zmin=-1, zmax=1, h=None) -> go.Figure:
    cs = [[i / (len(DIV[theme()]) - 1), c] for i, c in enumerate(DIV[theme()])] if diverging else [[0, SEQ[0]], [1, SEQ[5]]]
    fig = go.Figure(go.Heatmap(z=mat.values, x=list(mat.columns), y=list(mat.index), colorscale=cs, zmin=zmin if diverging else None,
                               zmax=zmax if diverging else None, hovertemplate="%{y} × %{x}<br>%{z:.3f}<extra></extra>"))
    return _fin(fig, title, "", "", h or max(320, 22 * len(mat) + 120))


def box(df: pd.DataFrame, col: str, by: str | None, title: str, kind="box") -> go.Figure:
    groups = [(k, g[col]) for k, g in df.groupby(by)] if by else [("all", df[col])]
    T = go.Violin if kind == "violin" else go.Box
    fig = go.Figure([T(y=v, name=str(k), marker_color=CAT[theme()][i % len(CAT[theme()])], line_width=1.5) for i, (k, v) in enumerate(groups)])
    return _fin(fig, title, by or "", col)
