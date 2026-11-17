#!/usr/bin/env python3
"""
CPU-Heavy Workload Generator & Host/VM Tracking Web Server.

Features:
1. Generates heavy multi-core CPU load across all available or configured cores.
2. Serves an HTML page and updates an HTML file that continuously appends:
   - VM Name
   - Host Name
   - Timestamp
3. Auto-detects VM Name and Host Name via:
   - Environment variables (VM_NAME, HOST_NAME)
   - OpenStack metadata service (http://169.254.169.254/)
   - Host system inspection (/etc/hostname, /etc/nodename, socket.gethostname())
4. Auto-appends every N seconds (configurable) and on every HTTP request.
"""

import os
import sys
import time
import json
import socket
import signal
import hashlib
import threading
import multiprocessing
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# --- Configuration ---
PORT = int(os.environ.get("PORT", "80"))
APPEND_INTERVAL = int(os.environ.get("APPEND_INTERVAL", "5"))  # seconds between auto-appends
CPU_WORKERS = int(os.environ.get("CPU_WORKERS", "0"))          # 0 = all CPU cores
CPU_LOAD_PERCENT = int(os.environ.get("CPU_LOAD_PERCENT", "100")) # 1 to 100
HTML_FILE_PATH = os.environ.get("HTML_FILE_PATH", "/app/data/index.html")

# Global State
stop_event = multiprocessing.Event()
history_lock = threading.Lock()
records = []
counter = 0


# --- Resolution of VM Name and Host Name ---
def fetch_openstack_metadata():
    """Try querying OpenStack metadata service (169.254.169.254)."""
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/openstack/latest/meta_data.json",
            headers={"User-Agent": "WorkloadAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception:
        return {}


def detect_vm_name():
    """Resolve the VM name."""
    # 1. Environment variable
    if os.environ.get("VM_NAME"):
        return os.environ.get("VM_NAME").strip()

    # 2. OpenStack metadata
    meta = fetch_openstack_metadata()
    if meta.get("name"):
        return meta["name"]

    # 3. /etc/vmname or hostname fallback
    for p in ["/etc/vmname", "/etc/host_vmname"]:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    v = f.read().strip()
                    if v:
                        return v
            except Exception:
                pass

    return socket.gethostname()


def detect_host_name():
    """Resolve the physical compute/host node name."""
    # 1. Environment variable
    if os.environ.get("HOST_NAME"):
        return os.environ.get("HOST_NAME").strip()
    if os.environ.get("NODE_NAME"):
        return os.environ.get("NODE_NAME").strip()

    # 2. OpenStack metadata host / availability zone
    meta = fetch_openstack_metadata()
    if meta.get("meta", {}).get("hostname"):
        return meta["meta"]["hostname"]
    if meta.get("availability_zone"):
        return meta["availability_zone"]

    # 3. Mounted host files
    for p in ["/etc/nodename", "/etc/host_hostname", "/etc/compute_host"]:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    v = f.read().strip()
                    if v:
                        return v
            except Exception:
                pass

    return socket.gethostname()


# --- CPU Heavy Worker ---
def cpu_stress_worker(worker_id, stop_flag, load_percent):
    """
    Burn CPU cycles on a dedicated worker process.
    Supports adjustable load percentage (1-100%).
    """
    duty_cycle = max(0.01, min(1.0, load_percent / 100.0))
    chunk_time = 0.1  # 100ms slice
    work_time = chunk_time * duty_cycle
    sleep_time = chunk_time * (1.0 - duty_cycle)

    data = os.urandom(1024)
    while not stop_flag.is_set():
        start = time.time()
        # Active CPU burn using SHA-256 calculation loop
        while (time.time() - start) < work_time:
            data = hashlib.sha256(data).digest()
        
        # Sleep remainder if load_percent < 100
        if sleep_time > 0.001:
            time.sleep(sleep_time)


# --- HTML Generation & Appending ---
def render_full_html():
    """Render the full HTML document containing all appended rows."""
    with history_lock:
        current_vm = detect_vm_name()
        current_host = detect_host_name()
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        rows_html = ""
        for rec in reversed(records[-100:]):  # Show latest 100 in table
            rows_html += f"""
            <tr>
                <td>{rec['id']}</td>
                <td class="badge-vm">{rec['vm_name']}</td>
                <td class="badge-host">{rec['host_name']}</td>
                <td class="badge-time">{rec['timestamp']}</td>
            </tr>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="{max(3, APPEND_INTERVAL)}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CPU Workload & VM Tracker</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f1f5f9;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --border-color: #334155;
            --badge-vm: #0284c7;
            --badge-host: #10b981;
            --badge-time: #f59e0b;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        header {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        h1 {{
            margin: 0 0 8px 0;
            font-size: 24px;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }}
        .card {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 16px;
        }}
        .card-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 4px;
        }}
        .card-value {{
            font-size: 16px;
            font-weight: 600;
            word-break: break-all;
        }}
        .card-value.highlight {{
            color: var(--accent);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
            font-size: 14px;
        }}
        th {{
            background: rgba(15, 23, 42, 0.9);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 0.05em;
        }}
        tr:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}
        .badge-vm {{
            color: var(--badge-vm);
            font-weight: 600;
        }}
        .badge-host {{
            color: var(--badge-host);
            font-weight: 600;
        }}
        .badge-time {{
            color: var(--badge-time);
            font-family: monospace;
        }}
        .pulse {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 8px #22c55e;
        }}
        footer {{
            text-align: center;
            margin-top: 24px;
            color: var(--text-muted);
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><span class="pulse"></span> CPU Workload &amp; Live Tracking</h1>
            <p style="margin: 0; color: var(--text-muted); font-size: 14px;">
                Continuously appending VM Name, Host Name, and Timestamp.
            </p>
            <div class="status-grid">
                <div class="card">
                    <div class="card-label">Current VM Name</div>
                    <div class="card-value highlight">{current_vm}</div>
                </div>
                <div class="card">
                    <div class="card-label">Current Host Name</div>
                    <div class="card-value" style="color: var(--badge-host);">{current_host}</div>
                </div>
                <div class="card">
                    <div class="card-label">Latest Timestamp</div>
                    <div class="card-value" style="color: var(--badge-time);">{current_time}</div>
                </div>
                <div class="card">
                    <div class="card-label">CPU Status</div>
                    <div class="card-value highlight">{len(multiprocessing.active_children())} Workers @ {CPU_LOAD_PERCENT}%</div>
                </div>
            </div>
        </header>

        <table>
            <thead>
                <tr>
                    <th style="width: 50px;">#</th>
                    <th>VM Name</th>
                    <th>Host Name</th>
                    <th>Timestamp</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">Awaiting records...</td></tr>'}
            </tbody>
        </table>

        <footer>
            Auto-refreshing every {max(3, APPEND_INTERVAL)}s | Total entries: {len(records)} | Endpoints: <code>/</code>, <code>/append</code>, <code>/json</code>, <code>/healthz</code>
        </footer>
    </div>
</body>
</html>
"""
    return html


def append_entry():
    """Append only the 3 required fields: VM Name, Host Name, and Timestamp."""
    global counter
    vm = detect_vm_name() or "unknown-vm"
    host = detect_host_name() or socket.gethostname()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with history_lock:
        counter += 1
        entry = {
            "id": counter,
            "vm_name": vm,
            "host_name": host,
            "timestamp": ts
        }
        records.append(entry)

        # Write to static HTML file so it can also be served or read directly
        try:
            os.makedirs(os.path.dirname(HTML_FILE_PATH), exist_ok=True)
            with open(HTML_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(render_full_html())
        except Exception as e:
            print(f"[ERROR] Failed writing HTML file: {e}", file=sys.stderr)

    return entry


def background_appender():
    """Background loop that appends an entry every APPEND_INTERVAL seconds."""
    # Initial immediate append
    append_entry()
    while not stop_event.is_set():
        time.sleep(APPEND_INTERVAL)
        if not stop_event.is_set():
            append_entry()


# --- HTTP Request Handler ---
class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            html_content = render_full_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))

        elif self.path == "/append":
            # Force an immediate append on request
            entry = append_entry()
            resp = json.dumps({"status": "appended", "entry": entry}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/json":
            with history_lock:
                data = {
                    "current_vm": detect_vm_name(),
                    "current_host": detect_host_name(),
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "total_records": len(records),
                    "records": records[-50:]  # latest 50 records
                }
            resp = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/healthz":
            resp = b"OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        # Suppress noisy HTTP access logs unless desired
        pass


def main():
    workers_count = CPU_WORKERS if CPU_WORKERS > 0 else (os.cpu_count() or 1)
    print(f"=================================================")
    print(f" CPU Workload & VM Tracking Service Starting")
    print(f" Port:             {PORT}")
    print(f" Workers:          {workers_count} (Cores detected: {os.cpu_count()})")
    print(f" CPU Load:         {CPU_LOAD_PERCENT}%")
    print(f" Append Interval:  {APPEND_INTERVAL}s")
    print(f" HTML Path:        {HTML_FILE_PATH}")
    print(f" Initial VM Name:  {detect_vm_name()}")
    print(f" Initial Host:     {detect_host_name()}")
    print(f"=================================================")

    # Handle termination signals
    def handle_signal(sig, frame):
        print("\nShutting down gracefully...")
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # 1. Start CPU worker processes
    workers = []
    for i in range(workers_count):
        p = multiprocessing.Process(
            target=cpu_stress_worker,
            args=(i, stop_event, CPU_LOAD_PERCENT),
            daemon=True
        )
        p.start()
        workers.append(p)
    print(f"[OK] Launched {len(workers)} CPU stress worker processes.")

    # 2. Start background appender thread
    t = threading.Thread(target=background_appender, daemon=True)
    t.start()
    print(f"[OK] Background appender active (interval: {APPEND_INTERVAL}s).")

    # 3. Start HTTP server
    server = ThreadingHTTPServer(("0.0.0.0", PORT), WebHandler)
    print(f"[OK] HTTP Server running on http://0.0.0.0:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
        for p in workers:
            p.join(timeout=1.0)
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
