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

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Nguyễn Việt Hải | Implement Correlation ID middleware, Log Context Enrichment (`bind_contextvars`), PII Redaction Processor đệ quy (`scrub_event`), cài đặt Langfuse AI skill và tích hợp Tracing. | Branch [`NguyenVietHai`](https://github.com/ThaiTu2602/Day13-K4-2A202601504/tree/NguyenVietHai) (Commit `3e05aab`) | Cấu trúc JSON logging với Correlation ID xuyên suốt request, kỹ thuật khử PII tự động đệ quy bằng Regex, và quy chuẩn tích hợp Tracing & Span hierarchy với Langfuse SDK. |

