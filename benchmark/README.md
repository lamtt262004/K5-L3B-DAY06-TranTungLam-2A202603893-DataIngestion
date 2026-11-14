# Benchmark — 28 câu (22 dev / 6 test)

File: [questions.jsonl](questions.jsonl). Viết và chia split **trước khi chạy bất kỳ truy xuất nào** (2026-11-14), sau khi đã chuẩn hóa corpus thành `data/pages.jsonl`.

## Trường dữ liệu

Theo BENCHMARK.md: `id`, `split`, `type` (direct / paraphrase / conditional / metadata_filter), `question`, `expected_answer`,
`gold_source_id`, `gold_page`, `evidence_quote` (gold chính), `filter` (hoặc `null`), `filter_context`.
Thêm `gold` = danh sách mọi `{source_id, page, evidence_quote}` hợp lệ (gồm cả gold chính); khi chấm, chunk khớp **bất kỳ** gold nào trong danh sách đều được tính hit. Chỉ d12, d20, d21 có nhiều hơn 1 gold.
`gold_page` = số thứ tự đơn vị nội dung trong tài liệu (xem `data/manifest.json`, page_id = `<source_id>-pNN`).
Ghi chú: 3 trường `gold_source_id`/`gold_page`/`evidence_quote` được tách ra ở cấp ngoài sau khi chạy để đúng tên trường của đề; nội dung câu hỏi, đáp án và gold không thay đổi (script kiểm tra so sánh trước/sau).

## Phân bố

| | dev | test |
|---|---:|---:|
| Tổng | 22 | 6 |
| Có metadata filter | 4 (d19–d22) | 2 (t05, t06) |
| Loại câu | direct 6, paraphrase 5, conditional 7, filter 4 | direct 2, paraphrase 1, conditional 1, filter 2 |

Filter dùng hai trường lấy từ header PEP: `pep_type` (Process / Informational / Standards Track) và `python_version` (3.6 / 3.7 / 3.8 / 3.10 / n/a).
Filter là **input giả định do người dùng cung cấp trước khi truy xuất** (vd: "tôi chỉ muốn đọc PEP Informational"), không phải gold source. Script kiểm tra mỗi giá trị filter phủ **≥ 2 tài liệu** (không lọc trùng đúng 1 gold document) và không loại gold.

## Cách chia dev/test và nguy cơ rò rỉ

Chia theo **chủ đề/mục** chứ không theo tài liệu (corpus chỉ có 8 PEP; tách theo tài liệu sẽ làm test chỉ phủ 1–2 PEP). Câu test hỏi về mục khác với mọi câu dev (naming constants, precedence của `:=`, f-string runtime, class docstring, as-pattern, thứ tự guard).
**Rò rỉ có thể có:** t06 (guard) cùng trang `pep-0634-p03` với d16 (irrefutable); t04 cùng trang `pep-0257-p03` với d09. Chiến lược không được tinh chỉnh trên các trang này, nhưng người chấm nên biết.

## Kiểm chứng evidence

`python -m src.run prepare` (gọi `evaluation.verify_benchmark`) kiểm tra từng `evidence_quote` có nằm nguyên văn (so sánh sau khi gộp khoảng trắng, không phân biệt hoa thường) trong text đã chuẩn hóa của trang gold. Kết quả lần chạy: 28/28 hợp lệ, 0 lỗi (`results/benchmark_verification.json`). Tôi đã đọc lại thủ công đáp án và evidence trên text nguồn.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

1. Evidence Hit@3 trên **dev** cao nhất.
2. Hòa → Hit@1 trên dev.
3. Hòa → grounding/coherence (ưu tiên chunk tự hiểu được), rồi tài nguyên (số chunk, thời gian ingest).

Test chỉ chạy **một lần** sau khi cố định cấu hình; không sửa cấu hình/benchmark dựa trên test.
