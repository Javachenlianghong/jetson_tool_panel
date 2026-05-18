"""Parse sync-to-jetson dry-run output for UI review."""

import re


def parse_sync_preview_output(lines):
    changed = 0
    deleted = 0
    rows = []
    notes = []
    for raw in lines:
        line = str(raw or "").rstrip()
        stripped = line.strip()
        match = re.match(r"Changed/new files:\s*(\d+)", stripped)
        if match:
            changed = int(match.group(1))
            continue
        match = re.match(r"Deleted files\s*:\s*(\d+)", stripped)
        if match:
            deleted = int(match.group(1))
            continue
        if stripped.startswith("upload "):
            rows.append({"action": "upload", "path": stripped[len("upload "):].strip(), "detail": "新增或修改"})
        elif stripped.startswith("delete "):
            rows.append({"action": "delete", "path": stripped[len("delete "):].strip(), "detail": "远端删除"})
        elif stripped.startswith("..."):
            rows.append({"action": "more", "path": stripped, "detail": "列表被截断"})
        elif stripped:
            if any(marker in stripped.lower() for marker in ("dry run", "already in sync", "baseline", "state")):
                notes.append(stripped)
    total = changed + deleted
    if total == 0 and not rows:
        summary = "没有发现需要同步的文件变更。"
    else:
        summary = "待上传 {} 个，待删除 {} 个。".format(changed, deleted)
    return {
        "changed": changed,
        "deleted": deleted,
        "total": total,
        "rows": rows,
        "notes": notes,
        "summary": summary,
    }
