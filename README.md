# Day 06 - Data Ingestion: Python PEP knowledge base

Bài lab cá nhân của **Trần Tùng Lâm (2A202603893, L3B)**. Đề bài gốc: [ASSIGNMENT.md](ASSIGNMENT.md).
Báo cáo: [report/individual/2A202603893_TranTungLam.md](report/individual/2A202603893_TranTungLam.md).

Pipeline đọc 8 PEP (định dạng reStructuredText), chuẩn hóa văn bản và chia thành 115 đơn vị nội dung có thể truy vết. Sau đó pipeline chia chunk theo 2 cách, tạo embedding bằng model thật, lưu vào **Chroma** (lưu bền vững trên đĩa, metric cosine, có metadata filter), rồi đánh giá 3 chiến lược A/B/C trên 28 câu hỏi (22 dev / 6 test).

| | |
|---|---|
| Corpus | 8 PEP, public domain / CC0, `python/peps@2ace2311`, 115 đơn vị ≥1.500 ký tự ([data/manifest.json](data/manifest.json)) |
| Embedding (kết quả chính) | `BAAI/bge-small-en-v1.5`, chạy local bằng sentence-transformers 6.3.0, 384 chiều, CPU, chi phí 0 |
| Embedding (thí nghiệm thêm) | OpenAI `text-embedding-3-small`, 1536 chiều, khoảng $0.003 → [results_openai/](results_openai/) |
| Vector store | ChromaDB 1.5.9 `PersistentClient` (`chroma_db/`), HNSW cosine (tìm kiếm xấp xỉ), lọc bằng `where` |
| Chiến lược | A: cửa sổ cố định 500/50; B: theo heading/đoạn, tối đa 1200; C: B + filter metadata (`pep_type`/`python_version`) |

## Cấu trúc

```text
src/                 code pipeline (ingestion, chunking, embeddings, store, evaluation, run)
scripts/             check_reingest_change.py (kiểm tra nạp lại tài liệu đã đổi), write_manual_labels.py
data/raw/            8 file .rst gốc (public domain/CC0)   data/manifest.json   data/pages.jsonl
benchmark/           questions.jsonl (gold + evidence + filter), README.md (split, tiêu chí chọn)
artifacts/           experiment_log.csv
results/             stats ingest/reingest, traces top-3, metrics dev/test, selection, manual/ (nhãn thủ công),
                     run.log (START/END từng lần chạy), errors.log (rỗng = không có lỗi)
results_openai/      cùng pipeline với embedding OpenAI (thí nghiệm bổ sung, không có nhãn thủ công)
starter/             starter pgvector của đề (không dùng: máy không có Docker; đề cho phép Chroma)
```

## Setup và chạy (Windows PowerShell; macOS/Linux tương tự)

Cần Python 3.10+ và mạng cho lần tải model đầu tiên (khoảng 130 MB). Không cần Docker.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env        # mặc định EMBED_PROVIDER=local, không cần key

python -m src.run all              # prepare -> ingest (rebuild) -> reingest -> dev -> select -> test -> audit
python scripts/check_reingest_change.py
python scripts/write_manual_labels.py
```

Có thể chạy từng bước:

```powershell
python -m src.run prepare          # đọc + chuẩn hóa, ghi manifest/pages, kiểm chứng 28 evidence
python -m src.run ingest --rebuild # chunk + embed + lưu A và B (C dùng lại index của B)
python -m src.run ingest --tag reingest   # nạp lại: phải "skipped" toàn bộ, số chunk không đổi
python -m src.run evaluate --split dev
python -m src.run select           # chọn chiến lược chỉ dựa trên dev (quy tắc chốt trước)
python -m src.run evaluate --split test
python -m src.run audit            # xuất mẫu coherence + kiểm tra metadata của top-3 test
```

Chạy bằng OpenAI: điền `OPENAI_API_KEY` trong `.env`, rồi đặt `EMBED_PROVIDER=openai` (trong `.env` hoặc biến môi trường) và chạy `python -m src.run all`. Chế độ này dùng collection `*_openai` và thư mục kết quả `results_openai/`. Nếu API lỗi, chương trình dừng hẳn, không chuyển sang vector giả.

`data/raw/` có thể tải lại từ `https://raw.githubusercontent.com/python/peps/2ace2311c6a460c71c92dc64046c6f299de2a3a7/peps/pep-NNNN.rst`; so khớp bằng `sha256` trong manifest.

## Kết quả chính (embedding local, xem báo cáo để phân tích)

| Strategy | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 | Chunks | Ingest |
|---|---|---|---|---|---|---|
| A fixed 500/50 | 9/22 | 16/22 | 2/6 | 2/6 | 606 | 33.0 s |
| B structure ≤1200 | 14/22 | 19/22 | 3/6 | 3/6 | 364 | 37.3 s |
| C = B + filter | 14/22 | 19/22 | 3/6 | 3/6 | 364 (chung index B) | — |

Không đưa lên repo: `.env` (key), `.venv/`, `chroma_db/` (tạo lại bằng `python -m src.run all`).
