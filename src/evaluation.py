"""Benchmark verification, automatic Hit@1 / Evidence Hit@3 scoring and aggregation.

Hit definition (GUIDE.md): a retrieved chunk is a hit when it belongs to a gold
(source_id, page) AND contains the FULL evidence quote (whitespace/case-insensitive).
Human labels (coherence, grounding) are NOT inferred here; see results/manual_*.csv.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

from . import config


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def load_questions() -> list[dict[str, Any]]:
    with config.QUESTIONS_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_benchmark(pages) -> dict[str, Any]:
    """Check every gold evidence quote exists on its gold page and filters are valid."""
    by_key = {(p.document_id, p.page): p for p in pages}
    qs = load_questions()
    problems = []
    for q in qs:
        for g in q["gold"]:
            p = by_key.get((g["source_id"], g["page"]))
            if p is None:
                problems.append(f"{q['id']}: gold page {g['source_id']} p{g['page']} not found")
            elif norm_ws(g["evidence_quote"]) not in norm_ws(p.text):
                problems.append(f"{q['id']}: evidence not on {g['source_id']} p{g['page']}")
        if q.get("filter"):
            for k, v in q["filter"].items():
                docs = {p.document_id for p in pages if str(p.metadata.get(k)) == str(v)}
                if not docs:
                    problems.append(f"{q['id']}: filter {k}={v} matches no page")
                elif len(docs) < 2:
                    problems.append(f"{q['id']}: filter {k}={v} selects a single document (leaks gold)")
                if not any(g["source_id"] in docs for g in q["gold"]):
                    problems.append(f"{q['id']}: filter {k}={v} excludes the gold source")
    split = Counter(q["split"] for q in qs)
    filt = Counter(q["split"] for q in qs if q.get("filter"))
    return {"n_questions": len(qs), "split": dict(split), "filter_questions": dict(filt),
            "types": dict(Counter(q["type"] for q in qs)), "problems": problems}


def chunk_hits(question: dict[str, Any], hit: dict[str, Any]) -> bool:
    text = norm_ws(hit["text"])
    md = hit["metadata"]
    for g in question["gold"]:
        if md["document_id"] == g["source_id"] and int(md["page"]) == int(g["page"]) \
                and norm_ws(g["evidence_quote"]) in text:
            return True
    return False


def partial_evidence(question: dict[str, Any], hit: dict[str, Any]) -> bool:
    """Gold page retrieved but evidence only partially inside the chunk (split evidence)."""
    md = hit["metadata"]
    text = norm_ws(hit["text"])
    for g in question["gold"]:
        if md["document_id"] == g["source_id"] and int(md["page"]) == int(g["page"]):
            words = norm_ws(g["evidence_quote"]).split()
            head, tail = " ".join(words[:4]), " ".join(words[-4:])
            if (head in text) != (tail in text) or (head in text and tail in text
                                                    and norm_ws(g["evidence_quote"]) not in text):
                return True
    return False


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    flags = [chunk_hits(question, h) for h in hits]
    gold_pages = {(g["source_id"], g["page"]) for g in question["gold"]}
    page_flags = [(h["metadata"]["document_id"], int(h["metadata"]["page"])) in gold_pages for h in hits]
    filt = question.get("filter")
    compliant = None
    if filt:
        compliant = all(all(str(h["metadata"].get(k)) == str(v) for k, v in filt.items()) for h in hits)
    return {
        "hit_flags": flags,
        "hit1": bool(flags and flags[0]),
        "hit3": any(flags),
        "gold_page_in_top3": any(page_flags),
        "split_evidence": any(partial_evidence(question, h) for h in hits) and not any(flags),
        "filter_compliant_top3": compliant,
    }


def summarize(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: Counter())
    for t in traces:
        for split in (t["split"], "all"):
            c = agg[(t["strategy"], split)]
            c["N"] += 1
            c["hit1"] += int(t["eval"]["hit1"])
            c["hit3"] += int(t["eval"]["hit3"])
            c["gold_page3"] += int(t["eval"]["gold_page_in_top3"])
            if t["filter_applied"]:
                c["filter_q"] += 1
                c["filter_ok"] += int(bool(t["eval"]["filter_compliant_top3"]))
            if t["question_has_filter"]:
                c["filter_q_any"] += 1
                c["filter_ok_any"] += int(bool(t["eval"]["filter_compliant_top3"]))
    rows = []
    for (strategy, split), c in sorted(agg.items()):
        rows.append({
            "strategy": strategy, "split": split, "N": c["N"],
            "hit1": c["hit1"], "hit3": c["hit3"],
            "hit1_rate": round(c["hit1"] / c["N"], 3), "hit3_rate": round(c["hit3"] / c["N"], 3),
            "gold_page_in_top3": c["gold_page3"],
            "filter_compliance": f"{c['filter_ok_any']}/{c['filter_q_any']}" if c["filter_q_any"] else "N/A",
        })
    return rows
