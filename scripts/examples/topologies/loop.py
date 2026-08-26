"""The loop family exhibit — every cell the engine can produce.
`loop` is the procedural directed loop: process stations on a spine,
exclusive decisions with guard chips, terminal exits, external taps,
one-level named scopes, and the return rail closing the circuit. Its two
public axes are ORIENTATION (vertical spine + margin rail, the default |
horizontal row + underslung return — one solver, both cells, through the
axis map) and the MOTION REGISTER (`turn` performs the claim in time —
the family default; `drift` is the quiet standing face). Devices are
STRUCTURAL: two decisions make a retry, tap edges make a supervised loop,
a scope node makes the nested cell, `accumulates` on the return makes the
flywheel — never a flag.

Shared skeleton (render/refusal/section/exhibit/scale_of) imported from
``topologies.exhibit`` — never re-copied.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.examples.topologies.exhibit import (  # noqa: E402
    Exhibit,
    exhibit,
    refusal,
    register_elsewhere,
    scale_of,
    section,
)

FAMILY = "loop"
_DIAGRAMS = _REPO / "outputs" / "diagrams"
OUT = _DIAGRAMS / "renders" / "topologies" / FAMILY
SPECIMEN_DIR = _REPO / "v04" / "v040" / "v044" / "loops"

SECTION_DIRS = (
    "why",
    "axis-grid",
    "scenarios",
    "corpus",
    "capabilities",
    "boundaries",
)


def _n(label: str, **kw: Any) -> dict[str, Any]:
    return {"label": label, **kw}


def _e(src: str, dst: str, **kw: Any) -> dict[str, Any]:
    return {"from": src, "to": dst, **kw}


# ── 1 · Specimens (the golden set, recreated) ───────────────────────────

_SPECIMENS: list[tuple[str, str, str]] = [
    # (preset name, specimen path fragment, one-line claim)
    (
        "loop-hillclimb",
        "turn/cycle-turn.svg",
        "The anchor: hill-climb on the drift face — the plain twin.",
    ),
    (
        "loop-hillclimb-turn",
        "turn/cycle-turn-choreography.svg",
        "The same geometry, register flipped: three turns — improve, revert, finish. The one-flag toggle.",
    ),
    (
        "loop-retry",
        "retry/cycle-retry.svg",
        "Bounded dual-exit: succeed, retry through the backoff, or exhaust.",
    ),
    (
        "loop-shuttle",
        "shuttle/cycle-shuttle-v2.svg",
        "The lateral row: draft ⇄ review, approved ships.",
    ),
    (
        "loop-runloop",
        "runloop/cycle-runloop-v2.svg",
        "Endless: one turn forever; the hero holds — the dwell is the thinking.",
    ),
    (
        "loop-flywheel",
        "runloop/cycle-runloop-v1.svg",
        "The accumulator: the return carries the gain, and its second flash holds longer.",
    ),
    (
        "loop-nested",
        "nested/cycle-nested.svg",
        "A loop inside a loop: the scope is the node for port purposes.",
    ),
    (
        "loop-tap",
        "tap/cycle-tap-v3.svg",
        "The supervised runloop: the knock lands only while the loop rests.",
    ),
]


# ── 2 · The axis grid: orientation x register ───────────────────────────


def _grid_spec(orientation: str, register: str) -> dict[str, Any]:
    return {
        "topology": "loop",
        "orientation": orientation,
        "motion_register": register,
        "title": f"Review loop · {orientation} · {register}",
        "nodes": [
            {"id": "draft", "label": "Draft the change"},
            {"id": "check", "label": "Run the checks"},
            {"id": "ok", "label": "Green?", "station": "decision"},
            {
                "id": "ship",
                "label": "Shipped.",
                "station": "terminal",
                "partition": "advance",
            },
        ],
        "edges": [
            _e("draft", "check"),
            _e("check", "ok"),
            _e("ok", "ship", label="yes", label_style="chip"),
            _e(
                "ok",
                "draft",
                label="no · fix it",
                label_style="chip",
                circuit="return",
            ),
        ],
    }


def _axis_grid() -> list[Exhibit]:
    out: list[Exhibit] = []
    for orientation in ("vertical", "horizontal"):
        for register in ("turn", "drift"):
            out.append(
                (
                    f"grid-{orientation}-{register}",
                    f"orientation: {orientation} x motion_register: {register} — one spec, four faces.",
                    _grid_spec(orientation, register),
                )
            )
    return out


# ── 3 · Real scenarios (agent/human work, 2026) ─────────────────────────

_SCENARIOS: list[Exhibit] = [
    (
        "tool-loop",
        "The MCP tool loop every coding agent runs: decide, call, read — until the task is done.",
        {
            "topology": "loop",
            "title": "The agent tool loop",
            "subtitle": "Loop · plan a step, call a tool over MCP, fold the result back into context — exit "
            "when the task completes",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Plan the next step",
                    id="plan",
                    desc="context · goal · budget",
                    role="hero",
                    kind="git-branch",
                ),
                _n(
                    "Call the tool",
                    id="call",
                    desc="mcp · bash · edit",
                    kind="zap",
                ),
                _n(
                    "Read the result",
                    id="read",
                    desc="fold into context",
                    kind="eye",
                ),
                _n("Task complete?", id="done", station="decision"),
                _n(
                    "Report and stop.",
                    id="stop",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("plan", "call"),
                _e("call", "read"),
                _e("read", "done"),
                _e("done", "stop", label="yes", label_style="chip"),
                _e(
                    "done",
                    "plan",
                    label="no · next step",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "prompt-hillclimb",
        "Prompt optimization as a hill-climb: mutate, score against the eval set, keep or revert.",
        {
            "topology": "loop",
            "title": "Prompt hill-climb",
            "subtitle": "Loop · mutate the prompt, score it on the eval set, keep the winner — stop at the "
            "target or the budget",
            "nodes": [
                _n("Mutate the prompt", id="mut"),
                _n("Score on the eval set", id="score"),
                _n("Score improved?", id="better", station="decision"),
                _n("Revert to champion", id="revert", partition="discard"),
                _n("Promote champion", id="keep", partition="advance"),
                _n(
                    "Stop?",
                    id="stop",
                    station="decision",
                    chips=["target hit", "budget spent"],
                ),
                _n(
                    "Ship the champion.",
                    id="ship",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("mut", "score"),
                _e("score", "better"),
                _e("better", "revert", label="no", label_style="chip"),
                _e("better", "keep", label="yes", label_style="chip"),
                _e("revert", "stop"),
                _e("keep", "stop"),
                _e("stop", "ship", label="yes", label_style="chip"),
                _e(
                    "stop",
                    "mut",
                    label="no · mutate again",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "agent-tap",
        "An autonomous agent under supervision: the operator can knock, but only between turns.",
        {
            "topology": "loop",
            "title": "The supervised agent",
            "subtitle": "Loop · the operator can interrupt between turns; every turn emits its trace",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Decide",
                    id="decide",
                    desc="plan the step",
                    role="hero",
                    kind="git-branch",
                ),
                _n("Act", id="act", desc="tools · code", kind="zap"),
                _n("Observe", id="obs", desc="fold results", kind="eye"),
                _n(
                    "Operator",
                    id="op",
                    desc="can interrupt",
                    station="external",
                    kind="user",
                ),
                _n(
                    "Traces",
                    id="tr",
                    desc="every turn",
                    station="external",
                    kind="activity",
                ),
            ],
            "edges": [
                _e("decide", "act"),
                _e("act", "obs"),
                _e(
                    "obs",
                    "decide",
                    label="next turn",
                    label_style="chip",
                    circuit="return",
                ),
                _e(
                    "op",
                    "decide",
                    label="interrupt",
                    label_style="chip",
                    circuit="tap-in",
                ),
                _e(
                    "obs",
                    "tr",
                    label="traces",
                    label_style="chip",
                    circuit="tap-out",
                ),
            ],
        },
    ),
    (
        "k8s-reconcile",
        "The reconcile loop that runs every controller: observe, diff against the declared state, apply, requeue.",
        {
            "topology": "loop",
            "glyph_tint": "brand",
            "title": "The reconcile loop",
            "subtitle": "Loop · a controller observes the cluster, diffs it against the declared state, applies "
            "the delta, and requeues",
            "nodes": [
                _n(
                    "Observe the cluster",
                    id="watch",
                    desc="watch · list · cache",
                    glyph="kubernetes",
                ),
                _n(
                    "Diff declared vs actual",
                    id="diff",
                    desc="terraform-shaped delta",
                    glyph="terraform",
                ),
                _n(
                    "Apply the delta",
                    id="apply",
                    desc="create · patch · delete",
                    glyph="docker",
                ),
            ],
            "edges": [
                _e("watch", "diff"),
                _e("diff", "apply"),
                _e(
                    "apply",
                    "watch",
                    label="requeue",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "failover-retry",
        "Provider failover as the retry device: the primary model retries, then the request fails over.",
        {
            "topology": "loop",
            "glyph_tint": "brand",
            "title": "Model failover",
            "subtitle": "Loop · the primary model retries through a backoff; a spent budget fails the request "
            "over to the fallback",
            "nodes": [
                _n(
                    "Call the primary model",
                    id="call",
                    desc="claude-fable-5",
                    glyph="claude",
                ),
                _n("Answered?", id="ok", station="decision"),
                _n(
                    "Return the answer.",
                    id="good",
                    station="terminal",
                    partition="advance",
                    kind="circle-check",
                ),
                _n("Budget left?", id="budget", station="decision"),
                _n("Back off and rotate keys", id="wait", kind="clock"),
                _n(
                    "Fail over to the fallback.",
                    id="fb",
                    station="terminal",
                    partition="exhausted",
                    glyph="openai",
                ),
            ],
            "edges": [
                _e("call", "ok"),
                _e("ok", "good", label="yes", label_style="chip"),
                _e("ok", "budget", label="no", label_style="chip"),
                _e("budget", "wait", label="yes", label_style="chip"),
                _e("budget", "fb", label="no", label_style="chip"),
                _e(
                    "wait",
                    "call",
                    label="attempt n+1",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "pr-shuttle",
        "The PR exchange on the lateral cell, in its own house brands.",
        {
            "topology": "loop",
            "orientation": "horizontal",
            "glyph_tint": "brand",
            "title": "The pull-request shuttle",
            "subtitle": "Loop · a branch shuttles between pushes and review until the approval merges it",
            "nodes": [
                _n(
                    "Push the branch",
                    id="push",
                    desc="agent commits",
                    glyph="github",
                ),
                _n(
                    "CI + review",
                    id="ci",
                    desc="checks · human read",
                    kind="circle-check",
                ),
                _n("Approve?", id="ok", station="decision"),
                _n(
                    "Merged to main.",
                    id="merged",
                    station="terminal",
                    partition="advance",
                    glyph="github",
                ),
            ],
            "edges": [
                _e("push", "ci"),
                _e("ci", "ok"),
                _e("ok", "merged", label="approved", label_style="chip"),
                _e(
                    "ok",
                    "push",
                    label="changes requested",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "training-flywheel",
        "The fine-tune flywheel: serve, collect preferences, train, redeploy — the checkpoint compounds.",
        {
            "topology": "loop",
            "glyph_tint": "brand",
            "title": "The fine-tune flywheel",
            "subtitle": "Loop · serve the checkpoint, collect preference pairs, train the next one, redeploy —"
            "the model compounds each turn",
            "nodes": [
                _n(
                    "Serve the checkpoint",
                    id="serve",
                    desc="production traffic",
                    glyph="huggingface",
                ),
                _n(
                    "Collect preference pairs",
                    id="collect",
                    desc="accepted · rejected",
                    glyph="duckdb",
                ),
                _n(
                    "Train the next epoch",
                    id="train",
                    desc="dpo · lora",
                    glyph="pytorch",
                ),
            ],
            "edges": [
                _e("serve", "collect"),
                _e("collect", "train"),
                _e(
                    "train",
                    "serve",
                    label="compounds",
                    label_style="chip",
                    circuit="return",
                    accumulates=True,
                ),
            ],
        },
    ),
    (
        "plan-delegate-loop",
        "The orchestrator's nested cell: the planning loop delegates into a complete inner tool loop.",
        {
            "topology": "loop",
            "title": "Plan, delegate, integrate",
            "subtitle": "Loop · the outer plan loop delegates into an inner tool loop that spins until the "
            "answer comes out",
            "node_style": "card+glyph",
            "nodes": [
                _n("Plan the milestone", id="plan"),
                _n("Subagent loop", id="scope", station="scope"),
                _n("Decide", id="i1", enclosure="scope", kind="git-branch"),
                _n("Call", id="i2", enclosure="scope", kind="zap"),
                _n("Read", id="i3", enclosure="scope", kind="eye"),
                _n("Integrate the result", id="integ"),
                _n("Milestones left?", id="more", station="decision"),
                _n(
                    "Done. Hand over.",
                    id="done",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("plan", "scope", label="delegate", label_style="chip"),
                _e("i1", "i2"),
                _e("i2", "i3"),
                _e(
                    "i3",
                    "i1",
                    label="next call",
                    label_style="chip",
                    circuit="return",
                ),
                _e("scope", "integ", label="result", label_style="chip"),
                _e("integ", "more"),
                _e("more", "done", label="no", label_style="chip"),
                _e(
                    "more",
                    "plan",
                    label="yes · next milestone",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "etl-scope",
        "A transform loop nested inside the horizontal row — the scope device on the lateral cell.",
        {
            "topology": "loop",
            "orientation": "horizontal",
            "title": "The ETL relay",
            "subtitle": "Loop · pull a batch, spin the transform loop until the chunk is clean, load it — and pull "
            "the next",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Pull the batch",
                    id="pull",
                    desc="source · cursor",
                    kind="database",
                ),
                _n("Transform loop", id="scope", station="scope"),
                _n(
                    "Map",
                    id="i1",
                    desc="reshape",
                    enclosure="scope",
                    kind="wrench",
                ),
                _n(
                    "Validate",
                    id="i2",
                    desc="schema check",
                    enclosure="scope",
                    kind="circle-check",
                ),
                _n("Load", id="load", desc="warehouse append", kind="upload"),
            ],
            "edges": [
                _e("pull", "scope", label="chunk", label_style="chip"),
                _e("i1", "i2"),
                _e(
                    "i2",
                    "i1",
                    label="next row",
                    label_style="chip",
                    circuit="return",
                ),
                _e("scope", "load", label="clean", label_style="chip"),
                _e(
                    "load",
                    "pull",
                    label="next batch",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "triage-ladder",
        "A four-rung unrolled ladder: the gather bus takes four arms, one more than its citation.",
        {
            "topology": "loop",
            "title": "Support triage, unrolled",
            "subtitle": "Loop · four tiers try in order — any tier can resolve, the last one escalates",
            "node_style": "card+glyph",
            "nodes": [
                _n("Bot answer", id="a1", desc="kb match", kind="zap"),
                _n("L1 agent", id="a2", desc="scripted fixes", kind="wrench"),
                _n("L2 agent", id="a3", desc="deep dive", kind="eye"),
                _n(
                    "Engineer",
                    id="a4",
                    desc="reads the code",
                    kind="git-branch",
                ),
                _n(
                    "Resolved",
                    id="done",
                    desc="ticket closed",
                    station="terminal",
                    partition="advance",
                ),
                _n(
                    "Escalated",
                    id="esc",
                    desc="incident opened",
                    station="terminal",
                    partition="exhausted",
                ),
            ],
            "edges": [
                _e("a1", "a2", label="miss · route up", label_style="chip"),
                _e("a2", "a3", label="miss · route up", label_style="chip"),
                _e("a3", "a4", label="miss · route up", label_style="chip"),
                _e("a1", "done"),
                _e("a2", "done", label="fixed", label_style="chip"),
                _e("a3", "done"),
                _e("a4", "done"),
                _e("a4", "esc", label="out of depth", label_style="chip"),
            ],
        },
    ),
    (
        "index-compounder",
        "The accumulate register on the lateral cell: the gauge banks left-to-right under the row.",
        {
            "topology": "loop",
            "orientation": "horizontal",
            "motion_register": "accumulate",
            "title": "The compounding index",
            "subtitle": "Loop · every pass adds a shard to the index — the gauge banks the gain and holds it",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Crawl the delta",
                    id="crawl",
                    desc="changed docs only",
                    kind="eye",
                ),
                _n(
                    "Embed the shards",
                    id="embed",
                    desc="batch encode",
                    kind="zap",
                ),
                _n(
                    "Merge the index",
                    id="merge",
                    desc="segments compact",
                    kind="database",
                ),
            ],
            "edges": [
                _e("crawl", "embed"),
                _e("embed", "merge"),
                _e(
                    "merge",
                    "crawl",
                    label="compounds · each pass",
                    label_style="chip",
                    circuit="return",
                    accumulates=True,
                    meter=6,
                ),
            ],
        },
    ),
    (
        "shift-loop",
        "The family cap, occupied: ten nodes — eight stations, one gate, one exit — on one spine.",
        {
            "topology": "loop",
            "title": "The agent's long shift",
            "subtitle": "Loop · eight stations end to end, one gate at the bottom — the return rides the full "
            "margin rail",
            "nodes": [
                _n("Wake on the cron", id="s1", kind="clock"),
                _n("Read the queue", id="s2", kind="eye"),
                _n("Pick a ticket", id="s3", kind="git-branch"),
                _n("Reproduce it", id="s4", kind="play"),
                _n("Write the fix", id="s5", kind="wrench"),
                _n("Run the suite", id="s6", kind="activity"),
                _n("Open the PR", id="s7", kind="upload"),
                _n("Log the outcome", id="s8", kind="database"),
                _n("Queue empty?", id="q", station="decision"),
                _n(
                    "Clock out.",
                    id="out",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("s1", "s2"),
                _e("s2", "s3"),
                _e("s3", "s4"),
                _e("s4", "s5"),
                _e("s5", "s6"),
                _e("s6", "s7"),
                _e("s7", "s8"),
                _e("s8", "q"),
                _e("q", "out", label="yes", label_style="chip"),
                _e(
                    "q",
                    "s1",
                    label="no · next ticket",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "crawl-budget",
        "The budget register on the lateral cell: the gauge drains left-to-right under the row.",
        {
            "topology": "loop",
            "orientation": "horizontal",
            "motion_register": "budget",
            "title": "The crawl budget",
            "subtitle": "Loop · each fetch spends one unit of the crawl budget — the gauge drains, the fresh "
            "domain refills it",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Fetch a page",
                    id="get",
                    desc="polite · throttled",
                    kind="zap",
                ),
                _n("More links?", id="more", station="decision"),
                _n(
                    "Domain done.",
                    id="done",
                    desc="index flushed",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("get", "more"),
                _e("more", "done", label="no", label_style="chip"),
                _e(
                    "more",
                    "get",
                    label="crawl on",
                    label_style="chip",
                    circuit="return",
                    meter=4,
                ),
            ],
        },
    ),
    (
        "handoff-lanes",
        "Three role lanes, six stations: a deeper swimlane than the shipped cell, two handoffs down.",
        {
            "topology": "loop",
            "orientation": "horizontal",
            "lanes": ["agent", "human", "system"],
            "title": "The delivery relay",
            "subtitle": "Loop · the agent builds, the human signs off, the system rolls out — a miss crosses all "
            "the way back",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Plan the change",
                    id="plan",
                    desc="scope it",
                    kind="git-branch",
                    category="agent",
                ),
                _n(
                    "Build it",
                    id="build",
                    desc="code · tests",
                    kind="wrench",
                    category="agent",
                ),
                _n(
                    "Sign off",
                    id="sign",
                    desc="human review",
                    kind="eye",
                    category="human",
                ),
                _n("Approve?", id="ok", station="decision", category="human"),
                _n(
                    "Roll out",
                    id="roll",
                    desc="staged deploy",
                    kind="rocket",
                    category="system",
                ),
                _n(
                    "Live.",
                    id="live",
                    desc="serving traffic",
                    station="terminal",
                    partition="advance",
                    style="pill",
                    kind="circle-check",
                    category="system",
                ),
            ],
            "edges": [
                _e("plan", "build"),
                _e("build", "sign", label="hands over", label_style="chip"),
                _e("sign", "ok"),
                _e("ok", "roll", label="approved", label_style="chip"),
                _e("roll", "live"),
                _e(
                    "ok",
                    "plan",
                    label="rework it",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "migration-atlas",
        "The still map: zones, guard chips, and the washed terminals carry the "
        "meaning with zero motion (the cycle-turn hand file's register).",
        {
            "topology": "loop",
            "motion_register": "drift",
            "zones": ["rework", "advance"],
            "title": "The migration campaign",
            "subtitle": "Loop · one codemod at a time — the map alone says what advances and what reworks",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Pick a package",
                    id="pick",
                    desc="dependency order",
                    kind="database",
                ),
                _n(
                    "Run the codemod",
                    id="run",
                    desc="apply · format",
                    kind="zap",
                ),
                _n("Suite green?", id="ok", station="decision"),
                _n(
                    "Patch by hand",
                    id="fix",
                    desc="the odd corners",
                    partition="discard",
                    kind="wrench",
                ),
                _n(
                    "Lands clean",
                    id="keep",
                    desc="commit it",
                    partition="advance",
                    kind="circle-check",
                ),
                _n(
                    "Campaign done?",
                    id="stop",
                    station="decision",
                    chips=["all packages", "budget spent"],
                ),
                _n(
                    "Migrated.",
                    id="done",
                    desc="tree is clean",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("pick", "run"),
                _e("run", "ok"),
                _e("ok", "fix", label="no", label_style="chip"),
                _e("ok", "keep", label="yes", label_style="chip"),
                _e("fix", "stop"),
                _e("keep", "stop"),
                _e("stop", "done", label="yes", label_style="chip"),
                _e(
                    "stop",
                    "pick",
                    label="no · next package",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "toolchain-map",
        "A second still map: the region, its legend chip, the inner circuit, and a telemetry aside "
        "read as one gestalt without a single keyframe.",
        {
            "topology": "loop",
            "motion_register": "drift",
            "title": "The toolchain, at rest",
            "subtitle": "Loop · the inner tool loop sits inside its region, the aside reports out, the pill "
            "closes it — the shape IS the explanation",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Take the task",
                    id="take",
                    desc="queue · claim",
                    kind="upload",
                ),
                _n("Tool loop", id="scope", station="scope"),
                _n(
                    "Decide",
                    id="i1",
                    desc="next call",
                    enclosure="scope",
                    kind="git-branch",
                ),
                _n(
                    "Call",
                    id="i2",
                    desc="mcp · bash",
                    enclosure="scope",
                    kind="zap",
                ),
                _n(
                    "Read",
                    id="i3",
                    desc="fold it in",
                    enclosure="scope",
                    kind="eye",
                ),
                _n(
                    "Ship the answer",
                    id="ship",
                    desc="task closed",
                    style="pill",
                    kind="circle-check",
                ),
                _n(
                    "Run log",
                    id="log",
                    desc="telemetry",
                    station="external",
                    kind="database",
                ),
            ],
            "edges": [
                _e("take", "scope", label="delegate", label_style="chip"),
                _e("i1", "i2"),
                _e("i2", "i3"),
                _e(
                    "i3",
                    "i1",
                    label="go again",
                    label_style="chip",
                    circuit="return",
                ),
                _e("scope", "ship", label="answered", label_style="chip"),
                _e(
                    "ship",
                    "log",
                    circuit="tap-out",
                    label="metrics",
                    label_style="chip",
                ),
                _e(
                    "ship",
                    "take",
                    label="next task",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "standup-loop",
        "Five stations on one endless spine — the longest plain circuit in the set, one pill among cards.",
        {
            "topology": "loop",
            "title": "The standup cadence",
            "subtitle": "Loop · five rituals, every day, in order — nothing exits, the cadence IS the point",
            "node_style": "card+glyph",
            "nodes": [
                _n(
                    "Read the board",
                    id="s1",
                    desc="overnight drift",
                    kind="eye",
                ),
                _n(
                    "Call the standup",
                    id="s2",
                    desc="three questions",
                    kind="play",
                    style="pill",
                ),
                _n(
                    "Unblock the pair",
                    id="s3",
                    desc="worst blocker first",
                    kind="wrench",
                ),
                _n(
                    "Ship the day's cut",
                    id="s4",
                    desc="small and green",
                    kind="upload",
                ),
                _n(
                    "Write the log",
                    id="s5",
                    desc="tomorrow's context",
                    kind="database",
                ),
            ],
            "edges": [
                _e("s1", "s2"),
                _e("s2", "s3"),
                _e("s3", "s4"),
                _e("s4", "s5"),
                _e(
                    "s5",
                    "s1",
                    label="next day",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
]


# ── 5 · Capability edges ────────────────────────────────────────────────

_CAPABILITIES: list[Exhibit] = [
    (
        "cap-two-node-loop",
        "The floor: a two-station loop is legal — request and retry ping-pong.",
        {
            "topology": "loop",
            "title": "The smallest loop",
            "nodes": [
                _n("Try the call", id="a"),
                _n("Adjust and retry", id="b"),
            ],
            "edges": [
                _e("a", "b"),
                _e(
                    "b",
                    "a",
                    label="again",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "cap-derived-endless",
        "Compile-by-omission: a plain endless loop needs NO edges — the chain plus the closing return derive.",
        {
            "topology": "loop",
            "title": "Derived endless loop",
            "subtitle": "Loop · no edges declared — the circuit derives from node order",
            "nodes": [_n("Sense"), _n("Plan"), _n("Act")],
        },
    ),
    (
        "cap-holder-growth",
        "The decision-holder grows for its chips — rhombus-true, never bbox-true.",
        {
            "topology": "loop",
            "title": "Holder growth",
            "nodes": [
                _n("Attempt the merge", id="a"),
                _n(
                    "Stop?",
                    id="stop",
                    station="decision",
                    chips=[
                        "target hit",
                        "no gains",
                        "out of ideas",
                        "budget spent",
                    ],
                ),
                _n(
                    "Stopped.",
                    id="done",
                    station="terminal",
                    partition="advance",
                ),
            ],
            "edges": [
                _e("a", "stop"),
                _e("stop", "done", label="yes", label_style="chip"),
                _e(
                    "stop",
                    "a",
                    label="no",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
    (
        "cap-exhausted-falls-through",
        "The two-terminal placement rule: the advance exit leaves at its decision's rank; the bottom belongs "
        "to exhaustion.",
        {
            "topology": "loop",
            "title": "Two terminals, two homes",
            "nodes": [
                _n("Call the API", id="call"),
                _n("2xx?", id="ok", station="decision"),
                _n(
                    "Return the body.",
                    id="good",
                    station="terminal",
                    partition="advance",
                ),
                _n("Budget left?", id="budget", station="decision"),
                _n("Back off", id="wait"),
                _n(
                    "Surface the error.",
                    id="bad",
                    station="terminal",
                    partition="exhausted",
                ),
            ],
            "edges": [
                _e("call", "ok"),
                _e("ok", "good", label="yes", label_style="chip"),
                _e("ok", "budget", label="no", label_style="chip"),
                _e("budget", "wait", label="yes", label_style="chip"),
                _e("budget", "bad", label="no", label_style="chip"),
                _e(
                    "wait",
                    "call",
                    label="attempt n+1",
                    label_style="chip",
                    circuit="return",
                ),
            ],
        },
    ),
]


# ── 6 · Boundaries (refusals as evidence) ───────────────────────────────

_BOUNDARIES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "the skip branch",
        "A branch that skips past a spine station has no lawful route — it would draw through the card.",
        {
            "topology": "loop",
            "nodes": [
                {"id": "a", "label": "Run"},
                {"id": "q", "label": "Green?", "station": "decision"},
                {"id": "fix", "label": "Patch"},
                {"id": "stop", "label": "Done?", "station": "decision"},
                {
                    "id": "out",
                    "label": "Out.",
                    "station": "terminal",
                    "partition": "advance",
                },
            ],
            "edges": [
                {"from": "a", "to": "q"},
                {
                    "from": "q",
                    "to": "fix",
                    "label": "no",
                    "label_style": "chip",
                },
                {
                    "from": "q",
                    "to": "stop",
                    "label": "yes",
                    "label_style": "chip",
                },
                {"from": "fix", "to": "stop"},
                {
                    "from": "stop",
                    "to": "out",
                    "label": "yes",
                    "label_style": "chip",
                },
                {
                    "from": "stop",
                    "to": "a",
                    "label": "no",
                    "label_style": "chip",
                    "circuit": "return",
                },
            ],
        },
    ),
    (
        "two returns",
        "A loop closes on exactly ONE outer return — the rail is the one lawful long route.",
        {
            "topology": "loop",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [
                {"from": "a", "to": "b", "circuit": "return"},
                {"from": "b", "to": "a", "circuit": "return"},
            ],
        },
    ),
    (
        "external without a tap",
        "Externals participate in tap edges only — the world touches the loop through its taps.",
        {
            "topology": "loop",
            "nodes": [
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "x", "label": "World", "station": "external"},
            ],
            "edges": [
                {"from": "a", "to": "b"},
                {"from": "b", "to": "a", "circuit": "return"},
                {"from": "a", "to": "x"},
            ],
        },
    ),
    (
        "scope boundary crossed",
        "The scope is the node for port purposes — nothing crosses its boundary.",
        {
            "topology": "loop",
            "nodes": [
                {"id": "p", "label": "Plan"},
                {"id": "s", "label": "Inner", "station": "scope"},
                {"id": "i1", "label": "A", "enclosure": "s"},
                {"id": "i2", "label": "B", "enclosure": "s"},
            ],
            "edges": [
                {"from": "p", "to": "i1"},
                {"from": "i1", "to": "i2"},
                {"from": "i2", "to": "i1", "circuit": "return"},
                {"from": "s", "to": "p", "circuit": "return"},
            ],
        },
    ),
    (
        "decision with one exit",
        "An exclusive decision spends exactly two exits, each with its guard.",
        {
            "topology": "loop",
            "nodes": [
                {"id": "a", "label": "A"},
                {"id": "d", "label": "OK?", "station": "decision"},
            ],
            "edges": [
                {"from": "a", "to": "d"},
                {"from": "d", "to": "a", "circuit": "return"},
            ],
        },
    ),
    (
        "terminal with an exit",
        "A terminal is a sink — the loop exits there; nothing leaves it.",
        {
            "topology": "loop",
            "nodes": [
                {"id": "a", "label": "A"},
                {"id": "t", "label": "Done.", "station": "terminal"},
                {"id": "b", "label": "B"},
            ],
            "edges": [
                {"from": "a", "to": "t"},
                {"from": "t", "to": "b"},
                {"from": "b", "to": "a", "circuit": "return"},
            ],
        },
    ),
    (
        "a second loop-closing edge",
        "The forward graph is acyclic — the return is the ONE back edge; a second cycle is two diagrams, or a scope.",
        {
            "topology": "loop",
            "nodes": [
                {"id": "work", "label": "Work"},
                {"id": "full", "label": "Full?", "station": "decision"},
                {"id": "compact", "label": "Compact"},
            ],
            "edges": [
                {"from": "work", "to": "full"},
                {"from": "full", "to": "compact", "label": "yes"},
                {
                    "from": "full",
                    "to": "work",
                    "label": "no",
                    "circuit": "return",
                },
                {"from": "compact", "to": "work"},
            ],
        },
    ),
    (
        "devices without edges",
        "Only the plain endless loop derives its edges; a decision makes edges content.",
        {
            "topology": "loop",
            "nodes": [{"label": "A", "station": "decision"}, {"label": "B"}],
        },
    ),
    (
        "the turn register off-loop",
        "The turn register ships on the loop family this release; other families keep the drift face.",
        {
            "topology": "pipeline",
            "motion_register": "turn",
            "nodes": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
        },
    ),
    (
        "past the cap",
        "Eleven stations exceeds the family cap — split the diagram.",
        {
            "topology": "loop",
            "nodes": [{"label": f"Step {i}"} for i in range(11)],
        },
    ),
]


def _all_specs() -> list[dict[str, Any]]:
    return [s for _, _, s in _axis_grid()] + [s for _, _, s in _SCENARIOS] + [s for _, _, s in _CAPABILITIES]


def _assert_tokens_resolve() -> None:
    """Every declared kind/glyph must resolve in a registry — an unresolved mark
    renders NOTHING (icon-or-nothing), and an exhibit that silently shows a bare
    card where it promised a mark is a broken promise."""
    import json

    core = json.loads((_REPO / "src/hyperweave/data/registries/glyphs-core.json").read_text())
    brands = json.loads((_REPO / "src/hyperweave/data/registries/glyphs.json").read_text())
    for spec in _all_specs():
        for node in spec.get("nodes", []):
            kind = node.get("kind", "")
            glyph = node.get("glyph", "")
            if kind and kind not in core:
                raise SystemExit(f"loop exhibit: kind {kind!r} resolves in no registry ({spec.get('title')})")
            if glyph and glyph not in brands:
                raise SystemExit(f"loop exhibit: glyph {glyph!r} resolves in no registry ({spec.get('title')})")


def build_loop() -> int:
    """Compose the loop family exhibit. Returns the artifact count."""
    from scripts.examples.topologies.exhibit import render

    _assert_tokens_resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.svg"):
        stale.unlink()
    for sub in SECTION_DIRS:
        (OUT / sub).mkdir(exist_ok=True)
        for stale in (OUT / sub).glob("*.svg"):
            stale.unlink()

    total = 0
    lines: list[str] = [
        "# loop — the procedural directed loop, every cell the engine can produce",
        "",
        "`loop` says what `cycle` cannot: *repeat UNTIL, then exit*. Where the",
        "cycle family (orbit | ring) draws closed endless rhythm, a loop carries",
        "logic — exclusive decisions with guard chips, terminal exits, a return",
        "rail closing the circuit, external taps, and one-level named scopes.",
        "",
        "Two public axes: **orientation** (vertical spine + margin rail, the",
        "default | horizontal row + underslung return — one solver, both cells,",
        "through the axis map) and the **motion register** (`turn` performs the",
        "claim in time and is the family default; `drift` is the quiet standing",
        "face; one flag flips them: `--motion-register`, `?motion_register=`,",
        "MCP `motion_register`).",
        "",
        "**Devices are structural, never flags**: two decisions = retry ·",
        "tap edges = supervised loop · a scope node = nested loop ·",
        "`accumulates` on the return = flywheel.",
        "",
        "Every artifact is a live engine render on the baked porcelain light",
        "face; nothing here is hand-drawn.",
        "",
    ]

    section(
        lines,
        "0 · Is this a loop or a cycle?",
        "The words overlap in English; the families split on capability.\n\n"
        "`cycle` **derives** a closed ring: every stage repeats forever, no stage"
        " ever exits, and nothing branches. Its cells are radial (orbit | ring) "
        "because endless rhythm wants a circle.\n\n"
        "`loop` carries **control flow**: a decision spends two guarded exits, a "
        "terminal ends the story, and the return rail is the one lawful long "
        "route home. Its cells are directed (vertical | horizontal) because "
        "until-logic wants a reading order.\n\n"
        '**Rule of thumb: if any stage can say "stop", it is a loop.** The '
        "flywheel below exists in BOTH families — the same four stages ride "
        "`cycle-orbit` as a narrative ring and `loop-flywheel` as a performed "
        "circuit — and that pair is the boundary, drawn.",
    )
    total += exhibit(
        lines,
        OUT,
        "why-cycle-face",
        "The narrative face: the same flywheel as `topology: cycle`, orientation orbit — endless, unbranched.",
        {
            "topology": "cycle",
            "orientation": "orbit",
            "title": "The flywheel as a cycle",
            "nodes": [
                _n(
                    "the flywheel",
                    id="hub",
                    desc="compounds each turn",
                    role="hero",
                    short="hw",
                ),
                _n("Generate", id="g", desc="agents create"),
                _n("Distribute", id="d", desc="ship anywhere"),
                _n("Capture", id="c", desc="corpus grows"),
                _n("Improve", id="i", desc="model learns"),
            ],
        },
        "why",
    )
    total += exhibit(
        lines,
        OUT,
        "why-loop-face",
        "The performed face: the same stages as `topology: loop` — the return carries the accumulator claim.",
        {
            "topology": "loop",
            "title": "The flywheel as a loop",
            "nodes": [
                _n("Generate", id="g", desc="agents create"),
                _n("Distribute", id="d", desc="ship anywhere"),
                _n("Capture", id="c", desc="corpus grows"),
                _n("Improve", id="i", desc="model learns"),
            ],
            "edges": [
                _e("g", "d"),
                _e("d", "c"),
                _e("c", "i"),
                _e(
                    "i",
                    "g",
                    label="compounds · each turn",
                    label_style="chip",
                    circuit="return",
                    accumulates=True,
                ),
            ],
        },
        "why",
    )

    from hyperweave.compose.bundled_specs import resolve_bundled_spec

    section(
        lines,
        "1 · The axis grid",
        "One four-node review loop, rendered at every cell of orientation x "
        "register. The geometry transposes through the axis map (boxes never "
        "rotate; the far channel becomes the underside — the underslung "
        "return IS the margin rail, transposed). The register flip is "
        "motion-only: drift faces carry zero keyframes.",
    )
    for slug, what, spec in _axis_grid():
        total += exhibit(lines, OUT, slug, what, spec, "axis-grid")

    section(
        lines,
        "2 · Real scenarios",
        "Loops agents and humans actually run: tool loops, retries, evals, "
        "reviews, compaction, supervision — and their branded siblings: "
        "reconcile loops, provider failover, PR shuttles, supervised "
        "deploys, consumer loops, and the fine-tune flywheel. Brand marks "
        "ride the identity slot; devices and orientations mix across the "
        "set so the family's compositional range is on one page.",
    )
    for slug, what, spec in _SCENARIOS:
        total += exhibit(lines, OUT, slug, what, spec, "scenarios")

    section(
        lines,
        "3 · The bundled corpus",
        "Every loop preset, rendered ONCE as shipped — `hyperweave compose "
        "diagram --spec-file <name>`. Anchor presets cite their hand "
        "specimen inline; the side-by-side proof board lives in "
        "`README_SPECIMENS.md`.",
    )
    from hyperweave.compose.bundled_specs import bundled_spec_names

    sources = {preset: source for preset, source, _claim in _SPECIMENS}
    for name in [n for n in bundled_spec_names("diagram") if n.startswith("loop")]:
        bs = resolve_bundled_spec("diagram", name)
        svg = render(OUT, f"corpus-{name}", dict(bs.value), "corpus")
        cite = f" — specimen: `{sources[name]}`" if name in sources else ""
        lines += [
            f"#### `{name}`{cite}",
            "",
            f"![{name}](../renders/topologies/{FAMILY}/corpus/corpus-{name}.svg)",
            "",
            f"*render scale {scale_of(svg)}*",
            "",
        ]
        total += 1

    section(
        lines,
        "4 · Capability edges",
        "The floors and growth laws worth pinning: the two-station floor, "
        "compile-by-omission, rhombus-true holder growth, and the "
        "two-terminal placement rule.",
    )
    for slug, what, spec in _CAPABILITIES:
        total += exhibit(lines, OUT, slug, what, spec, "capabilities")

    section(
        lines,
        "5 · Boundaries",
        "The refusals, quoted verbatim — a caller reads the same sentence. "
        "The quarantined `ivalid-cycle-family/` corpus documents what these "
        "walls exist to stop: blown occlusion, hue promoted to partitions, "
        "one port spending two edges.",
    )
    for title, why, spec in _BOUNDARIES:
        lines += [f"**{title}** — {why}", "", "```", refusal(spec), "```", ""]

    lines += _elsewhere_lines()
    (_DIAGRAMS / "topologies" / f"README_{FAMILY.upper()}.md").write_text("\n".join(lines) + "\n")
    return total


def _elsewhere_lines() -> list[str]:
    from scripts.examples.topologies.exhibit import _elsewhere_section

    return _elsewhere_section(FAMILY)


_ = register_elsewhere  # the porcelain board registers loop renders itself


def main() -> None:
    count = build_loop()
    print(f"loop exhibit: {count} renders")


if __name__ == "__main__":
    main()
