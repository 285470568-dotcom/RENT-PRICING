"""竞品库刷新：从 data/inbox/*.csv 导入，打 as_of，写回主库并归档。"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MAIN = DATA / "shanghai_competitors.json"
INBOX = DATA / "inbox"
ARCHIVE = DATA / "archive"

REQUIRED = ("name", "district", "lng", "lat", "area", "price")


def _norm_row(row: dict[str, str], default_as_of: str) -> dict[str, Any] | None:
    name = (row.get("name") or "").strip()
    if not name or name.startswith("示例"):
        # 跳过模板示例行（可用 --keep-sample 保留）
        if name.startswith("示例") and not row.get("_keep_sample"):
            return None
    try:
        item = {
            "name": name,
            "district": (row.get("district") or "").strip().replace("区", ""),
            "address": (row.get("address") or "").strip() or f"上海市{row.get('district','')}{name}",
            "lng": float(row["lng"]),
            "lat": float(row["lat"]),
            "layout": (row.get("layout") or "一室一厅").strip(),
            "area": float(row["area"]),
            "area_basis": (row.get("area_basis") or "套内").strip(),
            "price": float(row["price"]),
            "source": (row.get("source") or "人工导入").strip(),
            "segment": (row.get("segment") or "集中式公寓").strip(),
            "community": (row.get("community") or name).strip(),
            "as_of": (row.get("as_of") or default_as_of).strip(),
        }
    except (KeyError, TypeError, ValueError):
        return None
    for k in REQUIRED:
        if item.get(k) in ("", None):
            return None
    if item["price"] <= 0 or item["area"] <= 0:
        return None
    return item


def _key(item: dict[str, Any]) -> str:
    return f"{item.get('name')}|{round(float(item['lng']),5)}|{round(float(item['lat']),5)}"


def load_main() -> list[dict[str, Any]]:
    if not MAIN.exists():
        return []
    return json.loads(MAIN.read_text(encoding="utf-8"))


def ensure_as_of(items: list[dict[str, Any]], default_as_of: str) -> list[dict[str, Any]]:
    out = []
    for x in items:
        y = dict(x)
        y.setdefault("as_of", default_as_of)
        out.append(y)
    return out


def merge(base: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by = {_key(x): x for x in base}
    stats = {"added": 0, "updated": 0, "skipped": 0}
    for item in incoming:
        k = _key(item)
        if k in by:
            old = by[k]
            # 同 key 时保留更新的 as_of / 价格
            if str(item.get("as_of", "")) >= str(old.get("as_of", "")):
                by[k] = item
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        else:
            by[k] = item
            stats["added"] += 1
    return list(by.values()), stats


def read_inbox_csvs(keep_sample: bool = False) -> list[dict[str, Any]]:
    INBOX.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    rows: list[dict[str, Any]] = []
    for path in sorted(INBOX.glob("*.csv")):
        if path.name.endswith("_template.csv") and not keep_sample:
            # 仍可读，但跳过示例行
            pass
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                raw = { (k or "").strip(): (v or "").strip() for k, v in raw.items() }
                if keep_sample:
                    raw["_keep_sample"] = "1"
                item = _norm_row(raw, today)
                if item:
                    rows.append(item)
    return rows


def catalog_as_of(items: list[dict[str, Any]]) -> str:
    dates = [str(x.get("as_of") or "") for x in items if x.get("as_of")]
    return max(dates) if dates else ""


def refresh(keep_sample: bool = False, dry_run: bool = False) -> dict[str, Any]:
    today = date.today().isoformat()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    base = ensure_as_of(load_main(), today)
    incoming = read_inbox_csvs(keep_sample=keep_sample)
    merged, stats = merge(base, incoming)
    merged = sorted(merged, key=lambda x: (x.get("district") or "", x.get("name") or ""))
    result = {
        "as_of": catalog_as_of(merged),
        "count": len(merged),
        "incoming": len(incoming),
        **stats,
    }
    if dry_run:
        return result
    if MAIN.exists():
        stamp = today.replace("-", "")
        shutil.copy2(MAIN, ARCHIVE / f"shanghai_competitors_{stamp}.json")
    MAIN.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 写元数据
    meta = {
        "as_of": result["as_of"],
        "count": result["count"],
        "refreshed_at": today,
        "note": "由 scripts/refresh_competitors.py 生成",
    }
    (DATA / "competitors_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="刷新上海竞品库")
    parser.add_argument("--keep-sample", action="store_true", help="保留模板中的示例行")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stamp-existing", action="store_true", help="仅给现有库打上今日 as_of")
    args = parser.parse_args()
    if args.stamp_existing:
        today = date.today().isoformat()
        items = ensure_as_of(load_main(), today)
        for x in items:
            if not x.get("as_of"):
                x["as_of"] = today
        MAIN.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        meta = {"as_of": catalog_as_of(items), "count": len(items), "refreshed_at": today}
        (DATA / "competitors_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(meta, ensure_ascii=False))
        return
    print(json.dumps(refresh(keep_sample=args.keep_sample, dry_run=args.dry_run), ensure_ascii=False))


if __name__ == "__main__":
    main()
