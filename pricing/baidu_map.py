"""百度地图检索 + 模糊兜底（始终可用）。"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .simple_models import GeoPoint

# 各区中心点 + 常用路段/地标，保证无 AK 时也能模糊命中
DISTRICT_CENTERS: list[dict[str, Any]] = [
    {"name": "黄浦区中心", "district": "黄浦", "address": "上海市黄浦区人民广场", "lng": 121.4755, "lat": 31.2304},
    {"name": "静安区中心", "district": "静安", "address": "上海市静安区静安寺", "lng": 121.4455, "lat": 31.2235},
    {"name": "徐汇区中心", "district": "徐汇", "address": "上海市徐汇区徐家汇", "lng": 121.4365, "lat": 31.1883},
    {"name": "长宁区中心", "district": "长宁", "address": "上海市长宁区中山公园", "lng": 121.4186, "lat": 31.2189},
    {"name": "长宁区北新泾", "district": "长宁", "address": "上海市长宁区北新泾", "lng": 121.3738, "lat": 31.2215},
    {"name": "淞虹路商圈", "district": "长宁", "address": "上海市长宁区淞虹路", "lng": 121.3595, "lat": 31.2188},
    {"name": "虹口区中心", "district": "虹口", "address": "上海市虹口区四川北路", "lng": 121.4850, "lat": 31.2646},
    {"name": "杨浦区中心", "district": "杨浦", "address": "上海市杨浦区五角场", "lng": 121.5142, "lat": 31.2985},
    {"name": "普陀区中心", "district": "普陀", "address": "上海市普陀区真如", "lng": 121.3955, "lat": 31.2493},
    {"name": "浦东新区陆家嘴", "district": "浦东", "address": "上海市浦东新区陆家嘴", "lng": 121.5055, "lat": 31.2397},
    {"name": "浦东新区张江", "district": "浦东", "address": "上海市浦东新区张江高科技园区", "lng": 121.6012, "lat": 31.2035},
    {"name": "浦东新区世纪公园", "district": "浦东", "address": "上海市浦东新区世纪公园", "lng": 121.5488, "lat": 31.2186},
    {"name": "闵行区莘庄", "district": "闵行", "address": "上海市闵行区莘庄", "lng": 121.3815, "lat": 31.1124},
    {"name": "闵行区七宝", "district": "闵行", "address": "上海市闵行区七宝", "lng": 121.3502, "lat": 31.1528},
    {"name": "宝山区中心", "district": "宝山", "address": "上海市宝山区牡丹江路", "lng": 121.4891, "lat": 31.4050},
    {"name": "嘉定区中心", "district": "嘉定", "address": "上海市嘉定区嘉定新城", "lng": 121.2500, "lat": 31.3400},
    {"name": "松江区中心", "district": "松江", "address": "上海市松江区松江大学城", "lng": 121.2335, "lat": 31.0458},
    {"name": "青浦区中心", "district": "青浦", "address": "上海市青浦区青浦新城", "lng": 121.1240, "lat": 31.1510},
    {"name": "奉贤区中心", "district": "奉贤", "address": "上海市奉贤区南桥", "lng": 121.4740, "lat": 30.9180},
    {"name": "金山区中心", "district": "金山", "address": "上海市金山区石化", "lng": 121.3420, "lat": 30.7240},
    {"name": "崇明区中心", "district": "崇明", "address": "上海市崇明区城桥", "lng": 121.3970, "lat": 31.6230},
    {"name": "宜山路商圈", "district": "徐汇", "address": "上海市徐汇区宜山路", "lng": 121.4288, "lat": 31.1824},
    {"name": "漕河泾开发区", "district": "徐汇", "address": "上海市徐汇区漕河泾新兴技术开发区", "lng": 121.4040, "lat": 31.1690},
    {"name": "徐汇滨江", "district": "徐汇", "address": "上海市徐汇区龙腾大道", "lng": 121.4638, "lat": 31.1689},
    {"name": "南京西路商圈", "district": "静安", "address": "上海市静安区南京西路", "lng": 121.4506, "lat": 31.2238},
    {"name": "前滩", "district": "浦东", "address": "上海市浦东新区前滩", "lng": 121.4825, "lat": 31.1568},
    {"name": "虹桥商务区", "district": "闵行", "address": "上海市闵行区虹桥商务区", "lng": 121.3188, "lat": 31.1975},
]


class BaiduMapError(Exception):
    pass


def get_ak() -> str:
    return (
        os.environ.get("BAIDU_MAP_AK", "")
        or os.environ.get("BAIDU_AK", "")
        or _secrets_ak()
    )


def _secrets_ak() -> str:
    try:
        import streamlit as st

        return str(st.secrets.get("BAIDU_MAP_AK", "") or "")
    except Exception:
        return ""


def _extract_district(text: str) -> str:
    from .shanghai_market import resolve_district

    return resolve_district(text or "") or ""


class BaiduMapClient:
    """双模式：百度 API 优先，失败/无结果自动模糊兜底。"""

    def __init__(self, ak: str | None = None):
        self.ak = (ak if ak is not None else get_ak()) or ""

    def suggest(
        self, query: str, city: str = "上海", limit: int = 10
    ) -> tuple[list[dict[str, Any]], str]:
        """返回 (结果列表, 模式说明)。模式：baidu / fuzzy / baidu+fuzzy。"""
        q = (query or "").strip()
        if not q:
            fuzzy = self._fuzzy_suggest("", limit=limit)
            for item in fuzzy:
                item["mode"] = "fuzzy"
            return fuzzy, "fuzzy"

        baidu_hits: list[dict[str, Any]] = []
        mode = "fuzzy"
        if self.ak:
            try:
                baidu_hits = self._baidu_suggest(q, city=city, limit=limit)
                for item in baidu_hits:
                    item["mode"] = "baidu"
                mode = "baidu"
            except Exception:
                baidu_hits = []
                mode = "fuzzy"

        if baidu_hits:
            return baidu_hits[:limit], mode

        fuzzy = self._fuzzy_suggest(q, limit=limit)
        for item in fuzzy:
            item["mode"] = "fuzzy"
        return fuzzy, "fuzzy"

    def _baidu_suggest(
        self, query: str, city: str = "上海", limit: int = 10
    ) -> list[dict[str, Any]]:
        params = urlencode(
            {
                "query": query,
                "region": city,
                "city_limit": "true",
                "output": "json",
                "ak": self.ak,
            }
        )
        url = f"https://api.map.baidu.com/place/v2/suggestion?{params}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("status") != 0:
            raise BaiduMapError(
                f"百度地图 status={data.get('status')} {data.get('message')}"
            )

        results = []
        for item in data.get("result") or []:
            loc = item.get("location") or {}
            if "lng" not in loc or "lat" not in loc:
                continue
            addr = item.get("address") or ""
            name = item.get("name") or ""
            results.append(
                {
                    "name": name,
                    "address": addr or f"上海市{name}",
                    "district": _extract_district(f"{addr}{name}"),
                    "lng": float(loc["lng"]),
                    "lat": float(loc["lat"]),
                    "uid": item.get("uid", ""),
                }
            )
            if len(results) >= limit:
                break
        return results

    def _place_pool(self) -> list[dict[str, Any]]:
        from .competitors import OFFLINE_PLACES, load_competitors

        if not OFFLINE_PLACES:
            load_competitors()
        pool = list(DISTRICT_CENTERS)
        for p in OFFLINE_PLACES:
            pool.append(
                {
                    "name": p["name"],
                    "address": p.get("address", ""),
                    "district": p.get("district", ""),
                    "lng": p["lng"],
                    "lat": p["lat"],
                }
            )
        return pool

    def _fuzzy_suggest(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """与使用者输入强匹配：核心名称须命中候选；禁止无关区中心灌榜。"""
        pool = self._place_pool()
        q_raw = (query or "").strip()
        if not q_raw:
            return []

        q = _normalize_query(q_raw)
        q_district = _extract_district(q_raw)
        tokens = _query_tokens(q)

        scored: list[tuple[float, dict[str, Any]]] = []
        for p in pool:
            name = str(p.get("name") or "")
            addr = str(p.get("address") or "")
            district = str(p.get("district") or _extract_district(f"{name}{addr}"))
            hit, score = _strong_match_score(
                q=q,
                q_raw=q_raw,
                tokens=tokens,
                q_district=q_district,
                name=name,
                address=addr,
                district=district,
            )
            if not hit:
                continue
            if q_district and district and q_district != district and q_district not in name:
                continue
            scored.append(
                (
                    score,
                    {
                        "name": name,
                        "address": addr,
                        "district": district,
                        "lng": float(p["lng"]),
                        "lat": float(p["lat"]),
                        "match_score": score,
                    },
                )
            )

        scored.sort(key=lambda x: -x[0])
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _, h in scored:
            if h["name"] in seen:
                continue
            seen.add(h["name"])
            out.append(h)
            if len(out) >= limit:
                break

        # 库内无强匹配：仅返回一条「以用户输入为名」的近似点
        if not out:
            synth = _synthetic_place(q_raw, q, q_district)
            if synth:
                out = [synth]
        return out


def _normalize_query(q: str) -> str:
    q = q.strip()
    for prefix in ("上海市", "上海", "市"):
        if q.startswith(prefix):
            q = q[len(prefix) :]
    return q.strip()


def _split_district_prefix(q: str) -> tuple[str, str]:
    """从连写中拆出区名与剩余地名。

    仅在「区/新区」后缀，或剥离后剩余地名仍≥2字时才拆分。
    避免「静安寺」被拆成「静安」+「寺」。
    """
    d = _extract_district(q)
    if not d:
        return "", q

    for form in (f"{d}新区", f"{d}区"):
        if q.startswith(form):
            rest = q[len(form) :].lstrip("·•-—_ ")
            return d, (rest if len(rest) >= 2 else q)
        idx = q.find(form)
        if 0 <= idx <= 2:
            rest = (q[:idx] + q[idx + len(form) :]).strip("·•-—_ ")
            if len(rest) >= 2:
                return d, rest

    # 无「区」字时：仅当剩余段≥2字才剥离区名（徐汇宜山路）
    if q.startswith(d):
        rest = q[len(d) :].lstrip("·•-—_ ")
        if len(rest) >= 2:
            return d, rest
    return d, q


def _query_tokens(q: str) -> list[str]:
    district, rest = _split_district_prefix(q)
    parts = [t for t in re.split(r"[\s,，、/|\-_+]+", rest) if t]
    if rest and rest not in parts:
        parts.insert(0, rest)
    tokens: list[str] = []
    for p in parts:
        if len(p) >= 2:
            tokens.append(p)
    if district:
        tokens.append(district)
    # 原始全串也保留，便于整串命中
    if q and q not in tokens and len(q) >= 2:
        tokens.append(q)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out or ([q] if len(q) >= 2 else [])


def _strong_match_score(
    *,
    q: str,
    q_raw: str,
    tokens: list[str],
    q_district: str,
    name: str,
    address: str,
    district: str,
) -> tuple[bool, float]:
    blob_name = name
    blob_addr = address
    blob = f"{name}{address}"
    score = 0.0

    _, place_part = _split_district_prefix(q)
    place_part = place_part.strip() or q

    whole = False
    for key in filter(None, (q, q_raw, place_part)):
        if key in blob_name or key in blob_addr or key in blob:
            score += 200
            whole = True
            break
    if name and len(name) >= 2 and name in q_raw:
        score += 180
        whole = True

    # 核心地名 token：去掉区名后必须命中名称/地址
    name_tokens = []
    for t in tokens:
        if t in ("上海", "市", q_district):
            continue
        if q_district and t in (f"{q_district}区", f"{q_district}新区"):
            continue
        # 全串过长且含区名前缀时，用拆出的 place_part 代替
        if place_part and t == q and place_part != q:
            continue
        name_tokens.append(t)
    if place_part and place_part not in name_tokens and len(place_part) >= 2:
        if place_part != q_district and place_part not in (f"{q_district}区", f"{q_district}新区"):
            name_tokens.insert(0, place_part)

    # 仅区名：只匹配该区中心/以区名命名的地标，不灌入全区竞品
    if not name_tokens and q_district:
        if district == q_district and ("中心" in blob_name or blob_name.startswith(q_district)):
            return True, 80.0
        return False, 0.0

    if name_tokens:
        # 去重
        uniq: list[str] = []
        seen: set[str] = set()
        for t in name_tokens:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        name_tokens = uniq

        matched = 0.0
        for t in name_tokens:
            if t in blob_name or t in blob_addr:
                matched += 1.0
                score += 60 + min(len(t), 6) * 5
            elif len(t) >= 3 and any(
                t[i : i + 3] in blob_name or t[i : i + 3] in blob_addr
                for i in range(len(t) - 2)
            ):
                matched += 0.7
                score += 35
        coverage = matched / len(name_tokens)
        if not whole:
            if coverage < 1.0:
                # 至少有一个核心地名完整出现在「名称」中
                if not any(t in blob_name for t in name_tokens if len(t) >= 2):
                    return False, 0.0
                # 多 token 时要求主地名（最长 token）命中名称
                primary = max(name_tokens, key=len)
                if primary not in blob_name and primary not in blob_addr:
                    return False, 0.0
            else:
                score += 40
    elif not whole:
        return False, 0.0

    if q_district and district == q_district:
        score += 20

    if score < 60:
        return False, 0.0
    return True, score


def _synthetic_place(q_raw: str, q: str, q_district: str) -> dict[str, Any] | None:
    display = q_raw.strip() or q
    if len(display) < 2:
        return None
    from .shanghai_market import PLATE_TO_DISTRICT, infer_district

    district = q_district or infer_district(display, q, fallback="")
    if not district:
        for plate, dist in PLATE_TO_DISTRICT.items():
            if plate in display:
                district = dist
                break

    # 避免「长宁区」+「长宁区北新泾」重复
    if display.startswith("上海"):
        address = display
    elif district and (display.startswith(f"{district}区") or display.startswith(district)):
        address = f"上海市{display}"
    elif district:
        address = f"上海市{district}区{display}"
    else:
        address = f"上海市{display}"

    lng, lat = 121.4737, 31.2304
    best = None
    for p in DISTRICT_CENTERS:
        if display == p["name"] or display in p["name"] or p["name"] in display:
            best = p
            break
    if best is None:
        for p in DISTRICT_CENTERS:
            if district and p.get("district") == district:
                # 板块关键词优先于区中心
                if any(k in display and k in (p["name"] + p["address"]) for k in PLATE_TO_DISTRICT):
                    best = p
                    break
        if best is None and district:
            for p in DISTRICT_CENTERS:
                if p.get("district") == district and "中心" in p["name"]:
                    best = p
                    break
            if best is None:
                for p in DISTRICT_CENTERS:
                    if p.get("district") == district:
                        best = p
                        break
    if best:
        lng, lat = float(best["lng"]), float(best["lat"])

    return {
        "name": display,
        "address": address,
        "district": district,
        "lng": lng,
        "lat": lat,
        "match_score": 50,
        "synthetic": True,
    }


def render_baidu_map_html(
    center: GeoPoint,
    competitors: list[GeoPoint],
    ak: str | None = None,
    height: int = 420,
) -> str:
    ak = ak if ak is not None else get_ak()
    points = [
        {
            "lng": center.lng,
            "lat": center.lat,
            "name": center.name or "目标项目",
            "type": "target",
            "address": center.address,
        }
    ]
    for c in competitors:
        points.append(
            {
                "lng": c.lng,
                "lat": c.lat,
                "name": c.name,
                "type": "comp",
                "address": c.address,
            }
        )

    if not ak:
        return _fallback_map_html(center, competitors, height)

    points_json = json.dumps(points, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html,body,#map{{margin:0;padding:0;width:100%;height:{height}px;}}
</style>
<script src="https://api.map.baidu.com/api?v=1.0&type=webgl&ak={ak}"></script>
</head>
<body>
<div id="map"></div>
<script>
  var pts = {points_json};
  var map = new BMapGL.Map("map");
  var center = new BMapGL.Point(pts[0].lng, pts[0].lat);
  map.centerAndZoom(center, 15);
  map.enableScrollWheelZoom(true);
  pts.forEach(function(p) {{
    var pt = new BMapGL.Point(p.lng, p.lat);
    map.addOverlay(new BMapGL.Marker(pt));
    var color = p.type === "target" ? "#8B4513" : "#2F4F4F";
    var label = new BMapGL.Label((p.type==="target"?"● ":"○ ") + p.name, {{
      position: pt, offset: new BMapGL.Size(12, -24)
    }});
    label.setStyle({{
      color: "#f7f3ec", backgroundColor: color, border: "none",
      padding: "4px 8px", fontSize: "12px",
      fontFamily: "PingFang SC, Songti SC, serif"
    }});
    map.addOverlay(label);
  }});
</script>
</body>
</html>"""


def _fallback_map_html(
    center: GeoPoint, competitors: list[GeoPoint], height: int
) -> str:
    search = quote(center.address or center.name or "上海")
    rows = "".join(
        f"<tr><td>{'目标' if i==0 else '竞品'}</td><td>{p.name}</td>"
        f"<td>{p.address}</td><td>{p.lng:.5f}, {p.lat:.5f}</td></tr>"
        for i, p in enumerate([center, *competitors])
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
body{{margin:0;font-family:"Noto Serif SC","Songti SC",serif;background:#f4f1ea;color:#1c1a16;}}
.wrap{{padding:16px 20px;height:{height}px;box-sizing:border-box;overflow:auto;}}
a{{color:#6b4f2a;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
td,th{{border-bottom:1px solid #ddd4c5;padding:8px 6px;text-align:left;}}
</style></head><body>
<div class="wrap">
  <h3>区位示意（模糊/离线模式）</h3>
  <p><a href="https://map.baidu.com/search/{search}" target="_blank" rel="noopener">在百度地图中打开</a></p>
  <table>
    <tr><th>类型</th><th>名称</th><th>地址</th><th>坐标</th></tr>
    {rows}
  </table>
</div>
</body></html>"""
