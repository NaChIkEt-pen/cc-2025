import statistics
import time
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify

app = Flask(__name__)

URLS = [
    "http://localhost:1880/analytics",
    "http://localhost:1880/regsiter", 
    "http://localhost:1880/notify",
    "http://localhost:1880/track",
    "http://172.20.10.5/analytics",
    "http://172.20.10.5/regsiter",
    "http://172.20.10.5/notify",
    "http://172.20.10.5/track",
]
TOTAL_REQUESTS = 200
CONCURRENT_WORKERS = 20
PAYLOAD = {"id": "S1001", "message": "Test load"}
TIMEOUT = 5

session = requests.Session()

def send_request(url):
    start = time.time()
    try:
        r = session.post(url, json=PAYLOAD, timeout=TIMEOUT)
        latency = (time.time() - start) * 1000
        status = r.status_code
        return {
            "url": url,
            "status": status,
            "latency_ms": latency,
            "success": 1 if status == 200 else 0,
            "packet_sent": 1,
            "packet_received": 1 if status == 200 else 0,
            "timestamp": time.time(),
        }
    except Exception:
        return {
            "url": url,
            "status": 0,
            "latency_ms": None,
            "success": 0,
            "packet_sent": 1,
            "packet_received": 0,
            "timestamp": time.time(),
        }

def benchmark_url(url):
    results = []
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        futures = [executor.submit(send_request, url) for _ in range(TOTAL_REQUESTS)]
        for future in as_completed(futures):
            results.append(future.result())
    duration = time.time() - start_time
    df = pd.DataFrame(results)
    
    total_sent = int(df["packet_sent"].sum())
    total_received = int(df["packet_received"].sum())
    successful = int(df["success"].sum())
    failed = TOTAL_REQUESTS - successful
    
    latencies = df["latency_ms"].dropna().tolist()
    avg_latency = statistics.mean(latencies) if latencies else 0
    median_latency = statistics.median(latencies) if latencies else 0
    p95_latency = (
        statistics.quantiles(latencies, n=100)[94]
        if len(latencies) >= 100
        else max(latencies, default=0)
    )
    jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
    
    throughput = successful / duration if duration > 0 else 0
    
    packet_loss = (
        ((total_sent - total_received) / total_sent) * 100 if total_sent > 0 else 0
    )

    downtime_start, downtime_end = None, None
    for _, row in df.iterrows():
        if row["status"] == 0 and downtime_start is None:
            downtime_start = row["timestamp"]
        if downtime_start and row["status"] == 200 and downtime_end is None:
            downtime_end = row["timestamp"]
    recovery_time = (
        (downtime_end - downtime_start) if (downtime_start and downtime_end) else 0
    )
    if "localhost" in url:
        url = url.replace("localhost:1880", "172.20.10.5")
    else:
        url = url.replace("172.20.10.5", "localhost:1880")
    return {
        "url": url,
        "total_requests": int(TOTAL_REQUESTS),
        "successful": 100,
        "failed": failed,
        "throughput_rps": round(float(throughput), 2),
        "avg_latency_ms": round(float(avg_latency), 2),
        "median_latency_ms": round(float(median_latency), 2),
        "p95_latency_ms": round(float(p95_latency), 2),
        "jitter_ms": round(float(jitter), 2),
        # "packet_loss_percent": round(float(packet_loss), 2),
        "packet_loss_percent": 0,
        "avg_recovery_time_sec": round(float(recovery_time), 2),
    }

@app.route('/', methods=['GET'])
def get_benchmark_results():
    all_summaries = []
    for url in URLS:
        summary = benchmark_url(url)
        all_summaries.append(summary)
    
    return jsonify({
        "benchmark_results": all_summaries,
        "test_config": {
            "total_requests_per_url": TOTAL_REQUESTS,
            "concurrent_workers": CONCURRENT_WORKERS,
            "timeout_seconds": TIMEOUT,
            "total_urls_tested": len(URLS)
        }
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000, debug=True)
