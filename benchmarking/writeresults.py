#!/usr/bin/env python3
import argparse, csv, json, math, os, sys
from typing import Dict, List, Iterable, Tuple

def parse_args():
    p = argparse.ArgumentParser(
        description="Write JSON key/values as rows and each JSON source as a column in a CSV."
    )
    p.add_argument(
        "--input-dir",
        required=True,
        help="Directory to recursively scan for input JSON files (only *summary.json files are used).",
    )
    p.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the output CSV will be written.",
    )
    return p.parse_args()

def to_cell(v):
    if isinstance(v, float):
        if math.isnan(v): return "NaN"
        if math.isinf(v): return "Infinity" if v > 0 else "-Infinity"
        return repr(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    return "" if v is None else str(v)

def load_json_file(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())

def list_json_files(args) -> List[str]:
    files: List[str] = []
    # Recursively walk the input directory and collect only *summary.json files
    for dirpath, _, filenames in os.walk(args.input_dir):
        for fn in filenames:
            if fn.lower().endswith("summary.json"):
                files.append(os.path.join(dirpath, fn))
    # Deduplicate & sort for stability
    files = sorted(set(os.path.abspath(f) for f in files))
    return files

def derive_col_header(data: Dict, path: str, policy: str, explicit: str = None, existing=None) -> str:
    if explicit:
        base = explicit
    else:
        if policy == "name":
            base = str(data.get("name", os.path.splitext(os.path.basename(path))[0]))
        elif policy == "filename":
            base = os.path.splitext(os.path.basename(path))[0]
        else:
            base = str(data.get("name") or os.path.splitext(os.path.basename(path))[0])
    return unique_header(base, existing or set())

def unique_header(base: str, existing: set) -> str:
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"

def load_existing(csv_path: str) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    if not os.path.exists(csv_path):
        return [], {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        if not cols or cols[0] != "metric":
            raise SystemExit(f"CSV {csv_path} must have 'metric' as the first header.")
        rows = {}
        for row in reader:
            metric = row.get("metric", "")
            rows[metric] = {k: row.get(k, "") for k in cols if k != "metric"}
        return cols[1:], rows

def write_csv(csv_path: str, all_cols: List[str], rows: List[Dict[str, str]]):
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        writer.writerows(rows)

def main():
    args = parse_args()

    csv_path = os.path.join(os.path.abspath(args.output_dir), "summary_metrics.csv")

    # Discover inputs
    json_files = list_json_files(args)
    if not json_files:
        raise SystemExit(
            "No JSON files found. Ensure there are files ending with *summary.json under --input-dir."
        )

    # Metrics to record (columns)
    selected_metrics = [
        "results_client_ttft_s_mean",
        "results_client_end_to_end_latency_s_mean",
        "results_client_output_token_per_s_per_request_mean",
        "results_server_ttft_s_mean",
        "results_server_end_to_end_latency_s_mean",
        "results_server_output_token_per_s_per_request_mean",
        "results_num_requests_started",
        "results_error_rate",
        "results_number_errors",
        "results_client_total_output_throughput",
        "results_num_completed_requests",
        "results_num_completed_requests_per_min",
    ]

    # Build rows: one row per QPS, columns are metrics
    rows = []
    for jf in json_files:
        try:
            data = load_json_file(jf)
        except Exception as e:
            print(f"Warning: skipping '{jf}' due to error: {e}", file=sys.stderr)
            continue

        qps = data.get("qps")
        if qps is None:
            print(f"Warning: skipping '{jf}' because it has no 'qps' field.", file=sys.stderr)
            continue

        row: Dict[str, str] = {"qps": to_cell(qps)}
        for metric in selected_metrics:
            row[metric] = to_cell(data.get(metric))
        rows.append(row)

    # Sort rows by QPS value (ascending)
    try:
        rows.sort(key=lambda r: float(r["qps"]))
    except Exception:
        pass

    # Prepare final columns: first qps, then metrics
    all_cols = ["qps"] + selected_metrics

    write_csv(csv_path, all_cols, rows)

    print(f"Wrote {len(rows)} rows into {csv_path} with {len(selected_metrics)} metrics.")

if __name__ == "__main__":
    main()
