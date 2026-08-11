"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

Chạy:
    python scripts/render_dashboard.py
    python scripts/render_dashboard.py --open

Output là một file HTML tĩnh, tự chứa (không cần mạng) để chụp ảnh evidence.
Nguồn dữ liệu và threshold đều đọc từ contract, không hard-code trong template.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

DEFAULT_LOG = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_CONFIG = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_SLO = REPO_ROOT / "config" / "slo.yaml"
DEFAULT_OUT = REPO_ROOT / "submission" / "evidence" / "dashboard.html"


def load_records(log_path: Path, window_minutes: int) -> tuple[list[dict], datetime | None, datetime | None]:
    if not log_path.exists():
        raise SystemExit(f"Không tìm thấy {log_path}. Chạy API và scripts/load_test.py trước.")

    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = rec.get("ts")
        if not ts:
            continue
        rec["_ts"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        records.append(rec)

    if not records:
        raise SystemExit(f"{log_path} chưa có bản ghi hợp lệ nào.")

    newest = max(rec["_ts"] for rec in records)
    cutoff = newest - timedelta(minutes=window_minutes)
    windowed = [rec for rec in records if rec["_ts"] >= cutoff]
    return windowed, cutoff, newest


def by_minute(records: list[dict], value_key: str | None = None) -> dict[str, float]:
    buckets: dict[str, float] = defaultdict(float)
    for rec in records:
        minute = rec["_ts"].strftime("%H:%M")
        buckets[minute] += float(rec.get(value_key, 0) or 0) if value_key else 1
    return dict(sorted(buckets.items()))


def compute_panels(records: list[dict], panels: list[dict]) -> dict[str, dict]:
    responses = [r for r in records if r.get("event") == "response_sent"]
    requests = [r for r in records if r.get("event") == "request_received"]
    failures = [r for r in records if r.get("event") == "request_failed"]
    thresholds = {p["id"]: p["threshold"] for p in panels}

    latencies = [int(r.get("latency_ms", 0)) for r in responses]
    traffic_series = by_minute(requests)
    minutes_covered = max(1, len(traffic_series))
    total_errors = len(failures)
    total_attempts = len(requests) or 1
    costs = [float(r.get("cost_usd", 0) or 0) for r in responses]
    quality = [float(r.get("quality_score", 0) or 0) for r in responses]

    # Mỗi stat mang đơn vị riêng: "tổng request" là count, không phải requests_per_minute.
    return {
        "latency": {
            "stats": [
                ("P50", percentile(latencies, 50), "ms"),
                ("P95", percentile(latencies, 95), "ms"),
                ("P99", percentile(latencies, 99), "ms"),
            ],
            "series": {r["_ts"].strftime("%H:%M:%S"): float(r.get("latency_ms", 0)) for r in responses},
            "value": percentile(latencies, 95),
            "threshold": thresholds["latency"],
        },
        "traffic": {
            "stats": [
                ("Tổng request", len(requests), "requests"),
                ("Request/phút", round(len(requests) / minutes_covered, 2), "requests_per_minute"),
            ],
            "series": traffic_series,
            "value": round(len(requests) / minutes_covered, 2),
            "threshold": thresholds["traffic"],
        },
        "errors": {
            "stats": [
                ("Error rate", round(total_errors / total_attempts * 100, 2), "percent"),
                ("Số request lỗi", total_errors, "requests"),
            ],
            "breakdown": Counter(r.get("error_type", "unknown") for r in failures),
            "value": round(total_errors / total_attempts * 100, 2),
            "threshold": thresholds["errors"],
        },
        "cost": {
            "stats": [
                ("Tổng chi phí", round(sum(costs), 4), "usd"),
                ("Chi phí/request", round(sum(costs) / len(costs), 6) if costs else 0.0, "usd"),
            ],
            "series": by_minute(responses, "cost_usd"),
            "value": round(sum(costs), 4),
            "threshold": thresholds["cost"],
        },
        "tokens": {
            "stats": [
                ("Tokens in", sum(int(r.get("tokens_in", 0) or 0) for r in responses), "tokens"),
                ("Tokens out", sum(int(r.get("tokens_out", 0) or 0) for r in responses), "tokens"),
            ],
            "series": by_minute(responses, "tokens_out"),
            "value": sum(int(r.get("tokens_in", 0) or 0) + int(r.get("tokens_out", 0) or 0) for r in responses),
            "threshold": thresholds["tokens"],
        },
        "quality": {
            "stats": [
                ("Điểm trung bình", round(sum(quality) / len(quality), 4) if quality else 0.0, "score_0_to_1"),
                ("Số mẫu chấm", len(quality), "responses"),
            ],
            "series": {r["_ts"].strftime("%H:%M:%S"): float(r.get("quality_score", 0)) for r in responses},
            "value": round(sum(quality) / len(quality), 4) if quality else 0.0,
            "threshold": thresholds["quality"],
        },
    }


def breaches(value: float, threshold: dict) -> bool:
    if threshold["operator"] == "lte":
        return value > threshold["value"]
    return value < threshold["value"]


def svg_bars(series: dict[str, float], threshold_value: float | None, unit: str) -> str:
    if not series:
        return '<p class="empty">Chưa có dữ liệu trong cửa sổ thời gian này.</p>'

    width, height, pad = 620, 160, 26
    top = 30  # chừa chỗ cho nhãn đỉnh, không để nhãn đè lên cột
    values = list(series.values())
    data_peak = max(values) or 1

    # Thang đo bám theo dữ liệu, không bám theo threshold: SLO 50000 tokens mà dữ liệu chỉ
    # 5000 thì lấy threshold làm đỉnh sẽ ép mọi cột dẹp xuống thành một vạch vô nghĩa.
    # Chỉ kéo thang lên tới threshold khi nó còn nằm trong tầm nhìn của dữ liệu.
    in_frame = threshold_value is not None and threshold_value <= data_peak * 1.25
    peak = max(data_peak, threshold_value) if in_frame else data_peak

    slot = (width - pad * 2) / max(len(values), 1)
    bar_w = max(2.0, slot * 0.62)
    plot_h = height - top - pad

    bars = []
    for i, value in enumerate(values):
        bar_h = max(1.0, (value / peak) * plot_h)
        x = pad + i * slot + (slot - bar_w) / 2
        y = height - pad - bar_h
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="2" class="bar"/>')

    if in_frame:
        y = height - pad - (threshold_value / peak) * plot_h
        slo = (
            f'<line x1="{pad}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}" class="slo"/>'
            f'<text x="{width - pad}" y="{y - 5:.1f}" class="slo-label" text-anchor="end">'
            f'SLO {threshold_value:g} {unit}</text>'
        )
    else:
        # SLO nằm ngoài khung: ghi chú bằng chữ thay vì vẽ một đường sát mép trên.
        slo = (
            f'<text x="{width - pad}" y="14" class="slo-label" text-anchor="end">'
            f'SLO {threshold_value:g} {unit} — ngoài khung</text>'
        )

    keys = list(series.keys())
    labels = (
        f'<text x="{pad}" y="{height - 6}" class="axis">{keys[0]}</text>'
        f'<text x="{width - pad}" y="{height - 6}" class="axis" text-anchor="end">{keys[-1]}</text>'
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="biểu đồ">'
        f'<text x="{pad}" y="14" class="axis">đỉnh: {data_peak:g} {unit}</text>'
        f'{"".join(bars)}{slo}{labels}</svg>'
    )


def render(config: dict, slo: dict, data: dict[str, dict], cutoff, newest, log_path: Path) -> str:
    dash = config["dashboard"]
    panels_html = []

    for panel in dash["panels"]:
        pid = panel["id"]
        computed = data[pid]
        threshold = panel["threshold"]
        op = "≤" if threshold["operator"] == "lte" else "≥"
        breached = breaches(computed["value"], threshold)
        status = "BREACH" if breached else "OK"

        stats = "".join(
            f'<div class="stat"><span class="stat-label">{label}</span>'
            f'<span class="stat-value">{value:g}</span>'
            f'<span class="stat-unit">{stat_unit}</span></div>'
            for label, value, stat_unit in computed["stats"]
        )

        if pid == "errors":
            rows = "".join(
                f"<tr><td>{etype}</td><td>{count}</td></tr>"
                for etype, count in computed["breakdown"].most_common()
            )
            body = (
                f'<table class="breakdown"><thead><tr><th>error_type</th><th>count</th></tr></thead>'
                f"<tbody>{rows}</tbody></table>"
                if rows
                else '<p class="empty">Không có request_failed trong cửa sổ này.</p>'
            )
        else:
            body = svg_bars(computed["series"], threshold["value"], panel["unit"])

        panels_html.append(f"""
      <section class="panel">
        <header>
          <h2>{panel["title"]}</h2>
          <span class="badge {status.lower()}">{status}</span>
        </header>
        <p class="meta">nguồn: <code>{panel["source"]}</code> · đơn vị: <code>{panel["unit"]}</code>
           · threshold: <code>{threshold["aggregation"]} {op} {threshold["value"]:g}</code></p>
        <div class="stats">{stats}</div>
        {body}
        <p class="query"><code>{panel["query"]}</code></p>
      </section>""")

    slis = "".join(
        f"<tr><td>{name}</td><td>{cfg['objective']}</td><td>{cfg['target']}%</td></tr>"
        for name, cfg in slo["slis"].items()
    )

    # Mở bằng file:// nên phải khai báo charset tường minh, nếu không Safari đọc UTF-8
    # thành Latin-1 và toàn bộ tiếng Việt biến thành mojibake.
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{dash["title"]}</title>
<style>
  :root {{ --bg:#f6f7f9; --card:#fff; --ink:#16181d; --muted:#6b7280; --line:#e3e6ea;
           --bar:#3b6fd4; --ok:#127a4b; --breach:#b42318; --slo:#e0602c; }}
  :root:not([data-theme="light"]) {{ }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{ --bg:#0f1115; --card:#171a20; --ink:#e8eaed; --muted:#9aa1ab;
      --line:#272b33; --bar:#6f9bec; --ok:#3fbf85; --breach:#f2776a; --slo:#f2a05c; }}
  }}
  :root[data-theme="dark"] {{ --bg:#0f1115; --card:#171a20; --ink:#e8eaed; --muted:#9aa1ab;
    --line:#272b33; --bar:#6f9bec; --ok:#3fbf85; --breach:#f2776a; --slo:#f2a05c; }}
  body {{ background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
          margin:0; padding:28px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .head-meta {{ color:var(--muted); font-size:13px; margin:0 0 20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; overflow-x:auto; }}
  .panel header {{ display:flex; align-items:center; justify-content:space-between; gap:8px; }}
  h2 {{ font-size:15px; margin:0; }}
  .badge {{ font-size:11px; font-weight:700; letter-spacing:.04em; padding:2px 8px; border-radius:99px; }}
  .badge.ok {{ color:var(--ok); border:1px solid var(--ok); }}
  .badge.breach {{ color:var(--breach); border:1px solid var(--breach); }}
  .meta, .query {{ color:var(--muted); font-size:12px; margin:6px 0; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11.5px; }}
  .stats {{ display:flex; gap:20px; margin:12px 0 8px; flex-wrap:wrap; }}
  .stat {{ display:flex; flex-direction:column; }}
  .stat-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
  .stat-value {{ font-size:24px; font-weight:650; }}
  .stat-unit {{ color:var(--muted); font-size:11px; }}
  svg {{ width:100%; height:auto; }}
  .bar {{ fill:var(--bar); }}
  .slo {{ stroke:var(--slo); stroke-width:1.5; stroke-dasharray:5 4; }}
  .slo-label, .axis {{ fill:var(--muted); font-size:10px; }}
  .slo-label {{ fill:var(--slo); }}
  .empty {{ color:var(--muted); font-size:13px; font-style:italic; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th, td {{ text-align:left; border-bottom:1px solid var(--line); padding:5px 4px; }}
  .slo-table {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
                padding:16px; margin-top:16px; }}
</style>
</head>
<body>
<h1>{dash["title"]}</h1>
<p class="head-meta">
  time range: {dash["time_range_minutes"]} phút ({cutoff:%Y-%m-%d %H:%M:%S} → {newest:%H:%M:%S} UTC)
  · refresh: {dash["refresh_seconds"]}s · nguồn: <code>{log_path.relative_to(REPO_ROOT)}</code>
  · dựng lúc {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC
</p>
<div class="grid">{"".join(panels_html)}</div>
<div class="slo-table">
  <h2>SLO ({slo["service"]}, cửa sổ {slo["window"]})</h2>
  <table><thead><tr><th>SLI</th><th>Objective</th><th>Target</th></tr></thead><tbody>{slis}</tbody></table>
</div>
</body>
</html>
"""


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Dựng dashboard HTML từ log JSONL")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--slo", type=Path, default=DEFAULT_SLO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--open", action="store_true", help="Mở dashboard bằng trình duyệt mặc định")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    slo = yaml.safe_load(args.slo.read_text(encoding="utf-8"))
    window = config["dashboard"]["time_range_minutes"]

    records, cutoff, newest = load_records(args.log, window)
    data = compute_panels(records, config["dashboard"]["panels"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(config, slo, data, cutoff, newest, args.log), encoding="utf-8")

    print(f"Đã dựng {len(config['dashboard']['panels'])} panel từ {len(records)} bản ghi trong {window} phút gần nhất.")
    for panel in config["dashboard"]["panels"]:
        pid = panel["id"]
        state = "BREACH" if breaches(data[pid]["value"], panel["threshold"]) else "OK"
        print(f"  [{state:>6}] {pid:<8} {data[pid]['value']:g} {panel['unit']}")
    print(f"Dashboard: {args.out}")

    if args.open:
        webbrowser.open(args.out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
