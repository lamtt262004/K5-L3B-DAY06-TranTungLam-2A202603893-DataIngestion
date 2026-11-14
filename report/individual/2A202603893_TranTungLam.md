# Báo cáo cá nhân — Day 6

Họ tên: Trần Tùng Lâm, MSSV: 2A202603893, lớp: L3B. Ngày chạy: 2026-11-14. Lệnh tái lập: `python -m src.run all` (xem [README](../../README.md))

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** Corpus là kho tri thức về quy ước và tính năng Python, gồm 8 PEP: PEP 1 (quy trình PEP), 8 (style guide), 257 (docstring), 498 (f-string), 557 (dataclasses), 572 (`:=`), 634 (đặc tả pattern matching), 636 (tutorial pattern matching). Nguồn là `github.com/python/peps`, snapshot commit `2ace2311c6a4…`, truy cập 2026-11-14. Quyền sử dụng: mỗi file có tuyên bố *"placed in the public domain"* hoặc *"public domain or CC0-1.0-Universal"* ở mục Copyright. Script đọc và ghi tuyên bố này vào `license_or_permission`; file nào không có tuyên bố sẽ bị loại. File gốc là `.rst`, **không có phân trang**, nên theo GUIDE mỗi tài liệu được chia tuần tự tại ranh giới đoạn (dòng trống) thành các đơn vị ≥2.000 ký tự. Phần đuôi <1.500 ký tự được gộp vào đơn vị trước, nên **mọi đơn vị ≥1.500 ký tự** (nhỏ nhất 1.838). Kết quả là **115 đơn vị nội dung** từ 252.339 ký tự đã chuẩn hóa (PEP 1: 18, PEP 8: 22, PEP 257: 4, PEP 498: 12, PEP 557: 16, PEP 572: 22, PEP 634: 10, PEP 636: 11). Không nhân bản dữ liệu. Phần header RFC-822 của PEP được tách ra làm metadata, không tính vào nội dung. [data/manifest.json](../../data/manifest.json) ghi `source_id`, `title`, URL theo commit, giấy phép, `accessed_at`, `sha256`, và với từng đơn vị: `page_id`, `char_start`, `char_end`, số ký tự.
- **Chuẩn hóa, lỗi và giới hạn:** Chuẩn hóa Unicode NFC; thống nhất xuống dòng; tab → 4 dấu cách; bỏ NBSP và zero-width; gộp ≥3 dòng trống. Bỏ các dòng rst không mang nội dung: link target `.. _x:`, `.. code-block::`, `.. image::`, khối Emacs `Local Variables`, tùy chọn directive như `:class: good/bad`. Thông tin "đúng/sai" không bị mất vì PEP 8 đã có comment `# Correct:` / `# Wrong:` trong code. Giữ nguyên code block, cấu trúc heading rst và chú thích. Đọc UTF-8 ở chế độ strict: lỗi mã hóa sẽ làm chương trình dừng. Log: `manifest.warnings` = [], [results/errors.log](../../results/errors.log) rỗng, và [results/run.log](../../results/run.log) ghi `status=OK errors_logged=0`, tức là không có trang rỗng, quá ngắn hay lỗi đọc. Trong quá trình làm, tôi phát hiện và sửa một lỗi offset: block bắt đầu tại ký tự xuống dòng phân cách, khiến `section` bị lệch một heading. Sau khi sửa, kiểm tra tự động cho 0 chunk lệch section. Giới hạn: cú pháp rst như ``` ``code`` ``` và `:pep:` vẫn còn trong text; footnote `[#]_` không được liên kết.
- **Embedding, vector store, metric, lệnh chạy, chi phí:** Model `BAAI/bge-small-en-v1.5` chạy local (sentence-transformers 6.3.0, transformers 5.20.2, torch 2.14.1 CPU), **384 chiều**, `max_seq_length=512`, vector chuẩn hóa L2. Theo model card, query có tiền tố `"Represent this sentence for searching relevant passages: "`, document không có tiền tố. Văn bản đem embed cho mọi chiến lược là `"<title> — <section>\n<chunk text>"`. Token tối đa của một chunk là 429 < 512, nên **không chunk nào bị cắt**. Vector store là **ChromaDB 1.5.9 `PersistentClient`** (`chroma_db/`), `hnsw:space=cosine` (tìm kiếm **xấp xỉ** HNSW), lọc bằng `where` `$eq`. Thời gian: tải model 10.2 s, ingest A 33.0 s, B 37.3 s (CPU), đánh giá 66 truy vấn dev mất 1.3 s. **Chi phí $0.** Thí nghiệm bổ sung với OpenAI `text-embedding-3-small` (1536 chiều) tốn khoảng **$0.0027** (tính từ `usage.total_tokens`). Không dùng pgvector vì máy không có Docker/WSL2; đề cho phép thay bằng Chroma.
- **Metadata:** Mỗi chunk có các trường bắt buộc `document_id`, `source` (đường dẫn file), `page` (số đơn vị) và `page_id`, cùng `char_start`/`char_end` để định vị chính xác trong trang. Trường lọc bổ sung lấy từ header của chính PEP, không đoán: `pep_type` (str: Process / Informational / Standards Track) và `python_version` (str: 3.6 / 3.7 / 3.8 / 3.10 / `n/a` nếu header không có). Ngoài ra có `status`, `created`, `title`, `section` (đường dẫn heading tại điểm đầu chunk) và `doc_sha256`. Lý do chọn: người dùng thường biết mình cần *đặc tả* (Standards Track) hay *hướng dẫn* (Informational/Process), hoặc biết phiên bản Python đang dùng. Mỗi giá trị lọc phủ ≥2 tài liệu (Process: 1, 8; Informational: 257, 636; Standards Track: 498, 557, 572, 634; 3.10: 634, 636), nên filter không trùng với gold source.

## Cấu hình và benchmark

- **A / B / C:**
  - **A:** cửa sổ ký tự cố định 500, overlap 50, nằm trong từng trang (không vắt qua ranh giới trang), không lọc. 606 chunk.
  - **B:** chia theo cấu trúc. Heading rst luôn mở chunk mới và đi kèm đoạn văn sau nó; các đoạn cùng heading được gộp đến tối đa 1.200 ký tự; đoạn quá dài cắt tại cuối câu. Không lọc. 364 chunk.
  - **C:** dùng **chung index với B** (cùng chunk, cùng vector) và thêm `where` theo `pep_type`/`python_version` **chỉ khi câu hỏi có filter** (6/28 câu); 22 câu còn lại chạy không lọc, giống B. Như vậy khác biệt **duy nhất B→C là filter lúc truy vấn**, còn A→B chỉ khác cách chia chunk (cùng model, cùng cách ghép tiêu đề vào văn bản embed, cùng metadata, cùng store).
- **Bộ câu hỏi (≥20):** 28 câu, chia **22 dev / 6 test** trước khi chạy truy xuất: direct 8, paraphrase 6, conditional/exception 8, metadata filter 6 (dev d19–d22, **test t05, t06**). Mỗi câu có `expected_answer`, danh sách gold `{source_id, page, evidence_quote}` (chấp nhận nhiều gold, như d12, d20, d21) và `filter`/`filter_context` (filter là input giả định do người dùng nêu trước). Hàm `verify_benchmark` kiểm tra từng evidence nằm nguyên văn trên trang gold đã chuẩn hóa: **28/28 hợp lệ** ([results/benchmark_verification.json](../../results/benchmark_verification.json)). Dev/test chia theo chủ đề vì corpus chỉ có 8 PEP. Rò rỉ có thể có: t06 cùng trang `pep-0634-p03` với d16, t04 cùng trang `pep-0257-p03` với d09 (ghi trong [benchmark/README.md](../../benchmark/README.md)).
- **Tiêu chí chọn (chốt trước khi xem test):** (1) Evidence Hit@3 trên dev, (2) Hit@1 trên dev, (3) coherence/grounding, rồi đến số chunk. Script `select` ghi [results/selection.json](../../results/selection.json) trước khi chạy `evaluate --split test`. Test chỉ dùng để báo cáo; không tinh chỉnh tham số nào theo test.

## Kết quả

Hit = chunk thuộc đúng (source, page) gold **và** chứa **trọn** evidence (so sánh không phân biệt hoa thường và khoảng trắng).

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian ingest | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 9/22 | 16/22 | 606 | 33.0 s | $0 |
| A | test | 2/6 | 2/6 | 606 | | |
| B | dev | 14/22 | 19/22 | 364 | 37.3 s | $0 |
| B | test | 3/6 | 3/6 | 364 | | |
| C | dev | 14/22 | 19/22 | 364 (index B) | 0 (dùng lại) | $0 |
| C | test | 3/6 | 3/6 | 364 | | |

Thí nghiệm bổ sung với OpenAI `text-embedding-3-small` (cùng chunk, benchmark và quy tắc; [results_openai/](../../results_openai/)): A đạt Hit@1/Hit@3 dev 9/22 và 16/22, test 2/6 và 3/6; B và C đạt dev **16/22 và 19/22**, test 3/6 và **4/6**. Quy tắc chọn trên dev vẫn cho ra B.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0.90 (n=10): 0×1, 1×9, 2×0 | 18/18 | test 2/2, dev 4/4 (không lọc, tình cờ đúng phạm vi) | 4 / 0 / 2 → **0.67** |
| B | 1.60 (n=10): 0×0, 1×4, 2×6 | 18/18 | test **1/2**, dev 4/4 | 2 / 1 / 3 → **1.17** |
| C | 1.60 (n=10, cùng chunk với B) | 18/18 | test **2/2**, dev 4/4 | 2 / 1 / 3 → **1.17** |

Grounding được chấm trên 6 câu test (đề yêu cầu tối thiểu 5).

**Trace, nhãn và cách chọn mẫu:**
- Trace top-3 đầy đủ (câu hỏi, query đã embed, filter, chunk ID, text, score, metadata, gold, đánh giá) nằm trong [results/traces_dev.jsonl](../../results/traces_dev.jsonl) và [results/traces_test.jsonl](../../results/traces_test.jsonl); bảng từng câu ở `results/per_question_*.csv`.
- **Coherence:** 10 vị trí chốt trước khi xem điểm: lấy mỗi trang thứ 11 trong danh sách page_id đã sắp xếp (vị trí 0, 11, …, 99), tại điểm giữa trang; chấm chunk chứa điểm đó. Kết quả trong [results/manual/coherence_labels.csv](../../results/manual/coherence_labels.csv), có lý do cho từng nhãn.
- **Metadata:** 6 câu test × top-3 × 3 chiến lược = 54 bản ghi. Script so khớp text chunk với `page.text[char_start:char_end]`, so source/page/document_id với trang nguồn, so `pep_type`/`python_version` với header, và kiểm tra tiêu đề section có tồn tại; sau đó người chấm đọc lại. Kết quả trong [results/manual/metadata_labels.csv](../../results/manual/metadata_labels.csv).
- **Grounding:** [results/manual/grounding_labels.csv](../../results/manual/grounding_labels.csv).
- **Kiểm tra nạp lại:** [results/reingest_stats.json](../../results/reingest_stats.json) cho thấy nạp lại cùng phiên bản thì bỏ qua 606/364 chunk, số chunk không đổi. [results/reingest_change_check.json](../../results/reingest_change_check.json) mô phỏng tài liệu bị sửa (sha khác, bỏ trang cuối): 16 chunk cũ bị xóa, 10 chunk mới được thêm, 0 ID cũ còn sót, không trùng lặp. Chunk ID có dạng tất định `<page_id>-cNNN`; khi `doc_sha256` hoặc tập ID của một tài liệu thay đổi, toàn bộ chunk cũ của tài liệu đó bị xóa trước khi thêm chunk mới.
- Chạy `all` lần 2 cho top-3 chunk ID giống hệt lần 1 trên cả 84 truy vấn (A/B/C × 28).

## Phân tích và kết luận

- **A → B (chỉ đổi cách chia chunk):** B tăng Hit@1 dev từ 9 lên 14/22 và Hit@3 từ 16 lên 19/22; trên test từ 2/6 lên 3/6. Coherence tăng từ 0.90 lên 1.60: chunk của A hầu như luôn bắt đầu và kết thúc giữa câu, có khi giữa từ (`'double le'`, `'init=F'`), và mất chủ ngữ của quy tắc. Ví dụ d03 / vị trí #3: chunk A bắt đầu bằng `"s with two blank lines"`, mất phần "Surround top-level function and class definitions". Grounding tăng từ 0.67 lên 1.17. Tài nguyên: B có ít chunk hơn (364 so với 606) nhưng ingest lâu hơn một chút (37.3 s so với 33.0 s), vì chunk dài hơn nên tổng token gần bằng (71k so với 82k) mà chi phí attention cho mỗi chunk cao hơn. A có một lợi thế: chunk nhỏ hơn nên đôi khi xếp hạng chính xác hơn, ví dụ d08 và d15 có Hit@1 với A nhưng chỉ Hit@3 với B. Metadata `section` của A kém hữu ích: **13/18** bản ghi top-3 test của A vắt qua heading mới, nên `section` (lấy theo điểm đầu chunk) chỉ mô tả một phần nội dung. Ví dụ t01 A1 có section là "Method Names and Instance Variables" nhưng nội dung chính là "Constants". B có 0/18 bản ghi như vậy.
- **B → C (chỉ thêm filter):** Trên test, độ tuân thủ filter tăng từ 1/2 lên 2/2. Ở t06 ("Standards Track specification… guards"), top-3 của B có 2 chunk tutorial PEP 636 (Informational); C thay bằng 2 chunk PEP 634. Hit@k không đổi trên cả 6 câu filter, vì gold đều đã nằm trong top-3 của B, còn t05 thì cả hai đều miss. Trên dev, top-3 của B đã đúng phạm vi ở cả 4/4 câu filter, nên filter không thay đổi gì. Với corpus nhỏ này, filter chủ yếu làm sạch ngữ cảnh chứ không tăng Hit. Hạn chế: filter chỉ có ích khi người dùng cung cấp đúng phạm vi; lọc sai phạm vi sẽ loại bỏ gold.
- **Ví dụ sai:**
  1. **t02** (gold `pep-0572` p07, mục "Relative precedence of `:=`"): cả A, B, C đều trả về mục *"Lowering operator precedence"* (p15/p16), là **phương án đã bị bác bỏ** trong PEP. Nội dung này nói về "bind more tightly than comparison operators", có thể khiến LLM trả lời sai. Embedding không phân biệt được "đề xuất bị bác bỏ" với "đặc tả". Một metadata kiểu `section_kind=rejected` có thể giúp.
  2. **d06** (gold `pep-0008` p18, quy tắc dùng `def` thay vì gán `lambda`): B và C trả về cả 3 chunk từ PEP 572 (Assignment Expressions), vì câu hỏi có chữ "assigning… to a variable" trùng ngữ nghĩa với chủ đề của PEP 572. A có chunk gold page ở hạng 3 nhưng chunk đó chỉ chứa nửa sau của đoạn, không có câu evidence.
  3. **d20** (filter `python_version=3.10`): mục "Wildcard Pattern" của PEP 634 chỉ khoảng 100 ký tự, nên B tạo ra một chunk rất nhỏ. Chunk này thua chunk "Value Patterns" kế bên. Đây là mặt trái của việc chia theo heading: mục quá ngắn tạo ra chunk thiếu ngữ cảnh (chunk nhỏ nhất của B chỉ 29 ký tự).
- **Chiến lược chọn:** Theo quy tắc chốt trước, **B** được chọn: Hit@3 dev 19/22, Hit@1 14/22. B và C hòa trên mọi tiêu chí dev, và script giữ B do sắp xếp ổn định. Trên thực tế, C chỉ là B cộng thêm filter tùy chọn trên cùng index. Khuyến nghị: dùng index B và **bật filter khi người dùng nêu rõ phạm vi** (C), vì filter không làm giảm Hit mà tăng độ tuân thủ phạm vi. Điều kiện áp dụng: tài liệu có heading rõ ràng như rst/Markdown; nếu là PDF scan không có cấu trúc, lợi thế của B sẽ giảm.
- **Hạn chế:**
  - Test chỉ có 6 câu: chênh 1 câu tương đương 17 điểm phần trăm, nên mọi khác biệt test chỉ mang tính minh họa. Dev cũng chỉ 22 câu.
  - Hit tự động đòi hỏi **trọn** evidence, nên nghiêm ngặt: ví dụ t05 B có cú pháp `|` (đúng một nửa yêu cầu) nhưng vẫn tính là miss.
  - Benchmark do chính tôi viết sau khi đọc corpus, nên có thể thiên về các câu mà từ khóa dễ khớp.
  - Coherence và grounding do một người chấm, không mù chiến lược; C được gán nhãn giống B vì là cùng chunk.
  - Thời gian ingest đo trên CPU laptop, chỉ một lần chạy, chưa tách thời gian tải model.
  - Tìm kiếm HNSW là xấp xỉ, nhưng ở quy mô 364–606 vector thì kết quả ổn định giữa hai lần chạy.
  - Heuristic phát hiện evidence bị tách qua nhiều chunk ghi nhận 0 trường hợp. Các miss của A chủ yếu do chunk chứa evidence không lọt top-3, không phải do bị tách.
- **Nếu làm lại hoặc mở rộng:**
  - Gộp các mục quá ngắn (dưới khoảng 200 ký tự) với mục kế bên.
  - Thêm metadata `section_kind` (spec / rationale / rejected / tutorial) để lọc hoặc hạ hạng các mục "Rejected ideas".
  - Thử hybrid BM25 + dense (giữ nguyên chunk và filter), vì các câu như d06 và t03 có từ khóa đặc trưng ("lambda", "run time").
  - Viết thêm một bộ test mới và lớn hơn mà tôi chưa xem kết quả.
  - Nhờ người thứ hai chấm mù để đo độ đồng thuận.

**Sử dụng AI:** Code pipeline, bộ câu hỏi và bản nháp nhãn thủ công được viết với sự hỗ trợ của một trợ lý AI lập trình. Cách kiểm tra:
- Mọi evidence được kiểm tra tự động trên text nguồn (28/28).
- Mọi số liệu trong báo cáo lấy trực tiếp từ file trong `results/` do pipeline sinh ra.
- Nhãn coherence và grounding được gán bằng cách đọc từng chunk hoặc từng top-3 (lý do ghi trong CSV), sau đó tôi rà soát lại.
