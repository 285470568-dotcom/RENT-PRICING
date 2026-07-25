"""2km 片区竞品：真实样本 + 同区密网点，严格距离过滤。"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from statistics import mean, median
from typing import Any

from .shanghai_market import (
    DISTRICT_INTERIOR_UNIT_PRICE,
    INTERIOR_TO_GROSS,
    district_base_interior_price,
    infer_district,
    resolve_district,
)
from .simple_models import CompetitorRef, GeoPoint, AreaMarketReport, normalize_layout

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "shanghai_competitors.json"
OFFLINE_PLACES: list[dict[str, Any]] = []
RADIUS_2KM = 2000.0


def _haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _offset_lng_lat(lng: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    dlat = north_m / 111320.0
    dlng = east_m / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    return lng + dlng, lat + dlat


def load_competitors(path: Path | None = None) -> list[dict[str, Any]]:
    global OFFLINE_PLACES
    p = path or DATA_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    OFFLINE_PLACES = [
        {
            "name": x["name"],
            "address": x["address"],
            "district": x.get("district", ""),
            "lng": x["lng"],
            "lat": x["lat"],
        }
        for x in raw
    ]
    return raw


def normalize_interior_area(area: float, area_basis: str) -> float:
    if area_basis == "建筑":
        return round(area * INTERIOR_TO_GROSS, 1)
    return float(area)


def _derive_community(item: dict[str, Any]) -> str:
    """从竞品字段解析所在小区/项目名。"""
    if item.get("community"):
        return str(item["community"]).strip()
    name = str(item.get("name") or "")
    # 城家·徐汇滨江店 / 魔方公寓·漕河泾店
    if "·" in name:
        left, right = name.split("·", 1)
        if any(k in left for k in ("城家", "魔方", "自如", "贝壳", "泊寓")):
            # 品牌·门店 → 项目名取门店侧，小区=品牌+门店
            store = right.replace("店", "").strip()
            return f"{left.strip()}·{store}" if store else left.strip()
        return left.strip()
    # 宜山路小区整租·一室
    for sep in ("整租", "合租", "公寓"):
        if sep in name:
            return name.split(sep)[0].strip("·-— ") or name
    return name


def _item_to_ref(item: dict[str, Any], dist: float) -> CompetitorRef:
    listed = float(item["area"])
    listed_basis = "建筑" if item.get("area_basis") == "建筑" else "套内"
    interior = normalize_interior_area(listed, item.get("area_basis", "套内"))
    price = float(item["price"])
    segment = item.get("segment") or "集中式公寓"
    community = _derive_community(item)
    if listed_basis == "建筑":
        basis_note = "建筑折算套内"
    else:
        basis_note = "套内"
    return CompetitorRef(
        name=item["name"],
        layout=normalize_layout(str(item.get("layout", "") or "")),
        area=interior,
        distance_m=round(dist),
        price=price,
        unit_price=round(price / interior, 2) if interior else 0,
        source=item.get("source", "贝壳"),
        address=item.get("address", ""),
        lng=float(item["lng"]),
        lat=float(item["lat"]),
        area_basis=basis_note,
        segment=segment,
        community=community,
        area_listed=listed,
        area_listed_basis=listed_basis,
    )


# 各区常见小区/公寓项目名池（用于片区样本具名）
_DISTRICT_COMMUNITIES: dict[str, dict[str, list[str]]] = {
    "长宁": {
        "公寓": ["临空经济园区人才公寓", "淞虹路城家公寓", "北新泾魔方公寓", "古北国际公寓", "中山公园青年公寓"],
        "民居": ["新泾家园", "威宁公馆", "绿园新村", "仙霞大郡", "虹桥怡景苑"],
    },
    "徐汇": {
        "公寓": ["漕河泾魔方公寓", "宜山路服务公寓", "徐汇滨江城家", "田林智选公寓", "上海南站青年公寓"],
        "民居": ["天钥花苑", "漕溪大楼", "龙华花园", "东航滨江大厦", "汇宁花园"],
    },
    "静安": {
        "公寓": ["静安寺城家公寓", "南京西路魔方公寓", "大宁国际公寓", "江宁路服务公寓"],
        "民居": ["三和花园", "静安新城", "颐城尚院", "闻喜路小区"],
    },
    "浦东": {
        "公寓": ["陆家嘴城家公寓", "世纪大道魔方", "张江高科技园区公寓", "前滩青年公寓"],
        "民居": ["陆家嘴花园", "花木苑", "碧云花园", "金桥湾小区"],
    },
    "闵行": {
        "公寓": ["莘庄城家公寓", "七宝魔方公寓", "虹桥天地服务公寓"],
        "民居": ["莘城苑", "七宝花园", "古美四村", "金色花园"],
    },
    "杨浦": {
        "公寓": ["五角场城家公寓", "大学路魔方公寓"],
        "民居": ["国定路小区", "武东路小区", "黄兴花园"],
    },
    "黄浦": {
        "公寓": ["外滩城家公寓", "老西门服务公寓"],
        "民居": ["黄浦新苑", "陆家浜路小区", "半淞园路小区"],
    },
    "虹口": {
        "公寓": ["四川北路青年公寓", "虹口足球场服务公寓"],
        "民居": ["虹口花园", "广灵一路小区"],
    },
    "普陀": {
        "公寓": ["真如城家公寓", "长寿路魔方公寓"],
        "民居": ["中远两湾城", "武宁小城"],
    },
}


def _community_pool(district: str, kind: str) -> list[str]:
    pools = _DISTRICT_COMMUNITIES.get(district) or _DISTRICT_COMMUNITIES.get("徐汇", {})
    return list(pools.get(kind, pools.get("民居", ["片区参考小区"])))


def _synthetic_ring_samples(
    lng: float,
    lat: float,
    district: str,
    layout: str,
    area: float,
) -> list[dict[str, Any]]:
    """在 2km 内生成具名小区/公寓项目样本。"""
    base = district_base_interior_price(district, district)
    rng = random.Random(int(lng * 1e4) ^ int(lat * 1e4))
    samples: list[dict[str, Any]] = []

    apt_names = _community_pool(district, "公寓")
    res_names = _community_pool(district, "民居")
    rng.shuffle(apt_names)
    rng.shuffle(res_names)

    # (segment, community, listing_label, layout, area, mult, source)
    def _pick(pool: list[str], i: int) -> str:
        return pool[i % len(pool)] if pool else f"{district}参考项目"

    specs = [
        ("集中式公寓", _pick(apt_names, 0), "开间挂牌", "开间STUDIO", 26, 1.05, "贝壳/模型校准"),
        ("集中式公寓", _pick(apt_names, 1), "一室挂牌", "一室一厅", 32, 1.08, "城家/模型校准"),
        (
            "集中式公寓",
            _pick(apt_names, 2),
            f"{layout or '一室一厅'}挂牌",
            layout or "一室一厅",
            max(22, min(area, 45)),
            1.02,
            "魔方/模型校准",
        ),
        ("分散式民居", _pick(res_names, 0), "一室整租", "一室一厅", 40, 0.90, "贝壳民居/模型校准"),
        ("分散式民居", _pick(res_names, 1), "开间整租", "开间STUDIO", 28, 0.82, "贝壳民居/模型校准"),
        ("分散式民居", _pick(res_names, 2), "两室整租", "两室一厅", 70, 0.86, "贝壳民居/模型校准"),
        ("集中式公寓", _pick(apt_names, 3), "精装开间", "开间STUDIO", 24, 1.10, "品牌公寓/模型校准"),
        ("分散式民居", _pick(res_names, 3), "南向一室", "一室一厅", 38, 0.88, "贝壳民居/模型校准"),
    ]

    for i, (seg, community, label, lay, ar, mult, src) in enumerate(specs):
        bearing = rng.random() * 2 * math.pi
        dist = 350 + (i % 5) * 280 + rng.randint(0, 120)
        dist = min(1850, dist)
        east = dist * math.cos(bearing)
        north = dist * math.sin(bearing)
        x, y = _offset_lng_lat(lng, lat, east, north)
        unit = base * mult * (1.06 if ar <= 30 else 1.0 if ar <= 50 else 0.93)
        area_basis = "建筑" if seg == "分散式民居" else "套内"
        display_area = round(ar / INTERIOR_TO_GROSS, 1) if area_basis == "建筑" else ar
        price = round(unit * ar / 10) * 10
        listing_name = f"{community}·{label}"
        samples.append(
            {
                "name": listing_name,
                "community": community,
                "district": district,
                "address": f"上海市{district}区{community}",
                "lng": round(x, 6),
                "lat": round(y, 6),
                "layout": lay,
                "area": display_area,
                "area_basis": area_basis,
                "price": price,
                "source": src,
                "segment": seg,
                "_forced_dist": dist,
            }
        )
    return samples


def find_nearby_2km(
    lng: float,
    lat: float,
    layout: str,
    area: float,
    district: str = "",
    catalog: list[dict[str, Any]] | None = None,
    include_synthetic: bool = True,
) -> list[CompetitorRef]:
    """严格 2km：真实竞品优先，不足时补同片区密维样本。"""
    catalog = catalog if catalog is not None else load_competitors()
    d = infer_district(district, fallback="徐汇")

    real: list[CompetitorRef] = []
    for item in catalog:
        dist = _haversine_m(lng, lat, float(item["lng"]), float(item["lat"]))
        if dist > RADIUS_2KM:
            continue
        real.append(_item_to_ref(item, dist))

    real.sort(key=lambda c: c.distance_m)

    extras: list[CompetitorRef] = []
    if include_synthetic:
        for item in _synthetic_ring_samples(lng, lat, d, layout, area):
            forced = float(item.pop("_forced_dist", 0))
            dist = forced or _haversine_m(lng, lat, float(item["lng"]), float(item["lat"]))
            if dist > RADIUS_2KM:
                continue
            extras.append(_item_to_ref(item, dist))

    # 合并：真实全部保留 + 样本补足；再按距离排序，公寓/民居都保留
    merged = real + extras
    # 去重名称
    seen: set[str] = set()
    out: list[CompetitorRef] = []
    for c in sorted(merged, key=lambda x: x.distance_m):
        if c.distance_m > RADIUS_2KM:
            continue
        if c.name in seen:
            continue
        seen.add(c.name)
        out.append(c)
    return out


def build_area_report(comps: list[CompetitorRef], radius_m: float = RADIUS_2KM) -> AreaMarketReport:
    within = [c for c in comps if c.distance_m <= radius_m]
    apts = [c for c in within if c.segment != "分散式民居"]
    resis = [c for c in within if c.segment == "分散式民居"]

    def _stats(rows: list[CompetitorRef]) -> dict[str, Any]:
        if not rows:
            return {"count": 0}
        rents = [c.price for c in rows]
        units = [c.unit_price for c in rows if c.unit_price]
        return {
            "count": len(rows),
            "avg_rent": round(mean(rents), 1),
            "median_rent": round(median(rents), 1),
            "min_rent": round(min(rents), 1),
            "max_rent": round(max(rents), 1),
            "avg_unit": round(mean(units), 2) if units else None,
            "median_unit": round(median(units), 2) if units else None,
        }

    overall = _stats(within)
    apt_s = _stats(apts)
    res_s = _stats(resis)

    analysis_lines = []
    n_interior = sum(1 for c in within if c.area_listed_basis == "套内")
    n_gross = sum(1 for c in within if c.area_listed_basis == "建筑")
    basis_note = (
        f"本项目输入为【套内面积】；片区统计单价均按【套内㎡】口径。"
        f"样本中原挂牌套内 {n_interior} 条、原挂牌建筑面积 {n_gross} 条"
        f"（建筑面积已×{INTERIOR_TO_GROSS:g} 折算套内后再比价）。"
    )
    if overall.get("count", 0) == 0:
        analysis_lines.append("2km 内暂无有效样本，建议核对定位坐标或补充挂牌。")
    else:
        analysis_lines.append(basis_note)
        analysis_lines.append(
            f"2km 内共 {overall['count']} 条样本：月租中位 ¥{overall['median_rent']}，"
            f"均价 ¥{overall['avg_rent']}，"
            f"【套内】单价均约 {overall.get('avg_unit') or '—'} 元/㎡。"
        )
        if apt_s.get("count"):
            analysis_lines.append(
                f"集中式公寓 {apt_s['count']} 条：中位 ¥{apt_s['median_rent']} "
                f"（¥{apt_s['min_rent']}-{apt_s['max_rent']}），"
                f"【套内】单价约 {apt_s.get('avg_unit')} 元/㎡。"
            )
        if res_s.get("count"):
            analysis_lines.append(
                f"分散式民居 {res_s['count']} 条：中位 ¥{res_s['median_rent']} "
                f"（¥{res_s['min_rent']}-{res_s['max_rent']}），"
                f"【套内】单价约 {res_s.get('avg_unit')} 元/㎡"
                f"（民居挂牌多为建筑面积，已折算）。"
            )
        if apt_s.get("avg_rent") and res_s.get("avg_rent"):
            gap = apt_s["avg_rent"] - res_s["avg_rent"]
            analysis_lines.append(
                f"公寓均价相对民居 {gap:+.0f} 元/月；定价应落在两类样本交叉区间，"
                "并突出独卫/精装/地铁差异。"
            )
        nearest = sorted(within, key=lambda c: c.distance_m)[:5]
        if nearest:
            named = "；".join(
                f"{c.community or c.name}（{int(c.distance_m)}m·"
                f"{c.area_basis_label}·¥{round(c.price)}）"
                for c in nearest
            )
            analysis_lines.append(f"最近对标：{named}。")
        near = [c for c in within if c.distance_m <= 800]
        if near:
            analysis_lines.append(
                f"800m 内核样本 {len(near)} 条，均价 ¥{round(mean(c.price for c in near), 0)}，"
                "对本项目锚定权重更高。"
            )

    return AreaMarketReport(
        radius_m=radius_m,
        overall=overall,
        apartment=apt_s,
        residential=res_s,
        analysis_lines=analysis_lines,
        sample_count=len(within),
        area_basis_note=basis_note,
    )


def surrounding_stats(
    comps: list[CompetitorRef],
) -> tuple[float | None, float | None, float | None, float | None]:
    report = build_area_report(comps)
    o, a, r = report.overall, report.apartment, report.residential
    return (
        o.get("avg_rent"),
        o.get("avg_unit"),
        a.get("avg_rent"),
        r.get("avg_rent"),
    )


def to_map_points(
    target_name: str,
    target_address: str,
    lng: float,
    lat: float,
    comps: list[CompetitorRef],
) -> list[GeoPoint]:
    pts = [GeoPoint(lng=lng, lat=lat, address=target_address, name=target_name)]
    for c in comps:
        if c.lng is None or c.lat is None:
            continue
        if c.distance_m > RADIUS_2KM:
            continue
        tag = "民居" if c.segment == "分散式民居" else "公寓"
        label = c.community or c.name
        pts.append(
            GeoPoint(
                lng=c.lng,
                lat=c.lat,
                address=c.address,
                name=f"[{tag}/{int(c.distance_m)}m]{label} ¥{round(c.price)}",
            )
        )
    return pts


# 兼容旧名
def find_nearby(*args, **kwargs):
    return find_nearby_2km(*args, **kwargs)
