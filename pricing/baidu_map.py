"""百度地图检索 + 模糊兜底（始终可用）。"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pathlib import Path

from .simple_models import GeoPoint

BRAND_POI_PATH = Path(__file__).resolve().parent.parent / "data" / "shanghai_brand_pois.json"
_BRAND_POIS: list[dict[str, Any]] | None = None


def load_brand_pois() -> list[dict[str, Any]]:
    global _BRAND_POIS
    if _BRAND_POIS is not None:
        return _BRAND_POIS
    if BRAND_POI_PATH.exists():
        raw = json.loads(BRAND_POI_PATH.read_text(encoding="utf-8"))
        _BRAND_POIS = list(raw) if isinstance(raw, list) else []
    else:
        _BRAND_POIS = []
    return _BRAND_POIS


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
        self,
        query: str,
        city: str = "上海",
        limit: int = 20,
        *,
        district: str = "",
        number: str = "",
        allow_approx: bool = False,
    ) -> tuple[list[dict[str, Any]], str]:
        """精准检索：只返回与关键词强相关的上海地址。

        - 有百度 AK：地理编码（区+路+号）+ Place Search（限指定区或全市）
        - 本地 POI / 模糊：仅强匹配，不生成「分区假地址」
        """
        q = (query or "").strip()
        district = _normalize_district_name(district)
        number = (number or "").strip()
        # 用户把「宜山路455号」整段填在路名里时，拆出门牌，避免本地匹配失败
        if not number:
            q, number = _split_road_and_number(q)
        else:
            q, embedded = _split_road_and_number(q)
            if embedded and not number:
                number = embedded
        if not q and not number:
            return [], "empty"

        # 地理编码用完整地址；本地/模糊只用路名核心（不含门牌）
        road_core = q or _strip_house_number(number)
        place = f"{q}{number}".strip()
        full_address = _compose_shanghai_address(district, q, number)

        buckets: list[dict[str, Any]] = []
        modes: list[str] = []

        if self.ak:
            try:
                # 1) 结构化地理编码：区+路+号 → 单点最准
                if district and (q or number):
                    geo = self._baidu_geocode(full_address)
                    if geo:
                        geo["mode"] = "geocode"
                        buckets.append(geo)
                        modes.append("geocode")

                # 2) Place Search：限定行政区更准
                region = _district_region(district) if district else city
                place_hits = self._baidu_place_search(place or road_core, city=region, limit=limit)
                sug_hits = self._baidu_suggest(
                    place or road_core, city=region if district else city, limit=limit
                )
                raw_baidu = place_hits + sug_hits
                filtered = [
                    h
                    for h in raw_baidu
                    if _is_relevant_hit(h, q=road_core, number=number, district=district)
                ]
                if district:
                    filtered = [
                        h
                        for h in filtered
                        if (h.get("district") or "") == district
                        or district in (h.get("address") or "")
                        or district in (h.get("name") or "")
                    ]
                for item in filtered:
                    item["mode"] = "baidu"
                buckets.extend(filtered)
                if filtered:
                    modes.append("baidu")
            except Exception:
                pass

        local_hits = self._local_poi_suggest(road_core, limit=limit, district=district)
        for item in local_hits:
            item.setdefault("mode", "catalog")
        if local_hits:
            buckets.extend(local_hits)
            modes.append("catalog")

        fuzzy_hits = self._fuzzy_suggest(
            road_core, limit=limit, skip_local=True, district=district
        )
        for item in fuzzy_hits:
            item["mode"] = item.get("mode") or "fuzzy"
        if not allow_approx:
            fuzzy_hits = [
                h
                for h in fuzzy_hits
                if not h.get("approx")
                and not h.get("synthetic")
                and h.get("mode") != "district"
            ]
        if fuzzy_hits:
            buckets.extend(fuzzy_hits)
            modes.append("fuzzy")

        merged = _merge_places(buckets, limit=limit)
        if not allow_approx:
            merged = [
                h
                for h in merged
                if not h.get("approx") and h.get("mode") != "district"
            ]

        if not merged:
            return [], "none"

        mode = "+".join(dict.fromkeys(modes)) if modes else "fuzzy"
        return merged, mode

    def _baidu_geocode(self, address: str) -> dict[str, Any] | None:
        """百度地理编码：完整地址 → 坐标（门牌级）。"""
        if not self.ak or not (address or "").strip():
            return None
        params = urlencode(
            {
                "address": address.strip(),
                "city": "上海市",
                "output": "json",
                "ak": self.ak,
                "ret_coordtype": "bd09ll",
            }
        )
        url = f"https://api.map.baidu.com/geocoding/v3/?{params}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != 0:
            return None
        result = data.get("result") or {}
        loc = result.get("location") or {}
        if "lng" not in loc or "lat" not in loc:
            return None
        conf = float(result.get("confidence") or 0)
        level = str(result.get("level") or "")
        # 置信度过低的编码不要当精位点
        if conf < 50 and level in ("城市", "区县", ""):
            return None
        name = address.strip()
        district = _extract_district(address)
        return {
            "name": name,
            "address": name if name.startswith("上海") else f"上海市{name.lstrip('市')}",
            "district": district,
            "lng": float(loc["lng"]),
            "lat": float(loc["lat"]),
            "uid": "",
            "confidence": conf,
            "level": level,
            "mode": "geocode",
        }

    def _baidu_suggest(
        self, query: str, city: str = "上海", limit: int = 20
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

    def _baidu_place_search(
        self, query: str, city: str = "上海", limit: int = 20
    ) -> list[dict[str, Any]]:
        """百度 Place Search：指定区域内的多点结果。"""
        results: list[dict[str, Any]] = []
        page_size = min(20, max(10, limit))
        pages = max(1, (limit + page_size - 1) // page_size)
        for page_num in range(min(pages, 2)):
            params = urlencode(
                {
                    "query": query,
                    "region": city,
                    "city_limit": "true",
                    "output": "json",
                    "ak": self.ak,
                    "page_size": page_size,
                    "page_num": page_num,
                    "scope": 2,
                }
            )
            url = f"https://api.map.baidu.com/place/v2/search?{params}"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != 0:
                if page_num == 0:
                    raise BaiduMapError(
                        f"百度检索 status={data.get('status')} {data.get('message')}"
                    )
                break
            batch = data.get("results") or []
            if not batch:
                break
            for item in batch:
                loc = item.get("location") or {}
                if "lng" not in loc or "lat" not in loc:
                    continue
                addr = item.get("address") or ""
                name = item.get("name") or ""
                area = item.get("area") or ""
                results.append(
                    {
                        "name": name,
                        "address": addr or f"上海市{area}{name}",
                        "district": _extract_district(f"{addr}{area}{name}"),
                        "lng": float(loc["lng"]),
                        "lat": float(loc["lat"]),
                        "uid": item.get("uid", ""),
                    }
                )
                if len(results) >= limit:
                    return results
            total = int(data.get("total") or 0)
            if (page_num + 1) * page_size >= total:
                break
        return results

    def _baidu_place_search_by_districts(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """仅在已显式需要全市铺开且有 AK 时使用；默认检索不再调用。"""
        from .shanghai_market import DISTRICT_NAMES

        q = (query or "").strip()
        if len(q) < 2 or not self.ak:
            return []
        q_district = _extract_district(q)
        districts = [q_district] if q_district else list(DISTRICT_NAMES)
        per = max(2, limit // max(1, min(len(districts), 8)))
        out: list[dict[str, Any]] = []
        for d in districts[:12]:
            region = _district_region(d)
            try:
                _, rest = _split_district_prefix(_normalize_query(q))
                q_use = rest.strip() or q
                hits = self._baidu_place_search(q_use, city=region, limit=per)
            except Exception:
                continue
            for h in hits:
                if not h.get("district"):
                    h["district"] = d
                if _is_relevant_hit(h, q=q_use, number="", district=d):
                    out.append(h)
            if len(out) >= limit:
                break
        return out[:limit]

    def _local_poi_suggest(
        self, query: str, limit: int = 20, district: str = ""
    ) -> list[dict[str, Any]]:
        """本地上海 POI 库：强子串命中（路名不含门牌）。"""
        q_raw = _strip_house_number((query or "").strip())
        if len(q_raw) < 2:
            return []
        q = _normalize_query(q_raw)
        q_district = (district or _extract_district(q_raw) or "").strip()
        q_district = _normalize_district_name(q_district)
        _, place_part = _split_district_prefix(q)
        keys = [k for k in (q_raw, q, place_part) if k and len(k) >= 2]
        keys = [k for k in keys if k not in ("上海", q_district, f"{q_district}区")]
        if not keys:
            return []
        out: list[dict[str, Any]] = []
        for p in load_brand_pois():
            name = str(p.get("name") or "")
            addr = str(p.get("address") or "")
            brand = str(p.get("brand") or "")
            dist = str(p.get("district") or _extract_district(f"{name}{addr}"))
            dist = _normalize_district_name(dist)
            blob = f"{name}{addr}{brand}"
            if not any(k in blob for k in keys):
                continue
            if q_district and dist and q_district != dist:
                continue
            out.append(
                {
                    "name": name,
                    "address": addr,
                    "district": dist,
                    "lng": float(p["lng"]),
                    "lat": float(p["lat"]),
                    "mode": "catalog",
                    "brand": brand,
                }
            )
            if len(out) >= limit:
                break
        out.sort(key=lambda x: (x.get("district") or "", x.get("name") or ""))
        return out

    def _brand_poi_suggest(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._local_poi_suggest(query, limit=limit)

    def _place_pool(self) -> list[dict[str, Any]]:
        from .competitors import OFFLINE_PLACES, load_competitors

        if not OFFLINE_PLACES:
            load_competitors()
        pool = list(DISTRICT_CENTERS)
        for p in load_brand_pois():
            pool.append(
                {
                    "name": p["name"],
                    "address": p.get("address", ""),
                    "district": p.get("district", ""),
                    "lng": p["lng"],
                    "lat": p["lat"],
                }
            )
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

    def _fuzzy_suggest(
        self,
        query: str,
        limit: int = 20,
        skip_local: bool = False,
        district: str = "",
    ) -> list[dict[str, Any]]:
        """本地库/地标匹配；已选行政区时用路名子串宽松命中。"""
        q_raw = _strip_house_number((query or "").strip())
        if not q_raw:
            return []

        q_district = _normalize_district_name(district or _extract_district(q_raw) or "")

        local_hits: list[dict[str, Any]] = []
        if not skip_local:
            local_hits = self._local_poi_suggest(q_raw, limit=limit, district=q_district)
            if len(local_hits) >= 2:
                return local_hits

        pool = self._place_pool()
        q = _normalize_query(q_raw)
        _, place_part = _split_district_prefix(q)
        core = place_part or q
        tokens = _query_tokens(q)

        scored: list[tuple[float, dict[str, Any]]] = []
        for p in pool:
            name = str(p.get("name") or "")
            addr = str(p.get("address") or "")
            dist = _normalize_district_name(
                str(p.get("district") or _extract_district(f"{name}{addr}"))
            )
            if q_district and dist and q_district != dist and q_district not in name:
                continue

            # 已选区：路名子串直接命中（解决「宜山路」对「宜山路商圈」）
            blob = f"{name}{addr}"
            if q_district and core and len(core) >= 2 and (core in blob or any(t in blob for t in tokens if len(t) >= 2)):
                score = 120.0 if core in name or core in addr else 80.0
                scored.append(
                    (
                        score,
                        {
                            "name": name,
                            "address": addr,
                            "district": dist,
                            "lng": float(p["lng"]),
                            "lat": float(p["lat"]),
                            "match_score": score,
                        },
                    )
                )
                continue

            hit, score = _strong_match_score(
                q=q,
                q_raw=q_raw,
                tokens=tokens,
                q_district=q_district,
                name=name,
                address=addr,
                district=dist,
            )
            if not hit:
                continue
            scored.append(
                (
                    score,
                    {
                        "name": name,
                        "address": addr,
                        "district": dist,
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
            key = f"{h['name']}|{round(h['lng'],4)}|{round(h['lat'],4)}"
            if key in seen:
                continue
            seen.add(key)
            out.append(h)
            if len(out) >= limit:
                break

        if local_hits:
            out = _merge_places(local_hits + out, limit=limit)
        return out


def _normalize_district_name(district: str) -> str:
    d = (district or "").strip()
    if not d:
        return ""
    d = d.replace("上海市", "").replace("上海", "")
    d = d.replace("新区", "").replace("区", "").strip()
    if d.startswith("浦东"):
        return "浦东"
    return d


def _strip_house_number(text: str) -> str:
    """去掉末尾门牌，保留路名/小区名。"""
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(
        r"(\d+[-–]?\d*)\s*(号|弄|支弄|幢|栋|号楼|室|层)?\s*$",
        "",
        s,
    ).strip(" ,，、/-")
    return s or text.strip()


def _split_road_and_number(text: str) -> tuple[str, str]:
    """从『宜山路455号』拆出 (宜山路, 455号)。"""
    s = (text or "").strip()
    if not s:
        return "", ""
    m = re.search(
        r"^(.*?)(\d+[-–]?\d*\s*(?:号|弄|支弄|幢|栋|号楼)?)\s*$",
        s,
    )
    if not m:
        return s, ""
    road = (m.group(1) or "").strip(" ,，、/-")
    num = (m.group(2) or "").strip()
    if not road or len(road) < 2:
        return s, ""
    if not num.endswith(("号", "弄", "幢", "栋")) and re.fullmatch(r"\d+[-–]?\d*", num):
        num = f"{num}号"
    return road, num


def _district_region(district: str) -> str:
    d = (district or "").strip().replace("区", "")
    if d.startswith("浦东"):
        return "浦东新区"
    return f"{d}区" if d else "上海"


def _compose_shanghai_address(district: str, road: str, number: str = "") -> str:
    d = (district or "").strip().replace("区", "")
    road = (road or "").strip()
    number = (number or "").strip()
    body = f"{road}{number}"
    if not d:
        return f"上海市{body}" if body else "上海市"
    if d == "浦东" or d.startswith("浦东"):
        return f"上海市浦东新区{body}"
    return f"上海市{d}区{body}"


def _is_relevant_hit(
    hit: dict[str, Any],
    *,
    q: str,
    number: str = "",
    district: str = "",
) -> bool:
    """过滤与输入无关的百度噪声结果。"""
    name = str(hit.get("name") or "")
    addr = str(hit.get("address") or "")
    blob = f"{name}{addr}"
    qn = _normalize_query(q or "")
    _, place = _split_district_prefix(qn)
    keys = [k for k in (q, qn, place) if k and len(k) >= 2]
    if number and number not in blob and number.rstrip("号") not in blob:
        # 有门牌时优先要求门牌出现；不强制卡死（有的 POI 无门牌）
        pass
    if not keys:
        return bool(district)
    # 至少一个核心词出现在名称或地址
    if not any(k in blob for k in keys):
        return False
    if district:
        d = hit.get("district") or _extract_district(blob)
        if d and d != district and district not in blob:
            return False
    return True


def _merge_places(items: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """按坐标/名称去重；地理编码结果优先。"""
    # geocode 优先
    ordered = sorted(
        items,
        key=lambda x: (
            0 if x.get("mode") == "geocode" else 1,
            0 if x.get("mode") == "baidu" else 1,
            x.get("district") or "zzz",
            x.get("name") or "",
        ),
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in ordered:
        name = str(h.get("name") or "")
        lng = float(h.get("lng") or 0)
        lat = float(h.get("lat") or 0)
        key = h.get("uid") or f"{name}|{round(lng, 4)}|{round(lat, 4)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= limit:
            break
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
