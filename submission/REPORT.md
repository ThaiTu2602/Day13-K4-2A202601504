# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: LowTech Nhất
- Repository URL: https://github.com/ThaiTu2602/Day13-K4-2A202601504
- Commit SHA cuối: `44625e5` (tính tới thời điểm viết báo cáo này; cập nhật lại sau lần commit cuối cùng trước khi nộp)
- Thành viên và vai trò:
  - **Thành viên A — Đoàn Văn Tuyền (2A202601374)** — Logging & Middleware: phụ trách CP1 (Middleware, Correlation ID, gán log metadata).
  - **Thành viên B — Nguyễn Việt Hải (2A202601656)** — Security & Compliance: phụ trách CP1 (bật processor PII, cấu hình regex patterns che PII và nâng cấp che PII toàn cục).
  - **Thành viên C — Nguyễn Hoàng Minh (2A202601764)** — Metrics & Alerting: phụ trách CP2 (tích hợp Langfuse, đo đếm `error_rate_pct`, viết SLO, Alert rules và Runbook).
  - **Thành viên D — Nguyễn Thái Tú (2A202601504)** — QA & Incident Analyst: chạy load test sinh dữ liệu, thiết kế Dashboard Spec, chủ trì điều tra Challenge (CP3) và viết báo cáo `REPORT.md`.

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

- Challenge ID: `day13-k4-observability-v1` (cohort K4, seed 1304, incident chính thức `rag_slow`, `affected_feature=monitoring`, `latency_threshold_ms=2000` theo [`config/challenge.json`](../config/challenge.json)). Kích hoạt bằng `python scripts/inject_incident.py` (đọc thẳng challenge.json, không dùng `--scenario`), chạy input chính thức bằng `python scripts/load_test.py --challenge`.
- Triệu chứng từ metrics: `GET /metrics` ngay sau khi chạy 5 query challenge trả về `traffic=5`, `latency_p50=2653ms`, `latency_p95=3563ms`, `latency_p99=3563ms` — vượt xa ngưỡng 2000ms — trong khi `error_rate_pct=0` và `quality_avg=0.84`. Kết luận: đây là **suy giảm latency thuần túy**, không phải lỗi logic hay chất lượng câu trả lời (loại trừ ngay giả thuyết lỗi ở tầng LLM/answer). Ảnh: `submission/evidence/cp3-metrics.png`.
- Trace ID liên quan (5/5 request của challenge, tất cả đều feature=`monitoring`):
  - `k4-challenge-s01` — correlation `req-e0cf1951` — trace `7210b906f8fb002293d9e279c63a0e87` — latency 2653ms
  - `k4-challenge-s02` — correlation `req-b1d80b5e` — trace `d75e0b07fe1a5510e2fdb70f670f2efc` — latency **3563ms** (khớp đúng `p95`/`p99`, dùng làm trace đại diện để soi waterfall)
  - `k4-challenge-s03` — correlation `req-05f8041e` — trace `2ffd8a3c114231750c719ee20d16298d` — latency 2652ms
  - `k4-challenge-s04` — correlation `req-a2e2dea2` — trace `b398c7c0bd9ba433e37bb409a4c8905b` — latency 2653ms
  - `k4-challenge-s05` — correlation `req-7592ea2f` — trace `0e7008e21fa784de005ccc2347f96586` — latency 2653ms
  - Waterfall của trace `d75e0b07fe1a5510e2fdb70f670f2efc`: [`submission/evidence/waterfallcp3.png`](evidence/waterfallcp3.png) — tổng `run` 3.58s, span `retrieve` **2.51s**, span `generate` 0.15s. Span `retrieve` chiếm 70% tổng latency và một mình nó đã vượt ngưỡng 2000ms.
- Log line/correlation ID liên quan: toàn bộ 10 dòng (5 `request_received` + 5 `response_sent`, đều mang `correlation_id` và `trace_id`) lưu tại [`submission/evidence/cp3-challenge-logs.txt`](evidence/cp3-challenge-logs.txt). Ví dụ dòng nặng nhất:
  `{"service": "api", "latency_ms": 3563, ..., "event": "response_sent", "correlation_id": "req-b1d80b5e", "trace_id": "d75e0b07fe1a5510e2fdb70f670f2efc", "feature": "monitoring", "session_id": "k4-challenge-s02", ...}`
- Root cause: incident `rag_slow` chèn `time.sleep(2.5)` trực tiếp trong bước truy hồi tài liệu — [`app/mock_rag.py:19-20`](../app/mock_rag.py#L19-L20):
  ```python
  if STATE["rag_slow"]:
      time.sleep(2.5)
  ```
  Baseline đo được ở CP2 (mục 3, span `generate` ~152ms, span `retrieve` ~0ms khi không có incident — xem `cp2-trace-waterfall.json`) cộng thêm đúng ~2500ms khớp khít với độ trễ tăng thêm quan sát được (`2653 − 152 ≈ 2500ms`, `3563 − 152 ≈ 3400ms` do overhead mạng/queue ở lần request đầu). Việc `error_rate_pct=0` và `quality_avg` không đổi loại trừ khả năng lỗi ở LLM hay logic sinh câu trả lời — độ trễ đến từ đúng một dependency: bước RAG retrieval, không phải từ model hay downstream.
  **Xác nhận trực quan trên trace waterfall** ([`waterfallcp3.png`](evidence/waterfallcp3.png), trace `d75e0b07fe1a5510e2fdb70f670f2efc`, session `k4-challenge-s02`): tổng `run` = 3.58s, span `retrieve` = **2.51s**, span `generate` = 0.15s — khớp gần như tuyệt đối với `time.sleep(2.5)` bị chèn trong code. Span `retrieve` một mình đã chiếm 70% tổng latency và đủ để vượt ngưỡng 2000ms dù `generate` (LLM) vẫn nhanh bình thường — bằng chứng dứt khoát cho thấy nút nghẽn nằm ở bước RAG retrieval, không phải LLM.
- Fix action:
  1. Thêm timeout tường minh cho lệnh gọi `retrieve()` (ví dụ 800ms–1s) kèm fallback trả lời "không tìm thấy tài liệu, dùng câu trả lời chung" thay vì để request treo tới khi vector store phản hồi.
  2. Tách `retrieve` chạy bất đồng bộ/song song với các bước chuẩn bị khác nếu pipeline cho phép, để độ trễ của RAG không cộng dồn tuyến tính vào tổng latency.
  3. Trong ngữ cảnh bài lab: `python scripts/inject_incident.py --disable` để tắt incident, xác nhận `/metrics` trở lại baseline (`latency_p50` ~150-160ms như log trước CP3).
- Preventive measure:
  1. Thêm SLI/alert riêng cho latency của bước retrieval (không chỉ alert tổng `latency_p95` như hiện có trong `config/alert_rules.yaml`), để phát hiện sớm khi riêng dependency RAG chậm đi trước khi nó kéo tổng latency vượt SLO.
  2. Circuit breaker cho vector store: nếu retrieval liên tục chậm/timeout, tự động chuyển sang chế độ fallback (không dùng context) thay vì để mọi request đều trả giá bằng latency.
  3. Đưa kịch bản "dependency chậm" (như `rag_slow`) vào bộ load test định kỳ trước khi release, không chỉ chạy khi có incident thật — giúp đội phát hiện điểm nghẽn đơn lẻ (single point of latency) trước khi người dùng gặp phải.

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên (MSSV) | Vai trò | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|---|
| **A — Đoàn Văn Tuyền** (2A202601374) | Logging & Middleware | CP1: Triển khai `CorrelationIdMiddleware` ([`app/middleware.py`](../app/middleware.py)) — sinh `correlation_id` từ header `x-request-id` hoặc tạo mới (`req-<8hex>`), bind vào structlog contextvars, `clear_contextvars()` chống rò rỉ giữa các request, trả `x-request-id`/`x-response-time-ms` ở response header; gán log metadata (`bind_contextvars(user_id_hash, session_id, feature, model, env)`) trong [`app/main.py`](../app/main.py). | Commit [`3e05aab`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/commit/3e05aab31b83355b5397c3175df3977d6554e1b) · [`2c96d39`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/commit/2c96d39) (fix: move correlation_id from metadata to tags to pass tests) | Cách truyền `correlation_id` xuyên suốt một request qua ASGI middleware + contextvars, và vì sao phải `clear_contextvars()` đầu mỗi request để tránh rò rỉ dữ liệu của request trước sang request sau khi server dùng chung thread/task. |
| **B — Nguyễn Việt Hải** (2A202601656) | Security & Compliance | CP1: Bật processor `scrub_event` trong pipeline structlog ([`app/logging_config.py`](../app/logging_config.py), trước đó bị comment); mở rộng bộ regex PII trong [`app/pii.py`](../app/pii.py) (thêm pattern `passport`, `address_vn`); nâng cấp che PII từ chỗ chỉ che sơ bộ `message_preview` (qua `summarize_text`) sang che toàn cục ở mọi trường log — kết quả `scripts/validate_logs.py` đạt **100/100**, 0 PII leak trên 73 record. | Commit [`3e05aab`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/commit/3e05aab31b83355b5397c3175df3977d6554e1b) | Kỹ thuật khử PII đệ quy bằng regex trong logging pipeline, và rủi ro "redact quá tay" (over-redaction): `validate_logs.py` đạt 100/100 chỉ chứng minh không còn sót PII, không chứng minh log chưa bị xoá nhầm dữ liệu hợp lệ. |
| **C — Nguyễn Hoàng Minh** (2A202601764) | Metrics & Alerting | CP2: Tích hợp Langfuse (`@observe(as_type="span")` cho `mock_rag.retrieve`/`FakeLLM.generate`, liên kết hai chiều Logs↔Traces trong `app/agent.py`); thêm `error_rate_pct` vào `app/metrics.py`; viết `config/slo.yaml` (4 SLI có căn cứ số đo thật) và `config/alert_rules.yaml` (3 alert symptom-based) kèm runbook `docs/alerts.md`; dựng dashboard 6 panel (`scripts/render_dashboard.py`, `docs/dashboard-spec.md`); prompt versioning v1/v2 + rollback hai vòng (`evidence/cp2-prompt-label-rollback.md`). | Branch [`NguyenHoangMinh`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/tree/NguyenHoangMinh) · Commit `d355ae6`, `b87624f` · PR [#1](https://github.com/ThaiTu2602/Day13-K4-2A202601504/pull/1) | Alert phải đặt theo **triệu chứng người dùng**, không theo tên hàm: số cách hỏng là vô hạn còn số triệu chứng thì hữu hạn, nên một alert trên `latency_p95` bắt được cả RAG chậm lẫn LLM chậm, trong khi `retrieve_timeout_count` sẽ im lặng ngay sau lần refactor đầu tiên. Nguyên nhân không biến mất — nó chuyển từ *điều kiện kích hoạt* sang *bước điều tra* trong runbook. |
| **D — Nguyễn Thái Tú** (2A202601504) | QA & Incident Analyst | CP0: dựng `.venv`, cấu hình `.env`/Langfuse Cloud, chạy `load_test.py` sinh dữ liệu, ghi baseline `validate_logs.py` = 30/100 → `evidence/cp0-baseline-validate_logs.txt`.<br>CP3: chủ trì điều tra challenge chính thức `day13-k4-observability-v1` (incident `rag_slow`) — bật incident (`inject_incident.py`), chạy 5 query chính thức (`load_test.py --challenge`), đối chiếu `metrics` (P50 2653ms/P95 3563ms, vượt ngưỡng 2000ms) với trace waterfall thật (`d75e0b07fe1a5510e2fdb70f670f2efc`, span `retrieve` 2.51s) và log thô (`evidence/cp3-challenge-logs.txt`) để xác định root cause; viết mục 6 và tổng hợp toàn bộ `submission/REPORT.md`. | Branch `main`/`dev`, merge PR [#1](https://github.com/ThaiTu2602/Day13-K4-2A202601504/pull/1) | Cách chứng minh root cause bằng bộ ba **metric → trace → log** thay vì suy đoán: metric cho biết *có vấn đề gì*, trace khoanh vùng *span nào*, log xác nhận *đúng request nào* — thiếu một trong ba thì kết luận root cause không đủ evidence theo RULES.md. |
