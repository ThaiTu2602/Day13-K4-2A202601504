# CP2 — Bằng chứng đổi label và rollback prompt

Prompt: `day13-chat` trên Langfuse Cloud, project dùng chung `day13`. Mọi thay đổi label thực hiện qua
Langfuse API (`PATCH /api/public/v2/prompts/day13-chat/versions/{version}`) và **được xác nhận lại bằng
một request thật đi qua `/chat`**, đọc `prompt_version` từ metadata của trace — không kết luận suông
theo màn hình quản trị.

App cache prompt 60 giây (`cache_ttl_seconds=60` trong `app/prompt_management.py`), nên mỗi lần đổi
label đều restart server trước khi gửi request xác nhận.

## Ba version

| Version | Người tạo | Nội dung | Labels cuối cùng |
|---|---|---|---|
| v1 | API | `Feature/Docs/Question` — template gốc | `baseline`, `production` |
| v2 | API | Thêm `Answer in at most 3 sentences. Cite the retrieved docs when relevant.` | `candidate` |
| v3 | Tuyen230605 (UI) | Bản tiếng Việt: *"Bạn là một trợ lý AI xử lý tính năng…"* | `latest` |

Cả ba giữ nguyên ba biến bắt buộc `{{feature}}`, `{{docs}}`, `{{message}}` theo contract trong
`docs/PROMPT_VERSIONING.md`. Nội dung đầy đủ của v1/v2 nằm ở [`cp2-prompt-versions.json`](cp2-prompt-versions.json).

## Vòng 1 — cùng một input, hai label khác nhau

Input dùng chung: `{"user_id":"student-10","session_id":"s10","feature":"qa","message":"How should alerts be designed?"}`

| Label khi chạy | Trace ID | correlation_id | `prompt_version` ghi trong trace |
|---|---|---|---|
| `production` | `141483ab1bc3963b8ab2aa09a0b60ca5` | `req-9869c14f` | 1 |
| `candidate` | `e965c7e0e25dc7399bffafc8656fb779` | `req-3ce4c854` | 2 |

Đổi label lần đầu (`production` v1 → v2 → rollback v1) cũng đã được xác nhận bằng trace:

| Bước | Trace ID | `prompt_version` |
|---|---|---|
| Promote `production` sang v2 | `885a68edca070b10c5b6140bdc7041b9` (`req-ecc920f9`) | 2 |
| Rollback `production` về v1 | `085785e427dd7f723bd6c65634359b07` (`req-fa56c906`) | 1 |

## Vòng 2 — rollback khỏi v3 của team

Sau vòng 1, một thành viên khác tạo **v3** qua giao diện Langfuse và v3 nhận toàn bộ label
(`baseline`, `candidate`, `latest`, `production`). Nhóm diễn lại quy trình rollback trên đúng
trạng thái đó, vì đây mới là tình huống thật: một prompt mới được đẩy lên `production` và cần đưa
về bản đã biết là ổn định.

| Bước | Trạng thái label sau bước | correlation_id | Trace ID | `prompt_version` đọc từ trace |
|---|---|---|---|---|
| Hiện trạng: v3 giữ mọi label | v1: — · v2: — · v3: `baseline`,`candidate`,`latest`,`production` | `req-410c1a68` | `a2ebfc73dd6317a8d3cdf6b2c144328f` | **3** |
| Rollback `production` + `baseline` về v1, `candidate` về v2 | v1: `baseline`,`production` · v2: `candidate` · v3: `latest` | `req-2d5da29f` | `fb3e2e439547ccbca78d9538fa0e6e1d` | **1** |

Nội dung v3 **không bị xoá** — v3 vẫn còn nguyên trên Langfuse và giữ label `latest`; chỉ có việc
`production` trỏ về đâu là thay đổi.

## Điều rút ra

Label `LANGFUSE_PROMPT_LABEL=production` trong `.env` **không đổi ở bất kỳ bước nào** trong cả hai vòng.
Chỉ có version mà label đó trỏ tới là thay đổi. Vì vậy rollback prompt không cần sửa code, không cần
deploy lại, và mất đúng một lần restart để hết cache 60 giây.

Đây cũng là mitigation tạm thời được ghi trong runbook của alert `daily_cost_budget_exceeded`
([`docs/alerts.md`](../../docs/alerts.md)): khi một prompt version mới làm chi phí tăng, chuyển label
`production` về version cũ là cách dừng chảy máu nhanh nhất.

## Ảnh cần chụp bổ sung từ giao diện Langfuse

- [ ] Trang `Prompts → day13-chat`, thấy v1 mang `production` + `baseline`, v2 mang `candidate`, v3 mang `latest`.
- [ ] Trace `a2ebfc73…` và `fb3e2e43…` mở cạnh nhau, thấy `prompt_version` 3 và 1 trong metadata.
