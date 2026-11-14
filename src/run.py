"""Pipeline entry point.

    python -m src.run prepare            # read + normalize corpus, manifest, verify benchmark
    python -m src.run ingest [--rebuild] # chunk + embed + store A and B (C reuses B's index)
    python -m src.run evaluate --split dev
    python -m src.run select             # choose strategy from DEV only (pre-registered rule)
    python -m src.run evaluate --split test
    python -m src.run audit              # export samples for manual labelling
    python -m src.run all                # everything above in order
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import statistics
import time
from datetime import datetime, timezone

from . import config
from .chunking import build_chunks
from .evaluation import evaluate_query, load_questions, summarize, verify_benchmark
from .ingestion import build_corpus, load_pages, main as ingest_corpus

R = config.RESULTS_DIR


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_json(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


_ERRORS_THIS_RUN = 0


def _log_error(msg: str) -> None:
    global _ERRORS_THIS_RUN
    _ERRORS_THIS_RUN += 1
    R.mkdir(parents=True, exist_ok=True)
    with (R / "errors.log").open("a", encoding="utf-8") as f:
        f.write(f"{_now()} {msg}\n")
    _log_run(f"ERROR {msg}")


def _log_run(msg: str) -> None:
    """Always-written run log (start/end of every step, errors, provider/model)."""
    R.mkdir(parents=True, exist_ok=True)
    with (R / "run.log").open("a", encoding="utf-8") as f:
        f.write(f"{_now()} {msg}\n")


def cmd_prepare(_args) -> None:
    ingest_corpus()
    report = verify_benchmark(load_pages())
    report["checked_at"] = _now()
    _write_json(R / "benchmark_verification.json", report)
    print(json.dumps(report, indent=1))
    if report["problems"]:
        raise SystemExit("Benchmark verification failed; fix questions before running.")
    manifest = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    for w in manifest["warnings"]:
        _log_error(f"[ingestion] {w}")


def _env_info(embedder) -> dict:
    import chromadb, sentence_transformers, torch, transformers
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "chromadb": chromadb.__version__, "sentence_transformers": sentence_transformers.__version__,
        "transformers": transformers.__version__, "torch": torch.__version__,
        "device": embedder.device, "embed_model": embedder.model_name,
        "dimensions": embedder.dimensions, "max_seq_length": config.EMBED_MAX_SEQ,
        "query_instruction": config.QUERY_INSTRUCTION, "metric": "cosine (hnsw:space=cosine)",
        "search": "approximate (Chroma HNSW index)", "store_path": str(config.CHROMA_DIR.relative_to(config.ROOT)),
        "provider": config.EMBED_PROVIDER,
    }


def cmd_ingest(args) -> None:
    from .embeddings import get_embedder
    from .store import ChromaStore

    pages = load_pages()
    manifest = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    doc_sha = {d["source_id"]: d["sha256"] for d in manifest["documents"]}
    t0 = time.perf_counter()
    embedder = get_embedder()
    load_time = time.perf_counter() - t0
    store = ChromaStore(dimensions=embedder.dimensions)
    stats = {"run_at": _now(), "env": _env_info(embedder), "model_load_s": round(load_time, 2),
             "strategies": {}}

    done_collections = {}
    for name, spec in config.STRATEGIES.items():
        coll = spec["collection"]
        if coll in done_collections:
            stats["strategies"][name] = {**stats["strategies"][done_collections[coll]],
                                         "note": f"re-uses index of strategy {done_collections[coll]}; "
                                                 f"only adds metadata filter at query time"}
            continue
        if args.rebuild:
            store.drop(coll)
        col = store.collection(coll, embedder.model_name)
        chunks = build_chunks(pages, spec)
        inputs = {c.chunk_id: embedder.doc_input(c) for c in chunks}
        tokens = embedder.count_tokens(list(inputs.values()))
        truncated = sum(t > config.EMBED_MAX_SEQ for t in tokens)
        lens = [len(c.text) for c in chunks]

        def vec_fn(cs):
            return embedder.embed_documents([inputs[c.chunk_id] for c in cs])

        counts = {"added": 0, "deleted": 0, "skipped": 0}
        t1 = time.perf_counter()
        by_doc: dict[str, list] = {}
        for c in chunks:
            by_doc.setdefault(c.document_id, []).append(c)
        for doc_id, cs in by_doc.items():
            r = store.upsert_document(col, doc_id, doc_sha[doc_id], cs, vec_fn)
            for k in counts:
                counts[k] += r[k]
        elapsed = time.perf_counter() - t1
        if truncated:
            _log_error(f"[ingest {name}] {truncated} chunk inputs exceed {config.EMBED_MAX_SEQ} tokens (truncated)")
        stats["strategies"][name] = {
            "collection": coll, "params": spec, "chunk_count": len(chunks),
            "collection_count_after": col.count(),
            "chars_total": sum(lens), "chars_min": min(lens), "chars_median": statistics.median(lens),
            "chars_mean": round(statistics.mean(lens), 1), "chars_max": max(lens),
            "embed_tokens_total": sum(tokens), "embed_tokens_max": max(tokens),
            "inputs_truncated": truncated,
            "ingest_seconds": round(elapsed, 2), **counts,
            "cost_usd_cumulative": getattr(embedder, "cost_usd", lambda: 0.0)(),
        }
        done_collections[coll] = name
        print(f"[{name}] chunks={len(chunks)} count={col.count()} {counts} {elapsed:.1f}s")
        # export chunks for inspection (text + metadata)
        with (R / f"chunks_{name}.jsonl").open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps({"chunk_id": c.chunk_id, "document_id": c.document_id,
                                    "page": c.page, "metadata": c.metadata, "text": c.text},
                                   ensure_ascii=False) + "\n")
    tag = "reingest" if not args.rebuild and getattr(args, "tag", None) == "reingest" else "ingest"
    _write_json(R / f"{tag}_stats.json", stats)


def cmd_evaluate(args) -> None:
    from .embeddings import get_embedder
    from .store import ChromaStore

    split = args.split
    if split == "test" and not (R / "selection.json").exists():
        raise SystemExit("Run `select` on dev before evaluating test.")
    questions = [q for q in load_questions() if q["split"] == split]
    embedder = get_embedder()
    store = ChromaStore(dimensions=embedder.dimensions)
    traces = []
    t0 = time.perf_counter()
    for name, spec in config.STRATEGIES.items():
        col = store.collection(spec["collection"], embedder.model_name)
        if col.count() == 0:
            raise SystemExit(f"Collection {spec['collection']} empty; run ingest first.")
        for q in questions:
            apply_filter = bool(spec["use_filter"] and q.get("filter"))
            qv = embedder.embed_query(q["question"])
            tq = time.perf_counter()
            hits = store.search(col, qv, config.TOP_K, q["filter"] if apply_filter else None)
            latency = time.perf_counter() - tq
            if len(hits) < config.TOP_K:
                _log_error(f"[evaluate {name}] {q['id']} returned {len(hits)} < {config.TOP_K} hits")
            ev = evaluate_query(q, hits)
            traces.append({
                "strategy": name, "split": split, "question_id": q["id"], "type": q["type"],
                "question": q["question"], "query_text_embedded": config.QUERY_INSTRUCTION + q["question"],
                "question_has_filter": bool(q.get("filter")),
                "filter_applied": q["filter"] if apply_filter else None,
                "gold": q["gold"], "expected_answer": q["expected_answer"],
                "hits": [{"rank": i + 1, **h} for i, h in enumerate(hits)],
                "eval": ev, "search_latency_ms": round(latency * 1000, 2),
            })
    elapsed = time.perf_counter() - t0
    out = R / f"traces_{split}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = summarize(traces)
    _write_json(R / f"metrics_{split}.json", {"run_at": _now(), "split": split,
                                               "elapsed_s": round(elapsed, 2), "rows": summary})
    with (R / f"metrics_{split}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    # per-question hit table
    with (R / f"per_question_{split}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "type", "strategy", "filter_applied", "hit1", "hit3",
                    "gold_page_in_top3", "split_evidence", "top1_chunk", "top1_score"])
        for t in traces:
            w.writerow([t["question_id"], t["type"], t["strategy"], json.dumps(t["filter_applied"]),
                        int(t["eval"]["hit1"]), int(t["eval"]["hit3"]), int(t["eval"]["gold_page_in_top3"]),
                        int(t["eval"]["split_evidence"]), t["hits"][0]["chunk_id"], t["hits"][0]["score"]])
    for r in summary:
        print(f"{r['strategy']} {r['split']:4s} Hit@1 {r['hit1']}/{r['N']}  Hit@3 {r['hit3']}/{r['N']}  "
              f"filter {r['filter_compliance']}")


def cmd_select(_args) -> None:
    rows = json.loads((R / "metrics_dev.json").read_text(encoding="utf-8"))["rows"]
    stats = json.loads((R / "ingest_stats.json").read_text(encoding="utf-8"))["strategies"]
    dev = [r for r in rows if r["split"] == "dev"]
    # pre-registered rule: Hit@3 dev, then Hit@1 dev, then fewer chunks
    ranked = sorted(dev, key=lambda r: (-r["hit3"], -r["hit1"], stats[r["strategy"]]["chunk_count"]))
    sel = {"selected_at": _now(), "rule": "max dev Evidence Hit@3 -> max dev Hit@1 -> fewer chunks",
           "ranking": [{k: r[k] for k in ("strategy", "hit1", "hit3", "N")} for r in ranked],
           "selected": ranked[0]["strategy"],
           "frozen_config": config.STRATEGIES[ranked[0]["strategy"]]}
    _write_json(R / "selection.json", sel)
    print(json.dumps(sel, indent=1))


def cmd_audit(_args) -> None:
    """Export samples for manual labelling (coherence positions fixed in advance)."""
    pages = sorted(load_pages(), key=lambda p: p.page_id)
    # 10 positions chosen BEFORE looking at scores: every 11th page in sorted order,
    # character offset at the middle of that page.
    positions = [(pages[i].page_id, len(pages[i].text) // 2) for i in range(0, 110, 11)]
    chunks = {}
    for name in ("A", "B"):
        with (R / f"chunks_{name}.jsonl").open(encoding="utf-8") as f:
            chunks[name] = [json.loads(l) for l in f]
    rows = []
    for k, (pid, off) in enumerate(positions, start=1):
        for name in ("A", "B", "C"):
            src = "B" if name == "C" else name
            cand = [c for c in chunks[src] if c["metadata"]["page_id"] == pid
                    and c["metadata"]["char_start"] <= off < c["metadata"]["char_end"]]
            c = cand[0]  # for A with overlap, the first window that covers the position
            rows.append({"position": k, "page_id": pid, "char_offset": off, "strategy": name,
                         "chunk_id": c["chunk_id"], "section": c["metadata"]["section"],
                         "chunk_chars": c["metadata"]["chunk_chars"], "text": c["text"]})
    _write_json(R / "manual" / "coherence_samples.json", rows)

    # metadata check support: compare every test top-3 record with the source page
    page_by_id = {p.page_id: p for p in pages}
    man = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    doc_meta = {d["source_id"]: d for d in man["documents"]}
    checks = []
    with (R / "traces_test.jsonl").open(encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            for h in t["hits"]:
                md = h["metadata"]
                p = page_by_id.get(md["page_id"])
                text_ok = p is not None and p.text[md["char_start"]:md["char_end"]].strip() == h["text"]
                src_ok = p is not None and md["source"] == p.source and md["document_id"] == p.document_id \
                    and int(md["page"]) == p.page
                d = doc_meta[md["document_id"]]
                type_ok = md["pep_type"] == d["pep_type"] and md["python_version"] == d["python_version"]
                sec_ok = p is not None and md["section"].split(" > ")[-1] in p.text or md["section"] == "(preamble)" \
                    or md["section"].split(" > ")[-1] in _full_doc_titles(pages, md["document_id"])
                checks.append({"strategy": t["strategy"], "question_id": t["question_id"], "rank": h["rank"],
                               "chunk_id": h["chunk_id"], "document_id": md["document_id"],
                               "source": md["source"], "page": md["page"], "pep_type": md["pep_type"],
                               "python_version": md["python_version"], "section": md["section"],
                               "text_matches_source_page": text_ok, "source_page_ok": src_ok,
                               "filter_fields_ok": type_ok, "section_title_exists": sec_ok,
                               "filter_applied": json.dumps(t["filter_applied"])})
    _write_json(R / "manual" / "metadata_check_auto.json", checks)
    print(f"coherence samples: {len(rows)}; metadata records: {len(checks)}")


_title_cache: dict[str, set] = {}


def _full_doc_titles(pages, doc_id):
    if doc_id not in _title_cache:
        titles = set()
        for p in pages:
            if p.document_id == doc_id:
                for _, path in p.headings:
                    titles.update(path.split(" > "))
        _title_cache[doc_id] = titles
    return _title_cache[doc_id]


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    p = sub.add_parser("ingest")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--tag", default="ingest")
    p = sub.add_parser("evaluate")
    p.add_argument("--split", choices=["dev", "test"], required=True)
    sub.add_parser("select")
    sub.add_parser("audit")
    sub.add_parser("all")
    args = ap.parse_args()
    R.mkdir(parents=True, exist_ok=True)
    if args.cmd == "all":  # fresh full run -> fresh logs
        (R / "run.log").write_text("", encoding="utf-8")
        (R / "errors.log").write_text("", encoding="utf-8")
    (R / "errors.log").touch()  # empty file = no error recorded
    _log_run(f"START cmd={args.cmd} provider={config.EMBED_PROVIDER} "
             f"model={config.OPENAI_EMBED_MODEL if config.EMBED_PROVIDER == 'openai' else config.EMBED_MODEL} "
             f"python={platform.python_version()}")
    try:
        if args.cmd == "all":
            cmd_prepare(args)
            args.rebuild, args.tag = True, "ingest"
            cmd_ingest(args)
            args.rebuild, args.tag = False, "reingest"
            cmd_ingest(args)
            for split in ("dev",):
                args.split = split
                cmd_evaluate(args)
            cmd_select(args)
            args.split = "test"
            cmd_evaluate(args)
            cmd_audit(args)
        else:
            {"prepare": cmd_prepare, "ingest": cmd_ingest, "evaluate": cmd_evaluate,
             "select": cmd_select, "audit": cmd_audit}[args.cmd](args)
    except Exception as e:  # never silently fall back: log and re-raise
        _log_error(f"[{args.cmd}] {type(e).__name__}: {e}")
        _log_run(f"END cmd={args.cmd} status=FAILED")
        raise
    _log_run(f"END cmd={args.cmd} status=OK errors_logged={_ERRORS_THIS_RUN}")


if __name__ == "__main__":
    main()
