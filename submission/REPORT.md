# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`:
- Tổng số traces:
- Số PII leak còn lại:
- Link/đường dẫn dashboard:

## 3. Logging và tracing

- Evidence correlation ID:
- Evidence PII redaction:
- Evidence trace waterfall:
- Giải thích một span đáng chú ý:

## 4. Prompt versioning

- Prompt name:
- Version/label baseline:
- Version/label candidate:
- Trace ID của mỗi version:
- Bằng chứng đổi label hoặc rollback:

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`:
- Evidence dashboard:
- SLO đã chọn và lý do:
- Alert rules và runbook:

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

| Thành viên      | Phần việc                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Commit/PR                                                                                                          | Điều đã học                                                                                                                                                                                                                                                                                 |
| -----------------| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| --------------------------------------------------------------------------------------------------------------------| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Nguyễn Việt Hải | **CP1 — Logging & PII:** Triển khai middleware Correlation ID (`CorrelationIdMiddleware`) tự động sinh/truyền `x-request-id` và `x-response-time-ms`; thực hiện Log Context Enrichment (`bind_contextvars`) bổ sung đầy đủ metadata (`user_id_hash`, `session_id`, `feature`, `model`, `env`) vào log API; phát triển processor `scrub_event` đệ quy trong structlog pipeline khử sạch PII (Email, SĐT Việt Nam, CCCD, Thẻ tín dụng, Hộ chiếu); đạt điểm kiểm tra **100/100** từ `scripts/validate_logs.py`.<br>**CP2 — Tracing & Skill Integration:** Cài đặt Langfuse AI Skill từ `github.com/langfuse/skills` vào workspace (`.agents/skills/langfuse`); chuẩn hóa Tracing ứng dụng theo best practices (gắn retriever span `rag-retrieval`, trace `chat-response`, generation `llm-generate`, capture input/output an toàn và ghi nhận `quality_score` lên trace). | Branch [`NguyenVietHai`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/tree/NguyenVietHai) · Commit [`3e05aab`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/commit/3e05aab31b83355b5397c3175df3977d6554e1b) / [`6590cad`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/commit/6590cad) | Hiểu rõ cơ chế xây dựng JSON Logging có cấu trúc, kỹ thuật truyền vết Correlation ID xuyên suốt qua HTTP Middleware trong FastAPI, cách thiết kế pipeline lọc khử PII đệ quy an toàn bằng Regex, và quy trình cài đặt/áp dụng Agent Skill để tích hợp Langfuse Tracing đúng chuẩn kỹ thuật. |

