# Yêu cầu dashboard

Contract có thể kiểm tra bằng máy nằm tại `config/dashboard.yaml`. Hướng dẫn dựng và kiểm tra runtime nằm tại [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md).

Dashboard chính cần đủ 6 nhóm thông tin:

1. Latency P50/P95/P99.
2. Traffic: request count hoặc QPS.
3. Error rate và breakdown theo loại lỗi.
4. Cost theo thời gian.
5. Tổng token input/output.
6. Quality proxy.

Tiêu chuẩn trình bày:

- Khoảng thời gian mặc định: 1 giờ.
- Tự refresh mỗi 15–30 giây nếu công cụ hỗ trợ.
- Có threshold hoặc SLO line.
- Ghi rõ đơn vị.
- Chỉ giữ 6–8 panel quan trọng ở lớp chính.
- Screenshot phải nhìn được tên panel và khoảng thời gian.

Kiểm tra contract trước khi chụp evidence:

```bash
python scripts/validate_dashboard.py
```

## Công cụ nhóm sử dụng

Nhóm dựng dashboard bằng **script tự viết `scripts/render_dashboard.py`**, không dùng Grafana.
Lý do: nguồn chuẩn của contract là `data/logs.jsonl` (không phải Langfuse), nên một renderer đọc thẳng
file JSONL cho ra đúng con số mà `config/dashboard.yaml` mô tả, không cần dựng thêm hạ tầng và
không có nguy cơ ảnh dashboard lệch khỏi contract.

```bash
python scripts/render_dashboard.py          # sinh submission/evidence/dashboard.html
python scripts/render_dashboard.py --open   # sinh xong mở luôn trình duyệt để chụp ảnh
```

Script đọc threshold, đơn vị, time range và refresh trực tiếp từ `config/dashboard.yaml` và
`config/slo.yaml` — không hard-code trong template — nên contract đổi thì dashboard đổi theo.
Mỗi panel tự gắn nhãn `OK` hoặc `BREACH` bằng cách so giá trị đo được với threshold trong contract.
Langfuse vẫn là nơi mở trace/prompt version để điều tra sâu khi một panel chuyển sang `BREACH`.

## Đặc tả 6 panel

| # | Panel (`id`) | Tên hiển thị | Nguồn dữ liệu | Phép tổng hợp | Đơn vị | Threshold / SLO line |
|---|---|---|---|---|---|---|
| 1 | `latency` | Latency percentiles | `data/logs.jsonl` · `response_sent.latency_ms` | p50, p95, p99 | `ms` | p95 ≤ 3000 |
| 2 | `traffic` | Request traffic | `data/logs.jsonl` · `request_received` | count, rate_per_minute | `requests_per_minute` | rate ≥ 1 |
| 3 | `errors` | Error rate and breakdown | `data/logs.jsonl` · `request_received`, `request_failed`, `error_type` | error_rate_pct, count_by_value | `percent` | error_rate ≤ 2 |
| 4 | `cost` | Cost over time | `data/logs.jsonl` · `response_sent.cost_usd` | sum_by_minute, total | `usd` | total ≤ 2.5 |
| 5 | `tokens` | Input and output tokens | `data/logs.jsonl` · `response_sent.tokens_in`, `tokens_out` | sum_by_field | `tokens` | sum ≤ 50000 |
| 6 | `quality` | Quality proxy | `data/logs.jsonl` · `response_sent.quality_score` | mean | `score_0_to_1` | mean ≥ 0.75 |

Thiết lập chung: **time range mặc định 60 phút**, **refresh 30 giây**, SLO line vẽ đứt nét màu cam trên
mỗi biểu đồ. Ba panel đầu trả lời "người dùng có đang khổ không" (latency, traffic, error), ba panel sau
trả lời "hệ thống có đang đốt tiền hoặc trả lời kém không" (cost, tokens, quality).

## Giá trị baseline đã đo

Đo sau `python scripts/load_test.py --concurrency 5`, khi prompt `day13-chat` đã được cache
(lần gọi đầu tiên sau mỗi lần khởi động server chậm hơn ~1.2s vì phải fetch prompt từ Langfuse):

| Panel | Giá trị baseline | Trạng thái so với threshold |
|---|---|---|
| latency | P50 157 ms · P95 1354 ms · P99 1409 ms | OK (còn xa 3000 ms) |
| traffic | 34 request, ~5.67 request/phút | OK |
| errors | 0% | OK |
| cost | 0.0696 USD tích lũy, 0.002047 USD/request | OK (ngân sách 2.5 USD/ngày) |
| tokens | 1150 in + 4409 out | OK |
| quality | 0.8794 trên 34 mẫu | OK (ngưỡng 0.75) |

P95 cao hơn P50 gần 9 lần là do request đầu tiên sau mỗi lần restart phải fetch prompt từ Langfuse
(~1.2s), các request sau dùng cache 60 giây nên chỉ còn ~157ms. Đây là cold start, không phải sự cố —
cần nhớ khi đọc panel latency ở CP3 để không chẩn đoán nhầm.

Dùng bảng này làm mốc so sánh khi inject incident ở CP3: `rag_slow` phải đẩy panel latency lên
`BREACH`, `tool_fail` đẩy panel errors lên, `cost_spike` đẩy panel cost và tokens lên.
