
import json
from collections import Counter

CATEGORICAL_FIELDS = {"blood_group", "status", "reason", "blood_bank_name", "order_line_items"}
NUMERIC_FIELDS = {"age"}

def compress_value(v, limit=80):
    if v is None:
        return "None"
    if isinstance(v, str) and len(v) > limit:
        return v[:limit] + "...(truncated)"
    return v

def flatten_toon(obj, path="", out=None, visited=None):
    if out is None: out = {}
    if visited is None: visited = set()

    oid = id(obj)
    if oid in visited:
        return out
    visited.add(oid)

    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            flatten_toon(v, new_path, out, visited)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_path = f"{path}[{i}]"
            flatten_toon(v, new_path, out, visited)
    else:
        out[path] = compress_value(obj)
    return out

def format_toon(data):
    """Compact TOON using only fields actually present in the record"""
    if not isinstance(data, list):
        data = [data]

    toon_lines = []
    for record in data:
        final = {}
        for key, val in record.items():
            if val is not None:
                if key == "order_line_items" and isinstance(val, list):
                    final[key] = len(val)
                else:
                    final[key] = compress_value(val)
        toon_lines.append(" | ".join(f"{k}:{v}" for k, v in final.items()))
    return "\n".join(toon_lines)

def summary_toon(data):
    """
    Aggregated summary in TOON form:
    - Only include fields that exist in input
    - Categorical fields: count/frequencies
    - Numeric fields: min, max, avg, count
    """
    if not isinstance(data, list):
        data = [data]

    cat_counters = {}
    num_values = {}

    for record in data:
        for field in CATEGORICAL_FIELDS:
            val = record.get(field)
            if val is None:
                continue
            if field == "order_line_items":
                if isinstance(val, list) and val:
                    if field not in cat_counters:
                        cat_counters[field] = Counter()
                        cat_counters[field]["units_total"] = 0
                        cat_counters[field]["records_with_items"] = 0
                    total_units = sum(item.get("unit", 0) for item in val if isinstance(item, dict))
                    cat_counters[field]["units_total"] += total_units
                    cat_counters[field]["records_with_items"] += 1
            else:
                if field not in cat_counters:
                    cat_counters[field] = Counter()
                cat_counters[field][str(val)] += 1

        for field in NUMERIC_FIELDS:
            val = record.get(field)
            if isinstance(val, (int, float)):
                if field not in num_values:
                    num_values[field] = []
                num_values[field].append(val)

    summary = {}

    for field, counter in cat_counters.items():
        if counter:
            summary[field] = dict(counter)

    for field, vals in num_values.items():
        if vals:
            summary[field] = {
                "min": min(vals),
                "max": max(vals),
                "avg": sum(vals)/len(vals),
                "count": len(vals)
            }

    return " | ".join(f"{k}:{json.dumps(v)}" for k,v in summary.items())

