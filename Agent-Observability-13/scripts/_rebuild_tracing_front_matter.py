#!/usr/bin/env python3
"""Rebuild slides for pedagogy:

preflight → primer → agent sketch → 01 → spans+trace → LangSmith →
health → ids → 02 → … (runtime/store deep walk after 02)
"""

from __future__ import annotations

import html as html_lib
import json
import re
import runpy
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIDES_HTML = ROOT / "interactive-slides.html"
SPEAKER_HTML = ROOT / "speaker-script.html"
sys.path.insert(0, str(ROOT / "src"))


def load_data() -> tuple[dict, str, str]:
    text = SLIDES_HTML.read_text(encoding="utf-8")
    idx = text.find("const DATA=")
    if idx < 0:
        raise SystemExit("DATA not found")
    start = idx + len("const DATA=")
    data, end = json.JSONDecoder().raw_decode(text[start:])
    return data, text[:start], text[start + end :]


def capture_script(rel: str) -> str:
    buf = StringIO()
    with redirect_stdout(buf):
        try:
            runpy.run_path(str(ROOT / rel), run_name="__main__")
        except SystemExit:
            pass
    return buf.getvalue().strip()


def capture_ids_sample() -> dict:
    from obs_agent.contracts import FaultScenario, RunRequest
    from obs_agent.runtime import ObservabilityRuntime

    rt = ObservabilityRuntime(export_traces=True, sleep_fn=lambda _s: None)
    result = rt.run(
        RunRequest(question="What is the status of ORD-1001?", scenario=FaultScenario.CORRECT)
    )
    span_names: list[str] = []
    path = ROOT / "logs" / "traces.jsonl"
    if path.exists():
        line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
        payload = json.loads(line)
        span_names = [s.get("name", "") for s in payload.get("spans", [])]
    return {
        "request_id": result.request_id,
        "job_id": result.job_id,
        "attempt_id": result.attempt_id,
        "trace_id": result.trace_id,
        "span_names": span_names,
    }


def slide(
    *,
    title: str,
    minutes: int,
    kind: str,
    body: list[str],
    say: str,
    show: str,
    source: str,
    ask: str = "",
    answer: str = "",
    lab: str | None = None,
    beats: list[str] | None = None,
    output: str | None = None,
    optional: bool = False,
) -> dict:
    s: dict = {
        "title": title,
        "minutes": minutes,
        "kind": kind,
        "body": body,
        "say": say,
        "show": show,
        "ask": ask,
        "answer": answer,
        "source": source,
        "lab": lab,
    }
    if beats:
        s["beats"] = beats
    if output is not None:
        s["output"] = output
    if optional:
        s["optional"] = True
    return s


def build_early(
    *,
    primer_output: str,
    preflight_output: str,
    ids: dict,
) -> list[dict]:
    id_line = (
        f"request_id={ids['request_id']}  job_id={ids['job_id']}  "
        f"attempt_id={ids['attempt_id']}  trace_id={ids['trace_id']}"
    )
    span_preview = " → ".join(ids["span_names"][:7]) or "support_ops.queue_wait → … → support_ops.validate"

    return [
        slide(
            title="Agentic observability",
            minutes=2,
            kind="cover",
            body=[
                "The agent is running. Is it working?",
                "See a run first. Then read the traces that explain it.",
                "July cohort · phenomenon before implementation",
            ],
            show="Show the title slide. Terminal ready. Do not run the agent yet.",
            ask="When a system returns an answer, what evidence would convince you the run actually worked?",
            answer="Take two answers. Acknowledge uptime and latency, then ask whether either proves correctness.",
            source="README.md; LEARNER-FOLLOW-ALONG.md",
            say=(
                "Hi everyone. Today we investigate an agent the way we would investigate a service "
                "customers depend on. We already know how to make an agent return an answer. The "
                "question is how we know whether that answer helped.\n\n"
                "Teaching order today: shared telemetry vocabulary, a quick look at the support-ops "
                "system, a live comparison of two completed runs, then the code and LangSmith views "
                "that explain those runs. Phenomenon first. Implementation second.\n\n"
                "Keep one habit: which question are we asking, which signal answers it, and what "
                "would we do next?"
            ),
        ),
        slide(
            title="The investigation today",
            minutes=2,
            kind="agenda",
            body=[
                "01  Preflight, then telemetry primer",
                "02  Agent sketch → two completed runs",
                "03  Spans in code, then LangSmith",
                "04  Diagnose latency, quality, cost, SLOs",
            ],
            show="Show the agenda. Emphasize: cafe → agent sketch → lab 01 → code/LangSmith → labs.",
            source="LEARNER-FOLLOW-ALONG.md; DEMO-CHEATSHEET.md",
            say=(
                "Here is the route. We verify the environment, learn log, metric, and trace with a "
                "tiny cafe example, then sketch the support-ops agent and run two completed jobs—"
                "one correct, one confidently wrong.\n\n"
                "Only after that evidence exists do we open spans.py and compare local traces with "
                "LangSmith. The second half diagnoses latency, quality, cost, alerts, and export "
                "hygiene.\n\n"
                "If we are short on time late in the session, the cheatsheet marks stretch exercises "
                "you can park."
            ),
        ),
        slide(
            title="Preflight: environment ready",
            minutes=2,
            kind="lab",
            body=[
                "Confirm .env, model, and LangSmith flags",
                "Run one correct path smoke test",
                "Stop here if preflight fails",
            ],
            show=(
                "Run python3 run_lab.py 00. Point at openai_configured and langsmith_project. "
                "If it fails, fix env before continuing — do not start labs on a broken setup."
            ),
            lab="00",
            beats=[
                "0–1 min: explain why we preflight before demos.",
                "1–2 min: run lab 00; confirm OK or fix.",
            ],
            output=preflight_output,
            source="scripts/00_preflight.py; .env.example",
            ask="If openai_configured is false, should we still run the opening comparison?",
            answer="No for live paths. Use recorded results only as a fallback, and fix .env first.",
            say=(
                "Before any teaching demo, we check that the room can actually run the agent. "
                "Preflight loads .env, prints whether OpenAI and LangSmith are configured, and "
                "executes one correct-path smoke test.\n\n"
                "If this fails, we stop and fix the environment. Mid-session key problems waste "
                "more time than two minutes now."
            ),
        ),
        slide(
            title="Telemetry primer: three signals",
            minutes=5,
            kind="primer",
            body=[
                "LOG — one event, one message",
                "METRIC — aggregated counts and latency",
                "TRACE — related spans for one run",
            ],
            show=(
                "Run python3 run_lab.py primer. Point at log, then metric, then the slow-order "
                "span list. Ask which span dominated before revealing grind."
            ),
            lab="primer",
            beats=[
                "0–1 min: define the three signals without code.",
                "1–3 min: run the primer; narrate fast vs slow order.",
                "3–4 min: learners identify the dominant span.",
                "4–5 min: connect to the upcoming agent run.",
            ],
            output=primer_output,
            source="scripts/00a_telemetry_primer.py; TELEMETRY-PRIMER.md",
            ask="If the cafe dashboard only showed orders completed, would you know the grinder was slow?",
            answer="No. Completion can stay healthy while one span gets slower. You need the trace or a latency breakdown.",
            say=(
                "Telemetry is not a product name. It is the set of signals a running system emits "
                "so we can answer investigation questions later.\n\n"
                "A log is one event with a message: what happened?\n\n"
                "A metric is an aggregated number: how often, how much, or how long across many runs?\n\n"
                "A trace is related timed operations for one run. Each operation is a span. "
                "Spans have parents and children. A trace answers: where did the time go?\n\n"
                "I will run a tiny cafe example — not an agent. In the slow run, compare cafe.grind "
                "to cafe.extract. That comparison is the same skill we use when a support agent is slow."
            ),
        ),
        slide(
            title="The agent we are observing",
            minutes=3,
            kind="flow",
            body=[
                "Accept job",
                "Simulated queue wait",
                "Worker: retrieve, plan, tools, generate",
                "Validate answer",
                "Record health scorecard",
            ],
            show=(
                "Reveal the flow one stage at a time. Open agent.py _build_graph only after the "
                "stages are visible. Do not deep-dive spans yet."
            ),
            source="src/obs_agent/agent.py; src/obs_agent/runtime.py",
            ask="Where would a slow tool show up in this flow?",
            answer="Inside the worker, during tools — before generate and validate.",
            say=(
                "Here is the system we are about to run. The runtime accepts a request and creates "
                "identifiers. It simulates a short queue wait, invokes a worker, then validates the "
                "result.\n\n"
                "Inside the worker: retrieve reads the order catalog and policy text; plan selects "
                "actions; tools execute through a gateway; generate constructs the answer. On "
                "selected paths a real model call can run.\n\n"
                "We will investigate two runs of this same flow next. Keep the stages in mind when "
                "the scorecard disagrees with status=completed."
            ),
        ),
        # Opening lab 01 is pulled from existing slide content in rebuild_slides
    ]


def build_spans_and_langsmith(ids: dict) -> list[dict]:
    span_preview = " → ".join(ids["span_names"][:7]) or (
        "support_ops.queue_wait → gen_ai.agent.retrieve → support_ops.worker → …"
    )
    id_line = (
        f"request_id={ids['request_id']} · job_id={ids['job_id']} · "
        f"attempt_id={ids['attempt_id']} · trace_id={ids['trace_id']}"
    )
    return [
        slide(
            title="Spans that built that run",
            minutes=5,
            kind="code",
            body=[
                "01  spans.py — start_trace and with span()",
                "02  Nested with-blocks become parent/child",
                "03  Printed tree from the run you just saw",
            ],
            show=(
                "Open Source → spans.py only (start_trace, span context manager). Then show the "
                f"span names from the opening run: {span_preview}. Mention runtime/store briefly; "
                "full walk comes after the latency lab."
            ),
            source="src/obs_agent/telemetry/spans.py; logs/traces.jsonl",
            ask="What does entering a with ctx.span(...) block create that leaving the block finalizes?",
            answer="A child span with a parent pointer and start time; on exit, duration and status are recorded.",
            say=(
                "You just saw two completed jobs. Now we look at how this repository records a "
                "timeline for one job.\n\n"
                "Open spans.py. start_trace creates a TraceContext with a trace_id. The span "
                "context manager pushes a new span onto a stack, sets its parent to whatever is "
                "currently open, and on exit records duration and status. Nesting in code becomes "
                "parent and child in the trace — the same idea as cafe.grind under cafe.order.\n\n"
                f"From the correct run you just executed, the span names look like: {span_preview}.\n\n"
                "runtime.py is where those names are opened around the job. store.py appends the "
                "finished tree to traces.jsonl. We will open those files after the latency lab, "
                "once you have diagnosed bottlenecks from span timings."
            ),
        ),
        slide(
            title="Local traces and LangSmith",
            minutes=5,
            kind="langsmith",
            body=[
                "Same questions: which run? where time went? what did tools/model do?",
                "Local spans: strong on job lifecycle (queue → worker → validate)",
                "LangSmith: strong on LLM and tool call detail",
            ],
            show=(
                "Show the comparison table. Open the LangSmith project from .env "
                "(july-cohort-observability) and find the correct-path run from lab 01. "
                "Say explicitly that local trace_id and LangSmith run id are different unless correlated."
            ),
            source="config.py::_apply_langsmith_env; agent.py::_generate; https://docs.langchain.com/langsmith/observability",
            ask="If LangSmith shows a fast model call but the customer still waited, what might our local trace still reveal?",
            answer="Queue wait or tool latency outside the model span — the job lifecycle view.",
            say=(
                "Now that a live run exists, we can open LangSmith. It is not replacing our tracer. "
                "For model and tool calls it is often the detailed product UI. Our runtime spans "
                "teach the full job lifecycle: accept, queue, worker, validate.\n\n"
                "Use the same investigation questions in both places. Which run is this? Where did "
                "the time go? What did the tools and model actually do?\n\n"
                "Do not assume the local trace_id equals a LangSmith run id. They are related views "
                "of overlapping evidence, not automatically the same primary key.\n\n"
                f"Local IDs from a sample correct run look like: {id_line}."
            ),
        ),
    ]


def renumber(slides: list[dict]) -> list[dict]:
    t = 0
    out = []
    for i, raw in enumerate(slides, start=1):
        s = dict(raw)
        minutes = int(s.get("minutes") or 0)
        s["n"] = i
        s["start"] = t
        s["end"] = t + minutes
        t += minutes
        out.append(s)
    return out


def find_slide(by_title: dict, *titles: str) -> dict | None:
    for title in titles:
        if title in by_title:
            return dict(by_title[title])
        alt = title.replace("’", "'")
        if alt in by_title:
            return dict(by_title[alt])
        alt2 = title.replace("'", "’")
        if alt2 in by_title:
            return dict(by_title[alt2])
    return None


def rebuild_slides(data: dict, *, primer_output: str, preflight_output: str, ids: dict) -> list[dict]:
    by_title = {s["title"]: s for s in data["slides"]}

    early = build_early(primer_output=primer_output, preflight_output=preflight_output, ids=ids)

    opening = find_slide(by_title, "Two runs both completed")
    if opening is None:
        raise SystemExit("missing opening slide")
    opening["minutes"] = 5
    opening["show"] = (
        "Run python3 run_lab.py 01. Point at both status=completed lines, then the answers, "
        "then quality / grounded / business_success. Return to the slide and click Reveal comparison."
    )
    # Keep word-for-word continuity with the agent-sketch slide that now precedes this lab.
    say = opening.get("say") or ""
    if say.startswith("Let us start with a situation"):
        opening["say"] = (
            "You just saw the support-ops flow. Now we run it twice.\n\n"
            + say.replace(
                "Let us start with a situation that looks reassuring.",
                "Here is a situation that looks reassuring.",
                1,
            )
        )

    health = find_slide(by_title, "Five dimensions of a healthy run")
    if health is None:
        raise SystemExit("missing health slide")
    health["minutes"] = 3
    health["show"] = (
        "Click each health dimension. Use the opening comparison as the concrete example — "
        "Run B completed quickly but quality failed."
    )

    ids_slide = find_slide(by_title, "Identifiers connect the evidence")
    if ids_slide is None:
        raise SystemExit("missing ids slide")
    ids_slide["minutes"] = 2
    id_line = (
        f"request_id={ids['request_id']}  job_id={ids['job_id']}  "
        f"attempt_id={ids['attempt_id']}  trace_id={ids['trace_id']}"
    )
    ids_slide["body"] = [
        "request_id — the incoming request",
        "job_id — the unit of work",
        "attempt_id — this execution attempt",
        "trace_id — the span tree for this attempt",
        f"Example from a correct run: {id_line}",
    ]
    ids_slide["show"] = (
        f"Show the four identifiers, then the example line from a correct run:\n{id_line}\n"
        "Next slide prints the same fields on the latency cases."
    )
    ids_slide["say"] = (
        "Before we diagnose latency, make the identifiers concrete. The request ID identifies "
        "the incoming request. The job ID identifies the unit of work. The attempt ID identifies "
        "this execution attempt. The trace ID groups the spans for that attempt.\n\n"
        f"Here is a real line from a correct run you already executed: {id_line}.\n\n"
        "In this demo, run() creates fresh request, job, and attempt IDs together. We do not "
        "implement a persistent job retry service. When you read a lab printout, start by "
        "matching these four fields before comparing timings."
    )

    mid = build_spans_and_langsmith(ids)

    # Order: early (cover…agent) → opening → spans → langsmith → health → ids → rest from trace lab
    rest_titles = [
        "Trace lab: where did the time go?",
        "Trace investigation in pairs",
        "Runtime and store: finishing the code walk",
        "A useful dashboard starts with decisions",
        "Dashboard lab: five completed, four validated",
        "Latency distribution exercise",
        "Metric types and label choices",
        "Quality has several levels",
        "Quality lab: a citation can still support nothing",
        "Online evaluation and regression tests",
        "A regression case from the failed answer",
        "Efficiency per successful task",
        "Cost lab: success with a budget failure",
        "Designing a budget guard",  # optional stretch
        "The cost estimate has a defined scope",
        "SLI, SLO, and error budget",
        "The denominator includes unresolved work",
        "Alert lab: a signal with a next action",
        "A short incident investigation",
        "Error-budget arithmetic worth checking",
        "Incident response tabletop",  # optional stretch
        "Telemetry can contain customer data",
        "Hygiene lab: inspect the whole export path",
        "Testing the telemetry boundary",
        "LangSmith recap during investigation",
        "Diagnosis exercise",
        "What production would add",
        "Your agent’s observability plan",
        "Peer review of an observability plan",  # optional stretch
        "Closing the investigation",
    ]

    langsmith_recap = {
        "title": "LangSmith recap during investigation",
        "kind": "optional",
        "minutes": 2,
        "optional": True,
        "body": [
            "Return to LangSmith only for model/tool detail",
            "Keep local job/trace IDs for lifecycle questions",
            "Same investigation questions in both UIs",
        ],
        "show": (
            "Skip if on time pressure. Otherwise briefly reopen LangSmith only if a concrete "
            "run needs model/tool detail."
        ),
        "say": (
            "We already compared local traces and LangSmith after lab 01. Use this moment only "
            "if a concrete run needs model or tool detail from the product UI."
        ),
        "ask": "",
        "answer": "",
        "source": "config.py::_apply_langsmith_env",
        "lab": None,
    }

    runtime_store = {
        "title": "Runtime and store: finishing the code walk",
        "kind": "code",
        "minutes": 4,
        "body": [
            "01  runtime.py — where job spans are opened",
            "02  store.py — record_trace and traces.jsonl",
            "03  What this classroom tracer can and cannot prove",
        ],
        "show": (
            "Now open runtime.py around support_ops.job / queue_wait / tool.call / inference / "
            "validate, then store.py record_trace. Tie names back to the bottleneck cases."
        ),
        "say": (
            "You have diagnosed two latency cases from timings. Now finish the code walk.\n\n"
            "In runtime.py, a job opens support_ops.job, then queue_wait, then worker-related "
            "work, then tool and model spans, then validate. Those names are the timeline you "
            "just read.\n\n"
            "In store.py, record_trace keeps spans in memory and can append them to "
            "logs/traces.jsonl.\n\n"
            "A local classroom trace can prove structure and relative timing for the spans we "
            "recorded. It does not automatically equal a LangSmith run, and it is not a full "
            "OpenTelemetry export. Use it to practice investigation questions."
        ),
        "ask": "After a slow tool diagnosis, which file would you open first to confirm the span name?",
        "answer": "runtime.py where the tool.call span is opened around the gateway call.",
        "source": "src/obs_agent/runtime.py; src/obs_agent/telemetry/store.py; src/obs_agent/telemetry/spans.py",
        "lab": None,
    }

    rest: list[dict] = []
    for title in rest_titles:
        if title == "LangSmith recap during investigation":
            src = (
                find_slide(by_title, title, "LangSmith as an optional investigation view")
                or langsmith_recap
            )
        elif title == "Runtime and store: finishing the code walk":
            src = (
                find_slide(by_title, title, "What this local trace can prove")
                or runtime_store
            )
        else:
            src = find_slide(by_title, title)
        if src is None:
            print("WARN missing", title)
            continue
        s = dict(src)

        if title == "Trace lab: where did the time go?":
            s["minutes"] = 5
        if title == "Trace investigation in pairs":
            s["minutes"] = 5
        if title == "Runtime and store: finishing the code walk":
            s.update(runtime_store)
            s.pop("beats", None)
            s.pop("output", None)
        if title == "LangSmith recap during investigation":
            s.update(langsmith_recap)
            s.pop("beats", None)
            s.pop("output", None)

        # Stretch / optional markers for timeboxing
        if title in (
            "Designing a budget guard",
            "Incident response tabletop",
            "Peer review of an observability plan",
            "LangSmith recap during investigation",
            "Latency distribution exercise",
            "Error-budget arithmetic worth checking",
        ):
            s["optional"] = True
            if title == "Designing a budget guard":
                s["minutes"] = 4
                s["show"] = (s.get("show") or "") + " Stretch: skip if behind the clock."
            if title == "Incident response tabletop":
                s["minutes"] = 4
                s["show"] = (s.get("show") or "") + " Stretch: skip if behind the clock."
            if title == "Peer review of an observability plan":
                s["minutes"] = 4
                s["show"] = (s.get("show") or "") + " Stretch: skip if behind the clock."
            if title == "Latency distribution exercise":
                s["minutes"] = 4
            if title == "Error-budget arithmetic worth checking":
                s["minutes"] = 2

        rest.append(s)

    assembled = early + [opening] + mid + [health, ids_slide] + rest
    return renumber(assembled)


def render_speaker(slides: list[dict]) -> str:
    nav = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Speaker script · Agentic Observability</title>"
        "<style>body{font:19px/1.65 Georgia,serif;max-width:900px;margin:50px auto;padding:0 28px;"
        "color:#182329;background:#faf8f2}h1,h2,h3,nav,.cue{font-family:Arial,sans-serif}"
        "h1{font-size:42px}h2{font-size:28px;margin-top:65px}h3{font-size:17px;letter-spacing:.08em;"
        "text-transform:uppercase;color:#59666b}nav{position:sticky;top:0;background:#faf8f2;"
        "padding:10px 0;border-bottom:1px solid #ddd;font-size:14px}"
        ".cue{padding:16px 20px;background:#e9eeed;font-size:16px;line-height:1.55}"
        ".time{color:#985525;font-family:Arial,sans-serif}a{color:#146d74}pre{white-space:pre-wrap}"
        ".stretch{background:#f3e6d8}footer{font-size:13px;color:#59666b}"
        "@media print{nav{display:none}section{break-before:page}body{font-size:11pt;max-width:none}"
        "h2{margin-top:0}.cue{font-size:10pt}}</style>"
        '<nav><a href="interactive-slides.html">Audience slides</a> · '
        '<button onclick="print()">Print / PDF</button> · '
        '<a href="LEARNER-FOLLOW-ALONG.md">Learner card</a> · '
        '<a href="TELEMETRY-PRIMER.md">Telemetry primer</a> · '
        '<a href="#s1">Jump to start</a></nav>'
        "<h1>Agentic Observability speaker script</h1>"
        f"<p>Phenomenon-first session · {len(slides)} slides · "
        f"{slides[-1]['end']} minutes if every beat is taught; stretch slides are skippable.</p>"
        "<p>Order: preflight → primer → agent sketch → lab 01 → spans → LangSmith → health → "
        "ids → lab 02 → runtime/store → later labs. Lab commands run from Session-Observability.</p>"
    )

    sections = []
    for s in slides:
        n, start, end = s["n"], s["start"], s["end"]
        say_paras = "".join(f"<p>{html_lib.escape(p)}</p>" for p in (s.get("say") or "").split("\n\n") if p.strip())
        cues = [f"<b>SHOW</b> {html_lib.escape(s.get('show') or '')}"]
        if s.get("lab"):
            cues.append(f"<p><b>RUN</b> <code>python3 run_lab.py {html_lib.escape(str(s['lab']))}</code></p>")
        if s.get("optional"):
            cues.append('<p><b>STRETCH</b> Skip if behind the clock.</p>')
        if s.get("beats"):
            items = "".join(f"<li>{html_lib.escape(b)}</li>" for b in s["beats"])
            cues.append(f'<div class="cue"><b>PACING · relative to this slide</b><ul>{items}</ul></div>')
        ask = ""
        if s.get("ask"):
            ask = (
                f'<div class="cue"><b>ASK</b> {html_lib.escape(s["ask"])}'
                f'<p><b>EXPECTED RESPONSE</b> {html_lib.escape(s.get("answer") or "")}</p></div>'
            )
        klass = ' class="stretch"' if s.get("optional") else ""
        sections.append(
            f'<section id="s{n}"{klass}><h2>{n:02d} &nbsp; {html_lib.escape(s["title"])}</h2>'
            f'<p class="time">{start:02d}–{end:02d} minutes'
            f'{" · stretch" if s.get("optional") else ""}</p>'
            f'<div class="cue">{"".join(cues)}</div>'
            f"<h3>Say</h3>{say_paras}{ask}"
            f'<p class="source">Source: {html_lib.escape(s.get("source") or "")}</p></section>'
        )

    footer = (
        "<footer><p>Local authority: Session-Observability source and labs. "
        "LangSmith is an optional detailed view after lab 01 has produced a run.</p></footer></html>"
    )
    return nav + "".join(sections) + footer


def ensure_sources(data: dict) -> None:
    data.setdefault("source", {})
    for key in (
        "scripts/00a_telemetry_primer.py",
        "scripts/00_preflight.py",
        "LEARNER-FOLLOW-ALONG.md",
    ):
        path = ROOT / key
        if path.exists():
            data["source"][key] = path.read_text(encoding="utf-8")


def patch_render_kinds(html: str) -> str:
    if "case 'primer':" in html and "case 'lab':" in html:
        return html
    needle = (
        " case 'formula':content+=`<div class=\"bigformula\">Total cost of serving the tasks<br>÷"
        "<br><strong>Validated successful tasks</strong></div>"
        "<p class=\"lead\">Failures and retries still consume resources.</p>"
        "<p class=\"small\">Use the same population and window. Zero successes has no finite cost per success.</p>`;break;\n"
        " default:content+=rows(s);"
    )
    # After first rebuild, primer/code/langsmith may already exist — replace from formula through default
    alt = re.search(
        r" case 'formula':content\+=`.*?`;break;\n(?: case '(?:primer|code|langsmith|lab)':.*?\n)* default:content\+=rows\(s\);",
        html,
        flags=re.S,
    )
    insert = (
        " case 'formula':content+=`<div class=\"bigformula\">Total cost of serving the tasks<br>÷"
        "<br><strong>Validated successful tasks</strong></div>"
        "<p class=\"lead\">Failures and retries still consume resources.</p>"
        "<p class=\"small\">Use the same population and window. Zero successes has no finite cost per success.</p>`;break;\n"
        " case 'primer':content+=`<p class=\"lead\">Three signals. One cafe order.</p>`+rows(s)"
        "+`<p class=\"small\">Run the primer, then ask which span dominated the slow order.</p>`;break;\n"
        " case 'lab':content+=`<p class=\"lead\">Confirm the room can run before demos.</p>`+rows(s)"
        "+`<p class=\"small\">Stop and fix .env if preflight fails.</p>`;break;\n"
        " case 'code':content+=`<p class=\"lead\">Code with evidence from the run you just saw.</p>`+rows(s)"
        "+`<p class=\"small\">spans.py first · runtime/store after the latency lab</p>`;break;\n"
        " case 'langsmith':content+=`<div class=\"split\" style=\"margin-top:20px\">"
        "<div class=\"comparison\"><span class=\"tag\">LOCAL TRACES</span>"
        "<p class=\"lead\">Job lifecycle<br>queue → worker → validate</p></div>"
        "<div class=\"comparison\"><span class=\"tag\">LANGSMITH</span>"
        "<p class=\"lead\">LLM and tool<br>call detail</p></div></div>`+rows(s)"
        "+`<p class=\"small\">Open LangSmith only after lab 01 has produced a run. IDs are not automatically equal.</p>`;break;\n"
        " default:content+=rows(s);"
    )
    if alt:
        return html[: alt.start()] + insert + html[alt.end() :]
    if needle in html:
        return html.replace(needle, insert, 1)
    raise SystemExit("render switch needle not found")


def patch_chrome(text: str, slide_count: int, end_minute: int) -> str:
    text = re.sub(r"\d+-slide spoken script", f"{slide_count}-slide spoken script", text)
    text = re.sub(r"\d+-slide", f"{slide_count}-slide", text, count=3)
    text = re.sub(
        r"\d+ minutes of scripted teaching",
        f"{end_minute} minutes of scripted teaching",
        text,
    )
    return text


def refresh_lab_outputs(slides: list[dict]) -> None:
    """Re-capture recorded outputs so slide Recorded buttons match current scripts."""
    lab_scripts = {
        "00": "scripts/00_preflight.py",
        "primer": "scripts/00a_telemetry_primer.py",
        "01": "scripts/01_opening_demo.py",
        "02": "scripts/02_trace_lab.py",
        "03": "scripts/03_dashboard_lab.py",
        "04": "scripts/04_quality_lab.py",
        "05": "scripts/05_cost_lab.py",
        "06": "scripts/06_slo_alert_lab.py",
        "07": "scripts/07_hygiene_lab.py",
    }
    cache: dict[str, str] = {}
    for s in slides:
        lab = s.get("lab")
        if not lab or lab not in lab_scripts:
            continue
        if lab not in cache:
            cache[lab] = capture_script(lab_scripts[lab])
        s["output"] = cache[lab]


def write_demo_cheatsheet(slides: list[dict]) -> None:
    core = sum(s["minutes"] for s in slides if not s.get("optional"))
    full = slides[-1]["end"]
    lines = [
        "# Demo cues — generated from interactive-slides.html",
        "",
        "Working folder: `Session-Observability/`",
        "Learner card: `LEARNER-FOLLOW-ALONG.md`",
        "Speaker script: `speaker-script.html` (word-for-word with slide `say` / `show` / `ask`)",
        "",
        f"**Core ~{core} min** (skip stretch) · **full ~{full} min**",
        "",
        "| Clock | Slide | Command / action | Title |",
        "|---|---|---|---|",
    ]
    for s in slides:
        clock = f"{s['start']:02d}–{s['end']:02d}"
        if s.get("lab"):
            action = f"`python3 run_lab.py {s['lab']}`"
        elif s.get("optional"):
            action = "Stretch — skip if behind"
        else:
            action = "—"
        flag = " *(stretch)*" if s.get("optional") else ""
        lines.append(f"| {clock} | {s['n']} | {action} | {s['title']}{flag} |")

    stretch = [f"{s['n']} {s['title']}" for s in slides if s.get("optional")]
    lines += [
        "",
        "## Stretch (skip if behind)",
        "",
        " · ".join(stretch) if stretch else "(none)",
        "",
        "## Docker (after local story)",
        "",
        "```bash",
        "docker compose up --build",
        "python scripts/docker_opening_demo.py",
        "```",
        "",
    ]
    (ROOT / "DEMO-CHEATSHEET.md").write_text("\n".join(lines), encoding="utf-8")


def write_learner_card(slides: list[dict]) -> None:
    lab_rows = []
    step = 0
    notes = {
        "00": "Preflight OK before demos",
        "primer": "log vs metric vs slow `cafe.grind` span",
        "01": "both `completed`; only one is a good customer outcome",
        "02": "tool-heavy vs model-heavy latency",
        "03": "completed vs validated",
        "04": "citation without supporting evidence",
        "05": "success with a budget failure",
        "06": "alert → next action",
        "07": "redacted field vs raw export sibling",
    }
    ordered_labs = []
    for s in slides:
        if s.get("lab"):
            ordered_labs.append(s["lab"])

    lines = [
        "# Learner follow-along",
        "",
        "Generated to match `interactive-slides.html` and `speaker-script.html`.",
        "",
        "Work from: `Session-Observability/`",
        "",
        "```bash",
        "cd Session-Observability",
        "source .venv/bin/activate   # or: python3 -m venv .venv && pip install -r requirements.txt",
        "cp -n .env.example .env     # add OPENAI_API_KEY / LANGSMITH_* if using live paths",
        "```",
        "",
        "## Run in this order (with the instructor)",
        "",
        "| Step | Command | What you should notice |",
        "|---|---|---|",
    ]
    step = 0
    for lab in ordered_labs:
        lines.append(f"| {step} | `python3 run_lab.py {lab}` | {notes.get(lab, 'Follow the slide')} |")
        step += 1
        if lab == "primer":
            lines.append(
                f"| {step} | *(watch)* agent flow on slides | accept → queue → worker → validate |"
            )
            step += 1
        if lab == "01":
            lines.append(
                f"| {step} | *(Source)* `spans.py` | nested `with span()` ↔ parent/child |"
            )
            step += 1
            lines.append(
                f"| {step} | *(optional)* LangSmith UI | same questions; different ID than local `trace_id` |"
            )
            step += 1
        if lab == "02":
            lines.append(
                f"| {step} | *(Source)* `runtime.py` → `store.py` | finish code walk after latency diagnosis |"
            )
            step += 1

    stretch = [s["title"] for s in slides if s.get("optional")]
    lines += [
        "",
        "Also useful: `python3 run_lab.py all` · `python3 run_lab.py tests`",
        "",
        "## Do not",
        "",
        "- Open LangSmith before lab `01` (nothing to inspect yet)",
        "- Skip preflight if you plan to run live labs",
        "- Treat `status=completed` as “the customer was helped”",
        "",
        "## Stretch (skip if short on time)",
        "",
        " · ".join(stretch),
        "",
        "Docker (after the local story):",
        "",
        "```bash",
        "docker compose up --build",
        "python scripts/docker_opening_demo.py",
        "```",
        "",
    ]
    (ROOT / "LEARNER-FOLLOW-ALONG.md").write_text("\n".join(lines), encoding="utf-8")


def write_telemetry_primer_card(slide: dict) -> None:
    """Keep TELEMETRY-PRIMER.md ask/answer/transition aligned with the primer slide."""
    path = ROOT / "TELEMETRY-PRIMER.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    ask = slide.get("ask") or ""
    answer = slide.get("answer") or ""
    # Rewrite the card from the slide so it cannot drift
    path.write_text(
        "\n".join(
            [
                "# Telemetry primer — read aloud (~5 minutes)",
                "",
                "Aligned with slide **Telemetry primer: three signals**.",
                "Run **after** preflight (`python3 run_lab.py 00`), **before** the agent sketch and lab `01`.",
                "",
                "```bash",
                "cd Session-Observability",
                "python3 run_lab.py primer",
                "# or: python scripts/00a_telemetry_primer.py",
                "```",
                "",
                "---",
                "",
                "## SHOW",
                "",
                slide.get("show") or "Run python3 run_lab.py primer.",
                "",
                "## SAY",
                "",
                (slide.get("say") or "").strip(),
                "",
                "## RUN",
                "",
                "`python3 run_lab.py primer`",
                "",
                "## ASK",
                "",
                ask,
                "",
                "## EXPECTED RESPONSE",
                "",
                answer,
                "",
                "## Transition",
                "",
                "Deck order after this card: **agent flow → `python3 run_lab.py 01` → spans → LangSmith**.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def verify_alignment(slides: list[dict]) -> None:
    speaker = SPEAKER_HTML.read_text(encoding="utf-8")
    issues: list[str] = []
    for s in slides:
        n = s["n"]
        if f'id="s{n}"' not in speaker:
            issues.append(f"missing speaker section s{n}")
        title = html_lib.escape(s["title"])
        if title not in speaker:
            issues.append(f"title missing in speaker: {s['title']}")
        clock = f"{s['start']:02d}–{s['end']:02d}"
        if clock not in speaker:
            issues.append(f"clock missing in speaker: {clock} ({s['title']})")
        if s.get("lab"):
            cmd = f"python3 run_lab.py {s['lab']}"
            if cmd not in speaker:
                issues.append(f"lab cmd missing in speaker: {cmd}")
        # word-for-word say: first paragraph must appear escaped
        say = (s.get("say") or "").strip()
        if say:
            first = say.split("\n\n")[0]
            if html_lib.escape(first) not in speaker:
                issues.append(f"say drift on slide {n}")
        show = (s.get("show") or "").strip()
        if show and html_lib.escape(show) not in speaker:
            # show may contain newlines
            if html_lib.escape(show.split("\n")[0]) not in speaker:
                issues.append(f"show drift on slide {n}")
    if issues:
        raise SystemExit("alignment check failed:\n- " + "\n- ".join(issues))


def main() -> int:
    data, prefix, suffix = load_data()
    primer_output = capture_script("scripts/00a_telemetry_primer.py")
    preflight_output = capture_script("scripts/00_preflight.py")
    ids = capture_ids_sample()

    slides = rebuild_slides(
        data,
        primer_output=primer_output,
        preflight_output=preflight_output,
        ids=ids,
    )
    refresh_lab_outputs(slides)
    data["slides"] = slides
    ensure_sources(data)

    html = prefix + json.dumps(data, ensure_ascii=False) + suffix
    html = patch_chrome(html, len(slides), slides[-1]["end"])
    html = patch_render_kinds(html)
    SLIDES_HTML.write_text(html, encoding="utf-8")
    SPEAKER_HTML.write_text(render_speaker(slides), encoding="utf-8")

    write_demo_cheatsheet(slides)
    write_learner_card(slides)
    primer_slide = next(s for s in slides if s.get("lab") == "primer")
    write_telemetry_primer_card(primer_slide)
    verify_alignment(slides)

    core = sum(s["minutes"] for s in slides if not s.get("optional"))
    print(f"slides={len(slides)} full={slides[-1]['end']} core_without_stretch={core}")
    print("alignment: OK (slides ↔ speaker ↔ docs)")
    for s in slides[:14]:
        flag = " stretch" if s.get("optional") else ""
        print(f"{s['n']:02d} {s['start']:02d}-{s['end']:02d}{flag} {s['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
