"""Per-stage wall-clock metrics, appended as JSONL for later capacity fitting.

Each line of `metrics/stages.jsonl` under the data root is one record:
{"episode": <slug or null>, "stage": <script name>, "seconds": <float>, "ok": <bool>}.
Metrics are observability only; callers must not let a metrics failure abort conversion.
"""
import json
import statistics
from pathlib import Path

TAIL_LIMIT = 200


def percentile(values, q):
    """Linear-interpolation percentile of an unsorted sequence (numpy 'linear' method)."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))


def summarize_stage_seconds(rows):
    """Pure: rows -> {stage: {count, median, p90}} over each row's wall seconds."""
    seconds_by_stage = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        stage, seconds = row.get("stage"), row.get("seconds")
        if not isinstance(stage, str) or not stage:
            continue
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            continue
        seconds_by_stage.setdefault(stage, []).append(float(seconds))
    return {
        stage: {
            "count": len(values),
            "median": round(float(statistics.median(values)), 3),
            "p90": round(percentile(values, 0.9), 3),
        }
        for stage, values in seconds_by_stage.items()
    }


def stages_file(root):
    return Path(root) / "metrics" / "stages.jsonl"


def append_stage_record(root, record):
    """Append one JSONL record, creating the metrics directory if needed."""
    path = stages_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def tail_stage_records(path, limit=TAIL_LIMIT):
    """Last `limit` valid JSONL records; blank/corrupt/non-object lines are skipped."""
    if limit <= 0:
        return []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
