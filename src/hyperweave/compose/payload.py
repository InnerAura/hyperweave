"""Simple-frame payload builder — the envelope floor for non-resolver frames.

The structural frames (matrix, diagram, receipt) emit ``hw:payload`` from their
own resolvers. The seven lightweight frames (badge, strip, icon, divider,
marquee, chart, stats) have no resolver-emitted payload, so this module builds
a compact, re-ingestible one for each at context time.

A payload is content-only (no genome/variant — those ride in ``prov`` and are
recovered there by ``transform``), so ``id = sha256(payload)`` identifies the
DATA, not the skin: the same badge content under two genomes shares a payload
id. The returned ``data`` is the envelope's salience digest; ``markdown`` is the
text-shadow projection (the live-text the document agent leads with).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hyperweave.core.envelope import cdata_safe_json
from hyperweave.core.envelope_tier import EnvelopeTier, resolve_tier

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec, ResolvedArtifact


@dataclass(frozen=True)
class SimplePayload:
    """The envelope inputs for one lightweight frame."""

    payload_json: str
    schema: str
    title: str
    intent: str
    data: dict[str, Any]
    markdown: str


def _json(obj: Any) -> str:
    """Compact, CDATA-safe JSON — byte-stable so the envelope id is stable."""
    return cdata_safe_json(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def _strip_metrics(spec: ComposeSpec) -> list[dict[str, str]]:
    """Parse strip metric (label, value) pairs from slots or the value string.

    Mirrors ``engine._parse_strip_metric_pairs`` but inlined to avoid a
    context→engine import cycle. A bare comma chunk with no ``:`` becomes a
    label-less value so free-text strips still round-trip.
    """
    pairs: list[dict[str, str]] = []
    for slot in spec.slots:
        if slot.zone.startswith("metric") and ":" in slot.value:
            k, v = slot.value.split(":", 1)
            pairs.append({"label": k.strip(), "value": v.strip()})
    if not pairs and spec.value:
        for chunk in spec.value.split(","):
            c = chunk.strip()
            if ":" in c:
                k, v = c.split(":", 1)
                pairs.append({"label": k.strip(), "value": v.strip()})
            elif c:
                pairs.append({"label": "", "value": c})
    return pairs


def _metric_md(metrics: list[dict[str, str]]) -> str:
    """Render metric pairs as an interpunct-joined live-text run."""
    parts = [f"{m['label']}: {m['value']}" if m["label"] else m["value"] for m in metrics]
    return " · ".join(p for p in parts if p)


def build_simple_payload(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,  # reserved for future resolver-derived fields
    ctx: dict[str, Any],
) -> SimplePayload | None:
    """Build the compact payload for a lightweight frame, or ``None`` if the
    frame type carries its own resolver payload (matrix/diagram/receipt)."""
    ft = str(spec.type)
    intent = str(ctx.get("reasoning_intent") or "") or f"{ft} artifact"
    title = spec.title or ft

    if ft == "badge":
        content: dict[str, Any] = {"title": spec.title, "value": spec.value, "state": spec.state}
        if spec.glyph:
            content["glyph"] = spec.glyph
        data: dict[str, Any] = {"value": spec.value} if spec.value else {}
        md = " ".join(p for p in (f"**{spec.title}**" if spec.title else "", spec.value) if p) or f"badge: {spec.title}"
        title = spec.title or "badge"
    elif ft == "strip":
        metrics = _strip_metrics(spec)
        content = {"title": spec.title, "metrics": metrics}
        data = {"metrics_total": len(metrics)}
        if metrics:
            data["metrics"] = metrics[:8]
        head = f"**{spec.title}** " if spec.title else ""
        md = (head + _metric_md(metrics)).strip() or (spec.title or "strip")
        title = spec.title or "strip"
    elif ft == "icon":
        content = {"glyph": spec.glyph}
        shape = str(ctx.get("icon_variant") or "")
        if shape:
            content["shape"] = shape
        data = {"glyph": spec.glyph} if spec.glyph else {}
        md = f"icon: {spec.glyph}" if spec.glyph else "icon"
        title = spec.glyph or "icon"
    elif ft == "divider":
        content = {"variant": str(spec.divider_variant)}
        if spec.pair:
            content["pair"] = spec.pair
        data = {"variant": str(spec.divider_variant)}
        md = f"divider: {spec.divider_variant}"
        title = str(spec.divider_variant) or "divider"
    elif ft == "marquee":
        items = [
            str(it.get("text", "")).strip()
            for it in (ctx.get("scroll_items") or [])
            if isinstance(it, dict) and str(it.get("text", "")).strip()
        ]
        content = {"items": items, "direction": spec.marquee_direction}
        data = {"items_total": len(items)}
        if items:
            data["items"] = items[:12]
        md = " · ".join(items) if items else (spec.title or "marquee")
        title = spec.title or "marquee"
    elif ft == "chart":
        repo = str(ctx.get("chart_repo") or "")
        if not repo and spec.chart_repo:
            repo = f"{spec.chart_owner}/{spec.chart_repo}" if spec.chart_owner else spec.chart_repo
        current = str(ctx.get("chart_current_stars") or "")
        points_total = len(ctx.get("chart_markers") or [])
        content = {"repo": repo, "current": current}
        data = {"current": current, "points_total": points_total}
        chart_title = str(ctx.get("chart_title") or "STAR HISTORY")
        md = f"**{chart_title}** {repo} — {current} stars".strip()
        title = repo or chart_title
    elif ft == "stats":
        username = str(ctx.get("stats_username") or spec.stats_username or "")
        fields = (
            ("stars", "stars_display"),
            ("commits", "commits_display"),
            ("prs", "prs_display"),
            ("issues", "issues_display"),
            ("contrib", "contrib_display"),
            ("streak", "streak_display"),
        )
        metric_map = {k: str(ctx.get(src) or "") for k, src in fields}
        metric_map = {k: v for k, v in metric_map.items() if v and v != "—"}
        content = {"username": username, **metric_map}
        data = dict(metric_map)
        body = " · ".join(f"{k}: {v}" for k, v in metric_map.items())
        md = (f"**{username}** — {body}" if body else f"**{username}**").strip() if username else "stats"
        title = username or "stats"
    else:
        return None

    # Tier gates the envelope DIGEST depth, never the payload (the payload is
    # always the full re-ingestible seed). A MINIMAL frame drops the sampled
    # list entries (metrics[:8], items[:12]) and keeps only scalars + totals.
    tier = resolve_tier(ft, str(ctx.get("metadata_depth") or ""))
    if tier is EnvelopeTier.MINIMAL:
        data = {k: v for k, v in data.items() if not isinstance(v, list)}

    return SimplePayload(
        payload_json=_json(content),
        schema=f"{ft}/1",
        title=title,
        intent=intent,
        data=data,
        markdown=md,
    )
