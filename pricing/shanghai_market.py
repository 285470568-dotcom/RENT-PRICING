"""上海公寓定价：六大核心因子（全网调研权重）+ 2km 片区对标。"""

from __future__ import annotations

from dataclasses import dataclass


INTERIOR_TO_GROSS = 0.78

# 板块基准单价：套内·独卫·普通精装·无地铁溢价前的锚点（元/㎡·月）
DISTRICT_INTERIOR_UNIT_PRICE: dict[str, float] = {
    "黄浦": 145,
    "静安": 140,
    "徐汇": 138,
    "长宁": 128,
    "虹口": 118,
    "杨浦": 115,
    "普陀": 110,
    "浦东": 112,
    "闵行": 98,
    "宝山": 88,
    "嘉定": 82,
    "松江": 78,
    "青浦": 76,
    "奉贤": 70,
    "金山": 65,
    "崇明": 58,
}

PLATE_ADJUST: dict[str, float] = {
    "陆家嘴": 22,
    "世纪公园": 14,
    "花木": 12,
    "张江": 10,
    "金桥": 6,
    "前滩": 16,
    "世博": 10,
    "临港": -22,
    "川沙": -8,
    "徐家汇": 10,
    "衡复": 12,
    "武康路": 12,
    "静安寺": 12,
    "南京西路": 14,
    "人民广场": 14,
    "外滩": 16,
    "五角场": 6,
    "中山公园": 8,
    "虹桥": 5,
    "古北": 6,
    "北新泾": 2,
    "淞虹路": 2,
    "宜山路": 4,
    "漕河泾": 6,
    "莘庄": -5,
    "七宝": -3,
    "嘉定新城": -6,
    "松江大学城": -8,
    "青浦新城": -6,
}

# 板块/路名 → 行政区（避免只写「北新泾」时落到默认浦东）
PLATE_TO_DISTRICT: dict[str, str] = {
    "北新泾": "长宁",
    "淞虹路": "长宁",
    "古北": "长宁",
    "中山公园": "长宁",
    "虹桥枢纽": "闵行",
    "虹桥商务区": "闵行",
    "宜山路": "徐汇",
    "漕河泾": "徐汇",
    "徐家汇": "徐汇",
    "陆家嘴": "浦东",
    "张江": "浦东",
    "前滩": "浦东",
    "花木": "浦东",
    "世纪公园": "浦东",
    "五角场": "杨浦",
    "莘庄": "闵行",
    "七宝": "闵行",
}

DISTRICT_NAMES: tuple[str, ...] = (
    "黄浦",
    "静安",
    "徐汇",
    "长宁",
    "虹口",
    "杨浦",
    "普陀",
    "闵行",
    "宝山",
    "嘉定",
    "松江",
    "青浦",
    "奉贤",
    "金山",
    "崇明",
    "浦东",  # 放最后
)

DISTRICT_TIER: dict[str, str] = {
    "黄浦": "核心",
    "静安": "核心",
    "徐汇": "核心",
    "长宁": "次核心",
    "虹口": "次核心",
    "杨浦": "次核心",
    "普陀": "次核心",
    "浦东": "分化（核心-外围）",
    "闵行": "近郊主力供应",
    "宝山": "近郊供应高地",
    "嘉定": "外围",
    "松江": "外围",
    "青浦": "外围",
    "奉贤": "远郊",
    "金山": "远郊",
    "崇明": "远郊",
}


@dataclass(frozen=True)
class FactorRule:
    key: str
    name: str
    rank: int
    weight_pct: float  # 调研权重中枢
    criteria: str
    levels: tuple[tuple[str, float, str], ...]  # label, coefficient, tip


# 全网调研 Top6（排名与权重）
SHANGHAI_FACTOR_RULES: tuple[FactorRule, ...] = (
    FactorRule(
        key="metro",
        name="地铁/交通便利性",
        rank=1,
        weight_pct=27.5,
        criteria="定价第一锚点；一线地铁房溢价约30-50%，>800m溢价衰减",
        levels=(
            ("距站<500m", 1.30, "可溢价约30%+"),
            ("500-800m", 1.15, "中等溢价"),
            (">800m / 较弱", 1.00, "无地铁溢价"),
        ),
    ),
    FactorRule(
        key="decoration",
        name="装修标准与配置",
        rank=2,
        weight_pct=22.5,
        criteria="精装拎包/品牌家电/智能门锁是核心差异；精装vs简装常见差幅20-40%",
        levels=(
            ("精装拎包", 1.25, "即住交付"),
            ("简装", 1.10, "相对精装折价"),
            ("毛坯", 1.00, "基线"),
        ),
    ),
    FactorRule(
        key="building_age",
        name="房龄/建筑年代",
        rank=3,
        weight_pct=17.5,
        criteria=">15年折旧明显；电梯房相对楼梯房约+5-8%",
        levels=(
            ("<5年", 1.05, "次新"),
            ("5-15年", 1.00, "主流"),
            (">15年", 0.85, "折旧系数约0.85-0.90"),
        ),
    ),
    FactorRule(
        key="area_layout",
        name="房屋面积与户型",
        rank=4,
        weight_pct=12.5,
        criteria="单价随面积递减；LOFT 可额外溢价",
        levels=(
            ("≤35㎡", 1.08, "小户型单价上浮"),
            ("35-55㎡", 1.00, "主流"),
            (">55㎡", 0.94, "大户型单价下移"),
            ("LOFT", 1.30, "产品形态溢价"),
        ),
    ),
    FactorRule(
        key="floor_orient",
        name="楼层与朝向",
        rank=5,
        weight_pct=7.5,
        criteria="中高楼层、南北通透有小幅溢价；底层/顶楼折价",
        levels=(
            ("中高楼层", 1.05, "非顶楼"),
            ("底层/顶楼", 0.95, "折价"),
            ("南北通透", 1.06, "相对东西向"),
            ("南向", 1.03, "常见偏好"),
            ("北向/采光弱", 0.97, "略折"),
        ),
    ),
    FactorRule(
        key="amenity",
        name="周边配套成熟度",
        rank=6,
        weight_pct=7.5,
        criteria="商圈/产业聚集区带来稳定需求；配套弱则拖累出租率",
        levels=(
            ("成熟商圈/产业区", 1.06, "溢价约3-8%"),
            ("一般配套", 1.00, "中性"),
            ("配套较弱", 0.97, "略折"),
        ),
    ),
)

# 使用者可调权重默认=1（完全采用调研幅度）；键对应上表
USER_ADJUSTABLE_FACTORS: tuple[tuple[str, str, float], ...] = (
    ("metro", "地铁/交通", 0.275),
    ("decoration", "装修配置", 0.225),
    ("building_age", "房龄年代", 0.175),
    ("area_layout", "面积户型", 0.125),
    ("floor_orient", "楼层朝向", 0.075),
    ("amenity", "周边配套", 0.075),
)

DEFAULT_USER_WEIGHTS: dict[str, float] = {k: 1.0 for k, _, _ in USER_ADJUSTABLE_FACTORS}

FLOOR_OPTIONS = ["中高楼层", "底层", "顶楼"]
ORIENT_OPTIONS = ["南北通透", "南向", "东西向", "北向"]
AMENITY_OPTIONS = ["成熟商圈/产业区", "一般配套", "配套较弱"]
METRO_OPTIONS = ["距站<500m", "500-800m", ">800m"]


def resolve_district(text: str) -> str | None:
    """从文本识别行政区。优先匹配「XX区/XX新区」完整形态。"""
    import re

    blob = text or ""
    if not blob:
        return None
    m = re.search(
        r"(黄浦|静安|徐汇|长宁|虹口|杨浦|普陀|闵行|宝山|嘉定|松江|青浦|奉贤|金山|崇明|浦东)(?:新区|区)",
        blob,
    )
    if m:
        return m.group(1)
    for plate, dist in PLATE_TO_DISTRICT.items():
        if plate in blob:
            return dist
    # 纯区名（浦东放最后，减少误伤）
    for name in DISTRICT_NAMES:
        if name in blob:
            return name
    return None


def infer_district(*parts: str, fallback: str | None = None) -> str:
    """综合地址/小区/区字段推断行政区。地址中的「XX区」优先于可能过期的 district 字段。"""
    # 1) 带「区」字的文本最优先（如 上海市长宁区北新泾）
    for p in parts:
        if not p:
            continue
        if "区" in p or "北新泾" in p or any(k in p for k in PLATE_TO_DISTRICT):
            d = resolve_district(p)
            if d:
                return d
    # 2) 合并全文再解析
    blob = " ".join(str(p) for p in parts if p)
    d = resolve_district(blob)
    if d:
        return d
    return fallback or "徐汇"


def resolve_plate_adjust(text: str) -> tuple[str | None, float]:
    for plate, adj in PLATE_ADJUST.items():
        if plate in (text or ""):
            return plate, adj
    return None, 0.0


def district_base_interior_price(district: str, address_text: str = "") -> float:
    d = infer_district(address_text, district, fallback="徐汇")
    base = DISTRICT_INTERIOR_UNIT_PRICE.get(d, DISTRICT_INTERIOR_UNIT_PRICE["徐汇"])
    plate, adj = resolve_plate_adjust(f"{address_text}{district}")
    return round(base + adj, 2)


def metro_coefficient(metro_band: str) -> float:
    return {"距站<500m": 1.30, "500-800m": 1.15, ">800m": 1.00}.get(metro_band, 1.00)


def decoration_coefficient(decoration: str) -> float:
    return {"精装": 1.25, "简装": 1.10, "毛坯": 1.00}.get(decoration, 1.25)


def age_coefficient(age: int, has_elevator: bool = True) -> float:
    if age < 5:
        c = 1.05
    elif age <= 15:
        c = 1.00
    else:
        c = 0.85
    if not has_elevator:
        c *= 0.94  # 楼梯房相对电梯约 -5~-8%
    return round(c, 3)


def area_layout_coefficient(area: float, layout: str) -> float:
    if "LOFT" in (layout or "").upper() or "双钥匙" in (layout or ""):
        return 1.30
    if area <= 35:
        return 1.08
    if area <= 55:
        return 1.00
    return 0.94


def floor_orient_coefficient(floor: str, orientation: str) -> float:
    floor_c = 1.05 if floor == "中高楼层" else 0.95
    orient_c = {
        "南北通透": 1.06,
        "南向": 1.03,
        "东西向": 1.00,
        "北向": 0.97,
    }.get(orientation, 1.00)
    # 合并为单项系数（楼层×朝向开方归一，避免叠乘过大）：取几何合成再温和化
    return round((floor_c * orient_c) ** 0.5 * ((floor_c + orient_c) / 2) ** 0.5, 3)


def amenity_coefficient(amenity: str) -> float:
    return {
        "成熟商圈/产业区": 1.06,
        "一般配套": 1.00,
        "配套较弱": 0.97,
    }.get(amenity, 1.00)


def apply_user_weight(coef: float, user_weight: float) -> float:
    """生效系数 = 1 + (coef-1) × 用户权重。权重0→中性，1→调研全幅，2→加倍。"""
    w = max(0.0, float(user_weight))
    return round(1.0 + (coef - 1.0) * w, 4)
