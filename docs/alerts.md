# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.
Cấu hình máy đọc được nằm ở [`config/alert_rules.yaml`](../config/alert_rules.yaml); ngưỡng SLO nằm ở
[`config/slo.yaml`](../config/slo.yaml); panel tương ứng nằm ở [`config/dashboard.yaml`](../config/dashboard.yaml).

Luồng xử lý chung cho cả ba alert: **Metrics → Traces → Logs**. Bắt đầu từ panel bị breach, mở trace
chậm/lỗi trong khoảng thời gian đó, rồi dùng `correlation_id` trong metadata của trace để tìm đúng
log line trong `data/logs.jsonl`.

## Alert 1

- **Tên:** `chat_slow_for_users`
- **Severity:** warning
- **SLI/SLO liên quan:** `latency_p95_ms` — objective 3000ms, target 99.5% (`config/slo.yaml`)
- **Điều kiện và thời gian duy trì:** `latency_p95 > 3000ms` liên tục **5 phút**, tính trên
  `response_sent.latency_ms` trong cửa sổ 60 phút của panel `latency`.
- **Ảnh hưởng tới người dùng:** người dùng gõ câu hỏi và phải chờ quá 3 giây mới thấy câu trả lời;
  ở mức P95 nghĩa là cứ 20 request thì có 1 request chậm rõ rệt. Client có timeout ngắn sẽ bị hủy request.
- **Ba bước kiểm tra đầu tiên:**
  1. Mở panel `latency` và so P50 với P95. P50 vẫn thấp mà P95 tăng ⇒ chỉ một nhánh request bị chậm
     (tail latency), không phải toàn hệ thống; P50 tăng cùng ⇒ nghi ngờ phụ thuộc dùng chung.
  2. Mở Langfuse, lọc trace trong đúng khung giờ và sắp xếp theo latency giảm dần. Xem waterfall để biết
     span nào chiếm thời gian: `retrieve` (RAG/vector store) hay `generate` (LLM).
  3. Lấy `correlation_id` trong metadata của trace chậm, `grep` nó trong `data/logs.jsonl` để đối chiếu
     `latency_ms`, `feature`, `model` và xem có `request_failed` đi kèm không.
- **Mitigation tạm thời:** nếu span `retrieve` là thủ phạm, tắt sự cố đang inject
  (`python scripts/inject_incident.py --scenario rag_slow --disable`) hoặc hạ timeout của vector store
  để fail nhanh và trả fallback answer thay vì bắt người dùng chờ; nếu `generate` chậm, giảm số token
  đầu ra hoặc chuyển tạm sang model nhanh hơn. Thông báo tình trạng suy giảm cho người dùng.
- **Owner:** on-call-engineer

## Alert 2

- **Tên:** `chat_requests_failing`
- **Severity:** critical
- **SLI/SLO liên quan:** `error_rate_pct` — objective 2%, target 99.0%
- **Điều kiện và thời gian duy trì:** `count(request_failed) / count(request_received) * 100 > 5`
  liên tục **3 phút**. Ngưỡng alert (5%) cao hơn ngưỡng SLO (2%) để chỉ đánh thức người trực khi
  error budget đang bị đốt nhanh, không phải mỗi lần có lỗi lẻ.
- **Ảnh hưởng tới người dùng:** người dùng nhận HTTP 500 và không có câu trả lời nào — mất hoàn toàn
  chức năng, không chỉ chậm. Đây là lý do severity là critical còn Alert 1 chỉ là warning.
- **Ba bước kiểm tra đầu tiên:**
  1. Mở panel `errors`, đọc bảng breakdown theo `error_type` để biết lỗi tập trung vào một loại
     (ví dụ `RuntimeError` từ vector store) hay rải đều nhiều loại.
  2. Lọc log `event == "request_failed"` trong `data/logs.jsonl`, xem `payload.detail` và trường
     `feature` để biết lỗi có giới hạn ở một feature hay toàn bộ traffic.
  3. Lấy `correlation_id` của một request lỗi, mở trace tương ứng trên Langfuse và xem span nào ném
     exception; đối chiếu với `/health` để biết incident flag nào đang bật.
- **Mitigation tạm thời:** tắt incident đang bật (`python scripts/inject_incident.py --scenario tool_fail --disable`);
  nếu phụ thuộc ngoài thật sự chết, cho `retrieve` trả về danh sách rỗng và để agent chạy fallback answer
  (degraded nhưng còn dùng được) thay vì để exception nổi lên thành 500. Rollback deploy gần nhất nếu
  lỗi bắt đầu ngay sau khi triển khai.
- **Owner:** on-call-engineer

## Alert 3

- **Tên:** `daily_cost_budget_exceeded`
- **Severity:** warning
- **SLI/SLO liên quan:** `daily_cost_usd` — objective 2.5 USD/ngày
- **Điều kiện và thời gian duy trì:** `sum(cost_usd) > 2.5` trong cửa sổ **24 giờ**. Không cần
  "duy trì trong n phút" vì đây là chỉ số tích lũy, đã vượt là đã tốn tiền thật.
- **Ảnh hưởng tới người dùng:** không ảnh hưởng trực tiếp tới chất lượng câu trả lời, nhưng vượt
  ngân sách vận hành. Nếu không xử lý, biện pháp cắt giảm sau đó (giới hạn rate, hạ cấp model) mới là
  thứ người dùng cảm nhận được.
- **Ba bước kiểm tra đầu tiên:**
  1. Mở panel `cost` và panel `traffic` cạnh nhau. Chi phí tăng cùng traffic ⇒ tăng trưởng bình thường;
     chi phí tăng mà traffic phẳng ⇒ chi phí trên mỗi request đã tăng, đây mới là sự cố.
  2. Mở panel `tokens`: so `tokens_out` với `tokens_in`. `tokens_out` phình bất thường là dấu hiệu kinh
     điển của cost spike (kịch bản `cost_spike` nhân output_tokens lên 4 lần).
  3. Mở vài trace đắt nhất trên Langfuse, đọc `usage_details` và `cost_details` của span `run`, rồi đối
     chiếu `prompt_version` trong metadata — một prompt version mới dài hơn cũng làm chi phí tăng.
- **Mitigation tạm thời:** rollback prompt về version cũ bằng cách chuyển label `production`
  (xem [PROMPT_VERSIONING.md](PROMPT_VERSIONING.md)); đặt trần `max_tokens` cho output; tắt kịch bản
  `cost_spike` nếu đang được inject. Thông báo team-lead trước khi nới ngân sách.
- **Owner:** team-lead

## Vì sao alert phải dựa trên triệu chứng

Alert theo triệu chứng (`chat_slow_for_users`) mô tả điều người dùng chịu đựng; alert theo nguyên nhân
(`vector_store_timeout_count`) mô tả một cách hỏng cụ thể mà ta đã đoán trước.

- **Số cách hỏng là vô hạn, số triệu chứng thì hữu hạn.** Một alert trên `latency_p95` bắt được cả RAG
  chậm, LLM chậm, GC pause, hàng đợi đầy lẫn nguyên nhân chưa ai nghĩ tới. Muốn phủ bằng alert theo
  nguyên nhân, ta phải viết trước một rule cho từng khả năng — và sự cố thật luôn là cái chưa có rule.
- **Alert theo tên hàm mục nát theo mỗi lần refactor.** Đổi `retrieve()` sang tên khác hoặc thay vector
  store là alert im lặng, trong khi hệ thống vẫn hỏng. Ràng buộc vào `latency_p95` của
  `response_sent` thì tồn tại lâu bằng hợp đồng với người dùng.
- **Alert theo nguyên nhân tạo cả báo động giả lẫn báo động thiếu.** Vector store timeout một nhịp rồi
  retry thành công thì người dùng không hề hấn gì — đánh thức người trực lúc 3 giờ sáng là lãng phí.
  Ngược lại, mỗi thành phần đều "khỏe" nhưng tổng thời gian vẫn vượt 3 giây thì không rule nào nổ.
- **Đánh thức người trực phải tương xứng với thiệt hại.** Trang bị theo triệu chứng nghĩa là mọi lần
  bị đánh thức đều tương ứng với một điều xấu có thật đang xảy ra với người dùng, nên độ tin cậy của
  alert được giữ và không ai tập nhiễm thói quen bỏ qua cảnh báo.

Nguyên nhân không biến mất khỏi quy trình — nó chuyển từ *điều kiện kích hoạt* sang *bước điều tra*.
Đó chính là mục "Ba bước kiểm tra đầu tiên" của mỗi runbook ở trên: alert nói **"có gì đó đang hỏng với
người dùng"**, còn Metrics → Traces → Logs mới trả lời **"hỏng ở đâu"**.
