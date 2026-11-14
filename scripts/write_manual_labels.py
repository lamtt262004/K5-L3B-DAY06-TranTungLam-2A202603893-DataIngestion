"""Write the manual audit labels (coherence, grounding, metadata) to results/manual/*.csv.

Labels were assigned by reading every sampled chunk / top-3 record (see report for
method and bias). This script only stores them next to the exported samples so the
grader can see sample, label and reason side by side. Run after `python -m src.run audit`.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "results" / "manual"
LABELER = "Trần Tùng Lâm (có hỗ trợ AI, đã rà soát; xem báo cáo)"

COHERENCE = {
    (1, "A"): (1, "Bắt đầu giữa câu ('n GitHub <...>`__.'), kết thúc cắt giữa câu ('...coordination problems'); đoạn PEP Audience ở giữa đọc được."),
    (1, "B"): (2, "Trọn mục 'PEP Audience' từ heading đến hết đoạn; tự hiểu được."),
    (2, "A"): (1, "Bắt đầu giữa mục Rationale ('describing why...'), kết thúc giữa câu mục 6 ('...incompatibilities and the')."),
    (2, "B"): (1, "Gồm trọn các mục 2-5 của danh sách nhưng thiếu câu dẫn của danh sách (nằm ở trang trước)."),
    (3, "A"): (1, "Mất chủ ngữ của quy tắc chính ('...s with two blank lines' - thiếu 'Surround top-level function and class definitions'), cắt cuối giữa câu."),
    (3, "B"): (2, "Trọn mục 'Blank Lines' kèm heading; mọi câu đầy đủ."),
    (4, "A"): (1, "Bắt đầu giữa bullet ('implementation behind simple data attribute access syntax'), kết thúc cắt giữa từ ('double le')."),
    (4, "B"): (1, "Bullet đầy đủ, nhưng câu mở 'With this in mind' tham chiếu ngữ cảnh trước; Note 2 bị tách sang chunk sau."),
    (5, "A"): (1, "Ví dụ f-string còn nguyên nhưng đầu chunk cắt giữa câu ('with 'f', which...'), cuối cắt 'A simi'."),
    (5, "B"): (2, "Ví dụ code trọn vẹn + đoạn về PEP 215 đầy đủ; tự hiểu được dù câu dẫn 'Some examples are::' ở chunk trước."),
    (6, "A"): (1, "Dòng code cụt ở đầu, sau đó là danh sách References; mục cuối bị cắt ('Formatting')."),
    (6, "B"): (2, "Trọn danh sách References kèm heading; mỗi mục đầy đủ."),
    (7, "A"): (1, "Cắt giữa từ ở đầu ('cified on the call to replace') và cuối ('init=F'); câu về ValueError ở giữa còn nguyên."),
    (7, "B"): (1, "Bắt đầu giữa ví dụ make_dataclass (thiếu câu giới thiệu); phần replace() đầy đủ, kết thúc trọn câu."),
    (8, "A"): (0, "Bắt đầu giữa chuỗi ví dụ INVALID, 'this restriction' không có chủ thể, kết thúc cắt giữa câu ('no additional re') - khó hiểu nếu đứng riêng."),
    (8, "B"): (1, "Các đoạn đầy đủ nhưng câu đầu 'this restriction applies solely to...' tham chiếu quy tắc ở chunk trước."),
    (9, "A"): (1, "Bắt đầu giữa từ ('dings, including...'), kết thúc bằng mẩu heading mục sau ('Style guide recommendations ... can sometimes be u')."),
    (9, "B"): (2, "Trọn tiểu mục 'Why not use a sublocal scope...' từ heading đến hết."),
    (10, "A"): (1, "Câu đầu mất chủ ngữ ('not equal to the number of subpatterns'), kết thúc cắt giữa câu; các câu giữa đầy đủ."),
    (10, "B"): (2, "Bắt đầu bằng câu định nghĩa trọn vẹn 'For a sequence pattern to succeed...', kết thúc trọn câu."),
}

GROUNDING = {
    ("t01", "A"): (2, "A1 chứa trọn quy tắc Constants (chữ hoa, gạch dưới) - đủ trả lời, truy về pep-0008 p15."),
    ("t01", "B"): (2, "B1 là trọn mục Constants kèm ví dụ MAX_OVERFLOW, TOTAL."),
    ("t02", "A"): (0, "Không chunk nào chứa quy tắc ':=' kém chặt hơn or/and; A2 thuộc mục 'Lowering operator precedence' - phương án bị bác bỏ, dễ gây hiểu sai."),
    ("t02", "B"): (0, "B2/B3 là mục 'Lowering operator precedence' (rejected), B1 về dấu phẩy; thiếu đoạn 'Relative precedence of :=' (p07)."),
    ("t03", "A"): (0, "Các chunk nói về Rationale / lỗi compile-time; không có câu 'evaluated at run time, not a constant value'."),
    ("t03", "B"): (0, "Chunk Rationale/Specification chung về f-string, không trả lời câu hỏi runtime vs constant."),
    ("t04", "A"): (0, "Chỉ có định nghĩa docstring chung và PEP 8 'Documentation Strings'; không có nội dung class docstring."),
    ("t04", "B"): (2, "B1 (pep-0257 p03) chứa câu 'The docstring for a class should summarize its behavior and list the public methods and instance variables.'"),
    ("t05", "A"): (0, "Chỉ có đoạn dẫn nhập Or patterns (động cơ), không có cú pháp | hay as-pattern."),
    ("t05", "B"): (1, "B3 có cú pháp or pattern '|' (một nửa yêu cầu) nhưng thiếu as-pattern để biết giá trị nào khớp."),
    ("t06", "A"): (2, "A1 chứa trọn quy tắc thứ tự đánh giá guard (first to last, dừng khi đã chọn)."),
    ("t06", "B"): (2, "B1 chứa trọn quy tắc; B2/B3 là tutorial (Informational) - thừa nhưng không mâu thuẫn."),
}
GROUNDING_C_OVERRIDE = {
    "t06": "C1 giống B1 (đủ bằng chứng); C2/C3 đều là PEP 634 Standards Track - không còn chunk tutorial.",
}


def main() -> None:
    samples = json.loads((M / "coherence_samples.json").read_text(encoding="utf-8"))
    with (M / "coherence_labels.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["position", "page_id", "char_offset", "strategy", "chunk_id", "section",
                    "chunk_chars", "score_0_2", "reason", "labeler"])
        for r in samples:
            src = "B" if r["strategy"] == "C" else r["strategy"]
            score, why = COHERENCE[(r["position"], src)]
            if r["strategy"] == "C":
                why = "Cùng chunk với B (C dùng lại index B) - nhãn giống B. " + why
            w.writerow([r["position"], r["page_id"], r["char_offset"], r["strategy"], r["chunk_id"],
                        r["section"], r["chunk_chars"], score, why, LABELER])

    traces = [json.loads(l) for l in (ROOT / "results" / "traces_test.jsonl").open(encoding="utf-8")]
    by = {(t["question_id"], t["strategy"]): t for t in traces}
    with (M / "grounding_labels.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "strategy", "top3_chunk_ids", "score_0_2", "reason", "labeler"])
        for q in ["t01", "t02", "t03", "t04", "t05", "t06"]:
            for st in "ABC":
                score, why = GROUNDING[(q, "B" if st == "C" else st)]
                if st == "C":
                    same = [h["chunk_id"] for h in by[(q, "C")]["hits"]] == [h["chunk_id"] for h in by[(q, "B")]["hits"]]
                    why = ("Top-3 trùng B. " + why) if same else GROUNDING_C_OVERRIDE[q]
                ids = " ".join(h["chunk_id"] for h in by[(q, st)]["hits"])
                w.writerow([q, st, ids, score, why, LABELER])

    checks = json.loads((M / "metadata_check_auto.json").read_text(encoding="utf-8"))
    cols = ["strategy", "question_id", "rank", "chunk_id", "document_id", "source", "page", "pep_type",
            "python_version", "section", "text_matches_source_page", "source_page_ok", "filter_fields_ok",
            "section_title_exists", "chunk_spans_new_heading", "filter_applied"]
    with (M / "metadata_labels.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols + ["complete_and_correct", "note"])
        for c in checks:
            hit = by[(c["question_id"], c["strategy"])]["hits"][c["rank"] - 1]
            first = hit["text"].split("\n")[0].strip()
            c["chunk_spans_new_heading"] = bool(re.search(r"\n[=\-~^]{3,}\n", "\n" + hit["text"] + "\n")) \
                and first != c["section"].split(" > ")[-1]
            ok = all(c[k] for k in ("text_matches_source_page", "source_page_ok", "filter_fields_ok",
                                    "section_title_exists"))
            note = ("section = mục tại điểm bắt đầu chunk; chunk chứa thêm heading mục khác nên section "
                    "chỉ mô tả một phần nội dung") if c["chunk_spans_new_heading"] else ""
            w.writerow([c[k] for k in cols] + [ok, note])

    # print summaries
    for st in "AB":
        sc = [COHERENCE[(i, st)][0] for i in range(1, 11)]
        print(f"coherence {st}: {sc} mean={sum(sc)/10:.2f}")
    for st in "AB":
        sc = [GROUNDING[(q, st)][0] for q in ["t01", "t02", "t03", "t04", "t05", "t06"]]
        print(f"grounding {st}: {sc} 0/1/2={sc.count(0)}/{sc.count(1)}/{sc.count(2)} mean={sum(sc)/6:.2f}")


if __name__ == "__main__":
    sys.exit(main())
