# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL: https://github.com/ThaiTu2602/Day13-K4-2A202601504
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`:
  - **Baseline CP0 (2026-08-11): 30/100** — 42 log record, 40 record thiếu required field, 40 record thiếu enrichment, 0 unique correlation ID, 0 PII leak theo detector của script. Bằng chứng: [`submission/evidence/cp0-baseline-validate_logs.txt`](evidence/cp0-baseline-validate_logs.txt).
  - Chi tiết trừ điểm baseline: −30 required fields (`correlation_id` = `MISSING` trên log `service=api`), −20 correlation ID propagation (0 ID duy nhất), −20 enrichment (thiếu `user_id_hash`, `session_id`, `feature`, `model`). Chỉ mục PII qua vì `summarize_text()` đã che sơ bộ trong `message_preview`; chưa có PII processor toàn diện nên vẫn phải làm ở CP1.
  - **Sau CP1: 100/100** — 73 log record, 0 record thiếu required field, 0 record thiếu enrichment, 34 unique correlation ID, 0 PII leak. Bằng chứng: [`submission/evidence/cp1-validate_logs.txt`](evidence/cp1-validate_logs.txt).
- Tổng số traces: **136 traces** trên Langfuse Cloud, project dùng chung `day13` (`GET /api/public/traces` → `totalItems=136`), vượt xa mức tối thiểu 10. Danh sách trích xuất: [`cp2-traces.json`](evidence/cp2-traces.json); ảnh danh sách: [`Trace 1.png`](evidence/Trace%201.png), [`Trace 2.png`](evidence/Trace%202.png). Từ CP2, trace ghi `prompt_source=langfuse` (không còn `local-fallback`) vì prompt `day13-chat` đã được tạo.
- Số PII leak còn lại: 0 theo `validate_logs.py`; đã kiểm tra tay `data/logs.jsonl` không chứa email/số điện thoại VN/CCCD/số thẻ test kể cả khi gửi request cố tình nhồi PII.
- Link/đường dẫn dashboard: [`submission/evidence/dashboard.html`](evidence/dashboard.html), dựng bằng `python scripts/render_dashboard.py` từ `data/logs.jsonl`. `validate_dashboard.py` → `HỢP LỆ: 6/6 panel`.

## 3. Logging và tracing

- Evidence correlation ID: mọi log `service=api` đều mang `correlation_id` dạng `req-<8 hex>` do [`app/middleware.py`](../app/middleware.py) sinh (hoặc lấy lại từ header `x-request-id` nếu client đã gửi). Response trả về cùng ID ở header `x-request-id` và kèm `x-response-time-ms`. Xem [`cp1-validate_logs.txt`](evidence/cp1-validate_logs.txt) (34 unique correlation ID trên 73 record) và [`cp2-traces.json`](evidence/cp2-traces.json).
- Evidence PII redaction: processor `scrub_event` trong [`app/logging_config.py`](../app/logging_config.py) chạy trước khi ghi file. Request thử `Contact me at test@example.com or 0987654321, card 4111 1111 1111 1111, CCCD 012345678901` cho ra log `"message_preview": "Contact me at [REDACTED_EMAIL] or [REDACTED_PHONE_VN], card [REDACTED_CREDIT_CAR..."`, và `grep` các chuỗi PII gốc trong `data/logs.jsonl` không ra kết quả nào.
- Evidence trace waterfall: ảnh [`Trace Waterfall.png`](evidence/Trace%20Waterfall.png) — trace `fb3e2e439547ccbca78d9538fa0e6e1d`, waterfall thấy `run` (1.19s) lồng `retrieve` và `generate` (0.15s), kèm Session `s10`, User ID `49ef5a469240`, tags `lab`/`qa`/`claude-sonnet-4-5` và cost $0.001854. Bản trích xuất JSON đối chiếu: [`cp2-trace-waterfall.json`](evidence/cp2-trace-waterfall.json) — 3 span `run` (GENERATION, ~155ms) chứa `generate` (SPAN, ~152ms) và `retrieve` (SPAN, ~0ms). Đã gắn `@observe(as_type="span")` cho `mock_rag.retrieve` và `FakeLLM.generate` theo phần mở rộng của lab, nếu không waterfall chỉ có một span `run` duy nhất.
- Giải thích một span đáng chú ý: span `generate` chiếm ~152/155ms, tức **gần như toàn bộ latency nằm ở LLM**, còn `retrieve` gần 0ms vì corpus là dict in-memory. Đây chính là giá trị của việc tách sub-span: khi panel latency báo BREACH ở CP3, waterfall trả lời ngay "chậm ở LLM hay ở RAG" mà không phải đoán. Ở trạng thái bình thường, tỷ lệ này là `generate` áp đảo; nếu `retrieve` bỗng vọt lên vài giây thì đó là dấu hiệu của kịch bản `rag_slow`.
- Liên kết hai chiều Logs ↔ Traces: [`app/agent.py`](../app/agent.py) bind `trace_id` vào structlog contextvars (log `response_sent` mang `trace_id`) và ghi `correlation_id` vào metadata của generation. Từ một log line mở được đúng trace, và từ một trace `grep` ra đúng log line.

## 4. Prompt versioning

- Prompt name: `day13-chat` (text prompt trên Langfuse Cloud), giữ đủ ba biến `{{feature}}`, `{{docs}}`, `{{message}}`.
- Version/label baseline: **v1** — labels `baseline`, `production`. Template gốc `Feature/Docs/Question`.
- Version/label candidate: **v2** — label `candidate`. Thêm ràng buộc `Answer in at most 3 sentences. Cite the retrieved docs when relevant.`
- Version thứ ba: **v3** — label `latest`, do thành viên khác tạo qua giao diện Langfuse (prompt tiếng Việt, vẫn giữ đủ 3 biến).
- Ảnh ba version và label hiện tại: [`Prompts.png`](evidence/Prompts.png) — v1 `production`+`baseline`, v2 `candidate`, v3 `latest`.
- Trace ID của mỗi version (cùng một input `How should alerts be designed?`):
  - v1 / `production`: `141483ab1bc3963b8ab2aa09a0b60ca5` (correlation `req-9869c14f`)
  - v2 / `candidate`: `e965c7e0e25dc7399bffafc8656fb779` (correlation `req-3ce4c854`)
- Bằng chứng đổi label hoặc rollback: [`cp2-prompt-label-rollback.md`](evidence/cp2-prompt-label-rollback.md), gồm **hai vòng**, mỗi bước đều xác nhận bằng một request thật rồi đọc `prompt_version` từ metadata của trace:
  - Vòng 1: promote `production` sang v2 (trace `885a68edca070b10c5b6140bdc7041b9` → `prompt_version=2`), rollback về v1 (trace `085785e427dd7f723bd6c65634359b07` → `prompt_version=1`).
  - Vòng 2: sau khi team tạo v3 và v3 nhận toàn bộ label, nhóm rollback `production` khỏi v3 về v1 — trace `a2ebfc73dd6317a8d3cdf6b2c144328f` đọc ra `prompt_version=3` trước rollback, trace `fb3e2e439547ccbca78d9538fa0e6e1d` đọc ra `prompt_version=1` sau rollback. Nội dung v3 không bị xoá, chỉ còn giữ label `latest`.
  - `.env` giữ nguyên `LANGFUSE_PROMPT_LABEL=production` ở mọi bước — chỉ version mà label trỏ tới là thay đổi, nên rollback không cần sửa code hay deploy lại, chỉ tốn một lần restart để hết cache 60 giây.

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel có trong dashboard contract.` — lưu tại [`cp2-validate_dashboard.txt`](evidence/cp2-validate_dashboard.txt) (kèm output của `render_dashboard.py` và `pytest`).
- Evidence dashboard: ảnh [`Dashboard 1.png`](evidence/Dashboard%201.png) (6 panel) và [`Dashboard 2.png`](evidence/Dashboard%202.png) (phần dưới + bảng SLO). File gốc: [`dashboard.html`](evidence/dashboard.html), dựng bằng [`scripts/render_dashboard.py`](../scripts/render_dashboard.py) đọc thẳng `data/logs.jsonl` — đúng nguồn chuẩn mà contract quy định. Threshold, đơn vị, time range (60 phút) và refresh (30s) đều lấy từ `config/dashboard.yaml`, không hard-code, nên ảnh dashboard không thể lệch khỏi contract. Mỗi panel tự gắn nhãn OK/BREACH. Đặc tả chi tiết 6 panel ở [`docs/dashboard-spec.md`](../docs/dashboard-spec.md).
  - Số liệu trên ảnh đã nộp: latency P50 157ms / P95 1354ms / P99 1409ms · 34 request (~5.67 req/phút) · error 0% · cost 0.0696 USD (0.002047 USD/request) · 1150 tokens in + 4409 tokens out · quality 0.8794 trên 34 mẫu — cả 6 panel đều OK.
- SLO đã chọn và lý do ([`config/slo.yaml`](../config/slo.yaml)): giữ 4 SLI mặc định nhưng ghi rõ căn cứ từ số đo thật — `latency_p95_ms` 3000ms (baseline ~160ms nên còn nhiều headroom cho cold start), `error_rate_pct` 2% (dành cho lỗi phụ thuộc ngoài vì FakeLLM gần như không lỗi), `daily_cost_usd` 2.5 (≈1250 request/ngày với chi phí ~0.002 USD/request, đủ bắt sự cố `cost_spike`), `quality_score_avg` 0.75 (baseline 0.88, bắt được khi RAG trả rỗng vì mất 0.2 điểm docs).
- Alert rules và runbook: 3 alert symptom-based trong [`config/alert_rules.yaml`](../config/alert_rules.yaml) — `chat_slow_for_users` (warning, P95 > 3000ms trong 5 phút), `chat_requests_failing` (critical, error rate > 5% trong 3 phút), `daily_cost_budget_exceeded` (warning, > 2.5 USD/24h). Runbook đầy đủ với ba bước kiểm tra đầu tiên theo luồng Metrics → Traces → Logs ở [`docs/alerts.md`](../docs/alerts.md).
  - Vì sao symptom-based: số cách hỏng là vô hạn còn số triệu chứng thì hữu hạn — một alert trên `latency_p95` bắt được cả RAG chậm, LLM chậm lẫn nguyên nhân chưa ai nghĩ tới, trong khi alert đặt theo tên hàm (`retrieve_timeout_count`) sẽ im lặng ngay sau lần refactor đầu tiên và vẫn bỏ sót trường hợp mọi thành phần đều "khỏe" nhưng tổng thời gian vẫn vượt 3 giây. Nguyên nhân không biến mất khỏi quy trình, nó chuyển từ *điều kiện kích hoạt* sang *bước điều tra* trong runbook. Lập luận đầy đủ ở cuối [`docs/alerts.md`](../docs/alerts.md).

## 6. Điều tra challenge

- Challenge ID:
- Triệu chứng từ metrics:
- Trace ID liên quan:
- Log line/correlation ID liên quan:
- Root cause:
- Fix action:
- Preventive measure:

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| *(leader — tự điền)* | | | |
| Nguyễn Hoàng Minh | **CP0 — Setup & baseline:** dựng `.venv`, cấu hình `.env` và Langfuse Cloud (`tracing_enabled=true`, `auth_check=True`), chạy load test, ghi baseline `validate_logs.py` = 30/100 → `submission/evidence/cp0-baseline-validate_logs.txt`.<br>**CP2 — Traces:** gắn `@observe(as_type="span")` cho `mock_rag.retrieve` và `FakeLLM.generate` (`app/mock_rag.py`, `app/mock_llm.py`) để waterfall tách được RAG khỏi LLM; thêm liên kết hai chiều Logs ↔ Traces trong `app/agent.py` (bind `trace_id` vào log, ghi `correlation_id` vào generation metadata) và sửa lỗi làm vỡ public test `test_agent_prompt_trace.py`.<br>**CP2 — Prompt versioning:** tạo `day13-chat` v1/v2, chạy cùng input với hai label, thực hiện promote + rollback `production` hai vòng, mỗi bước xác nhận bằng trace thật → `evidence/cp2-prompt-label-rollback.md`.<br>**CP2 — Dashboard/SLO/Alert:** viết `scripts/render_dashboard.py` dựng 6 panel từ `data/logs.jsonl` theo đúng contract; điền `docs/dashboard-spec.md`, `config/slo.yaml`, `config/alert_rules.yaml` (3 alert symptom-based) và runbook `docs/alerts.md`.<br>**Báo cáo:** mục 2–5 của `submission/REPORT.md` và toàn bộ evidence CP0/CP2. | *(điền sau khi commit)* | Alert phải đặt theo **triệu chứng người dùng**, không theo tên hàm: số cách hỏng là vô hạn còn số triệu chứng thì hữu hạn, nên một alert trên `latency_p95` bắt được cả RAG chậm lẫn LLM chậm, trong khi `retrieve_timeout_count` sẽ im lặng ngay sau lần refactor đầu tiên. Nguyên nhân không biến mất — nó chuyển từ *điều kiện kích hoạt* sang *bước điều tra* trong runbook.<br>Một bài học nữa từ thực tế chạy bài: `validate_logs.py` đạt 100/100 **không** có nghĩa log đã sạch. Script chỉ kiểm tra chiều "còn sót PII", không kiểm tra chiều "redact quá tay" — pattern `address_vn` xoá sạch cả câu hỏi hợp lệ chứa chữ "số", làm log mất khả năng debug mà điểm vẫn tuyệt đối. |
| Nguyễn Việt Hải | Implement Correlation ID middleware, Log Context Enrichment (`bind_contextvars`), PII Redaction Processor đệ quy (`scrub_event`), cài đặt Langfuse AI skill và tích hợp Tracing. | Branch [`NguyenVietHai`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/tree/NguyenVietHai) (Commit `3e05aab`) | Cấu trúc JSON logging với Correlation ID xuyên suốt request, kỹ thuật khử PII tự động đệ quy bằng Regex, và quy chuẩn tích hợp Tracing & Span hierarchy với Langfuse SDK. |
