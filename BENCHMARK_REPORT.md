# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích trực tiếp từ các file JSON trong `reports/`, file CSV trong `benchmark-results/`, log JSON thực tế của container `agent`, và screenshot trong `screenshots/`.

**Họ tên:** Phạm Hồng Khánh Huy  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows + Docker Desktop (Linux engine)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Mock LLM mặc định ~`120–180 ms` + retrieval ~`20 ms`; ngưỡng `500 ms` đủ bao phủ phần lớn request bình thường và phát hiện sớm khi hệ thống nghẽn hoặc tail latency tăng cao. |
| Error rate `/ask` | `< 2 %` | Tỷ lệ lỗi mặc định `MOCK_ERROR_RATE=0.01` (1%); vượt 2% là dấu hiệu bất thường từ upstream hoặc lỗi ứng dụng cần cảnh báo. |
| Accuracy trên golden dataset | `≥ 85 %` (mục tiêu `100 %` sau khi bổ sung KB) | Chặn regression trước khi deploy trong CI (`eval/run_eval.py --min-accuracy 0.85`). |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Nguồn: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json` (mỗi mức 300 requests, `MOCK_ERROR_RATE=0`).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.38 | 195.6 | 235.6 | 1682.5 | 0.0% | PASS |
| 10 | 36.70 | 191.6 | 433.2 | 1704.9 | 0.0% | PASS |
| 50 | 99.00 | 195.8 | 525.2 | 1723.5 | 0.0% | FAIL (`p95 > 500ms`) |
| 100 | 57.83 | 622.2 | 3149.2 | 3342.9 | 0.0% | FAIL (`p95 > 500ms`) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Không tăng tuyến tính ở mức cao.** Từ `1 → 10 → 50`, RPS tăng mạnh (`4.38 → 36.70 → 99.00 req/s`) nhờ `await asyncio.sleep(...)` xử lý đồng thời không block event loop. Tuy nhiên đến `concurrency = 100`, RPS tụt xuống `57.83 req/s` và `p50`/`p95` tăng vọt (`622.2 ms` / `3149.2 ms`) do 1 process uvicorn + hàng đợi kết nối trên Windows bị bão hòa khi dồn quá nhiều kết nối đồng thời.

### 2.2 Tail latency

Nguồn: `reports/load_v2_slow0.json`, `reports/load_v2_slow003.json`, `reports/load_v2_slow01.json` (concurrency = 20, 300 requests).

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 202.3 | 426.6 | 464.8 |
| 0.03 (mặc định) | 208.6 | 222.5 | 1688.3 |
| 0.1 | 339.1 | 1675.9 | 1739.6 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **`p99`** (và tiếp theo là `p95` khi tỷ lệ chậm vượt 5%) nhạy nhất: từ `MOCK_SLOW_RATE=0` lên `0.03`, `avg` chỉ tăng nhẹ `+6.3 ms` (`202.3 → 208.6 ms`), nhưng `p99` nhảy vọt gấp **3.6 lần** (`464.8 → 1688.3 ms`). Khi lên `0.1`, cả `p95` cũng vọt lên `1675.9 ms`.
- Không nên đặt SLO theo **average** vì 90–97% request nhanh sẽ kéo giá trị trung bình xuống thấp, che giấu trải nghiệm tệ của nhóm người dùng rơi vào tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` (23 câu hỏi trong `golden_dataset.jsonl`).

| Chỉ số | Agent v1 | Agent v2 (KB gốc) | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (`1/23`) | 91.3% (`21/23`) | **100.0% (`23/23`)** |
| Avg tokens / câu | 56.9 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000402 | $0.000760 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040155 | $0.00003619 | **$0.00003436** |
| Quality gate | FAIL | PASS (ngưỡng mặc định 80%, còn 2 câu sai) | **PASS (`--min-accuracy 1.0`, 0 regression)** |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` vào cuối `KNOWLEDGE_BASE` trong `06-lab-complete/benchmark-observability/develop/utils/mock_llm.py`. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` vào cuối `KNOWLEDGE_BASE` trong `06-lab-complete/benchmark-observability/develop/utils/mock_llm.py`. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- Agent `v2` tốn gần gấp đôi token mỗi câu (`113.7` vs `56.9`) và tăng nhẹ tổng cost (`$0.000790` vs `$0.000402`) do đính kèm context từ bước retrieval (`~20 ms`). Tuy nhiên accuracy tăng từ `4.3%` lên `100.0%`, kéo **chi phí trên mỗi câu trả lời đúng** giảm hơn **11 lần** (`$0.00040155 → $0.00003436`).

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với các alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

Trong lần chạy fault-injection tổng hợp (`MOCK_ERROR_RATE=0.25`, `MOCK_SLOW_RATE=0.35`, `LLM_MODEL=mock-llm-large`, kết hợp `docker pause` 1 trong 2 container `agent` dưới tải Locust 25 users), cả **4/4 alert** trong [alert_rules.yml](06-lab-complete/benchmark-observability/production/prometheus/alert_rules.yml) đều chuyển sang trạng thái **`firing`**:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.25` | `AgentHighErrorRate` (`error rate > 5%`) | ~1 phút (`for: 1m`, `activeAt: 10:27:17Z`) | `Error rate` (`23.91%`) & `Requests/s theo status code` (`503`) |
| B | `MOCK_SLOW_RATE=0.35` | `AgentHighLatencyP95` (`p95 > 1s`) | ~2 phút (`for: 2m`, `activeAt: 10:27:12Z`) | `Latency p95` (`1.93s`) & `Latency /ask — p50 / p95 / p99` |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`burn rate > $2/giờ`) | ~2 phút (`for: 2m`, `activeAt: 10:23:17Z`) | `LLM cost (1h)` (`$5.8380`) & `Cost burn rate (USD/giờ)` |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`up == 0`) | ~30 giây (`for: 30s`, `activeAt: 10:27:12Z`) | `Instances up` (từ `2` giảm còn `1`) |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | N/A | Chỉ đổi label `agent_info{version="v1"}` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Chạy **eval tự động trên golden dataset** trong CI/CD (`.github/workflows/eval.yml` chạy `eval/run_eval.py --min-accuracy 0.85`) để chặn deploy khi có regression, kết hợp **online eval** (lấy mẫu traffic thật, LLM-as-judge, tỷ lệ retrieval hit/miss `RETRIEVAL_HITS`, và feedback người dùng).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger ([jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)):

- `trace_id`: `6521f342c43da3aa83ef916563a0760c`
- Tổng thời gian: `2008.4 ms` (`2.0s` trên Jaeger UI)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-large` (`1982.8 ms` trong log / `2.0s` trên Jaeger UI, chiếm **`~98.7%`** tổng thời gian; bước `agent.retrieve_context` chỉ mất `23.2 ms`)
- Dòng log tương ứng (trích từ `docker compose logs agent` theo `trace_id`):

```json
{"ts": "2026-11-25T10:30:20.536807+00:00", "level": "INFO", "service": "observable-agent", "instance": "d39173d28805", "event": "llm_call", "trace_id": "6521f342c43da3aa83ef916563a0760c", "span_id": "b5cb394dad701597", "request_id": "8cc2569570c9", "model": "mock-llm-large", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 0.000788, "llm_ms": 1982.8}
{"ts": "2026-11-25T10:30:20.537139+00:00", "level": "INFO", "service": "observable-agent", "instance": "d39173d28805", "event": "http_request", "trace_id": "6521f342c43da3aa83ef916563a0760c", "span_id": "b5cb394dad701597", "request_id": "8cc2569570c9", "method": "POST", "route": "/ask", "status": 200, "ms": 2008.4}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated`; trong ngoặc là số liệu riêng của `POST /ask`).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.87 (`/ask`: 59.77) | 190 | 240 (`/ask`: 250) | 1700 | 72 / 7868 (`0.92%`) |
| 3 | 66.05 (`/ask`: 59.93) | 190 | 220 (`/ask`: 220) | 1700 | 71 / 7890 (`0.90%`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Có cải thiện nhẹ `p95`** (`250 ms → 220 ms` cho `/ask`, `240 ms → 220 ms` Aggregated) nhờ giảm cạnh tranh/queuing trên event loop giữa các container.
- **RPS hầu như giữ nguyên (~`66 req/s`)** vì ở bài test này `100` user của Locust đều có `wait_time = between(0.5, 2)` (nghỉ trung bình ~`1.25s` sau mỗi request) nên tổng tốc độ sinh tải từ phía Locust chỉ đạt ~`66 req/s`, chưa làm bão hòa CPU của 1 instance async FastAPI.
- **`p99` giữ ở `1700 ms`** vì tail latency đến từ từng lời gọi mock LLM (`MOCK_SLOW_RATE=0.03` cộng thêm `1500 ms`), không phải từ CPU nên scale thêm replica không giảm được `p99` của một request đơn lẻ.
- **Tỷ lệ lỗi ~`0.9%`** khớp đúng với cấu hình `MOCK_ERROR_RATE=0.01` cho `/ask` (`72/7139` và `71/7159` request `/ask`).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Latency trung bình dễ đánh lừa; **percentile (`p95`/`p99`)** mới phản ánh đúng tail latency và trải nghiệm thực tế của người dùng.
  2. Tránh đưa label cardinality cao (`user_id`, `request_id`, URL thô) vào Prometheus metrics; hãy dùng Histogram cho phân bố giá trị và dùng structured JSON logs + OpenTelemetry `trace_id` để nhảy trực tiếp tới trace trên Jaeger khi debug.
  3. Infrastructure alerts (Prometheus) chỉ bắt được lỗi hạ tầng/tài nguyên, không phát hiện được tụt chất lượng trả lời (`AGENT_VERSION=v1`) — cần **eval quality gate trên golden dataset** trước khi deploy.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Theo dõi tỷ lệ `429 Rate Limit` / `402 Cost Guard`, tỷ lệ retrieval hit/miss (`agent_retrieval_total`), alert theo SLO error budget burn rate, và cấu hình Alertmanager gửi cảnh báo về Slack/PagerDuty.
