"""输入输出模型（上海独卫公寓 / 套内面积 / 六大因子）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .shanghai_market import DEFAULT_USER_WEIGHTS

if TYPE_CHECKING:
    from .rent_trend import RentTrend

DAYLIGHT_TYPES = ["带阳台", "明窗", "天井窗"]
DECORATION_SIMPLE = ["精装", "简装"]
GREENERY_LEVELS = ["优", "良", "一般", "较差"]
LAYOUT_OPTIONS = ["LOFT", "开间STUDIO", "一室一厅", "两室一厅"]

_LAYOUT_ALIASES = {
    "开间": "开间STUDIO",
    "STUDIO": "开间STUDIO",
    "studio": "开间STUDIO",
    "一房": "一室一厅",
    "一室": "一室一厅",
    "两房": "两室一厅",
    "两室": "两室一厅",
    "三房": "两室一厅",
    "双钥匙": "LOFT",
    "其他": "一室一厅",
}


def normalize_layout(layout: str) -> str:
    """统一户型枚举；兼容历史「开间/一房/两房」写法。"""
    s = (layout or "").strip()
    if s in LAYOUT_OPTIONS:
        return s
    if s in _LAYOUT_ALIASES:
        return _LAYOUT_ALIASES[s]
    upper = s.upper()
    if "LOFT" in upper:
        return "LOFT"
    if "STUDIO" in upper or "开间" in s:
        return "开间STUDIO"
    if "两室" in s or "两房" in s:
        return "两室一厅"
    if "一室" in s or "一房" in s:
        return "一室一厅"
    return "一室一厅"


@dataclass
class GeoPoint:
    lng: float
    lat: float
    address: str = ""
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AreaMarketReport:
    radius_m: float
    overall: dict[str, Any]
    apartment: dict[str, Any]
    residential: dict[str, Any]
    analysis_lines: list[str] = field(default_factory=list)
    sample_count: int = 0
    area_basis_note: str = ""
    data_as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimplePricingInput:
    city: str = "上海"
    district: str = ""
    community: str = ""
    address: str = ""
    lng: float | None = None
    lat: float | None = None
    layout: str = "一室一厅"
    area: float = 30.0  # 输入为套内面积
    decoration: str = "精装"
    building_age: int = 8
    greenery: str = "良"
    daylight: str = "明窗"
    private_bath: bool = True
    metro_band: str = "500-800m"
    floor: str = "中高楼层"
    orientation: str = "南向"
    has_elevator: bool = True
    amenity: str = "一般配套"
    user_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_USER_WEIGHTS))
    base_unit_price_override: float = 0.0
    search_mode: str = ""

    def location_label(self) -> str:
        if self.address:
            return self.address
        parts = [p for p in (self.city, self.district, self.community) if p]
        return "/".join(parts) if parts else "未定位"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimplePricingInput:
        weights = dict(DEFAULT_USER_WEIGHTS)
        raw_w = data.get("user_weights") or {}
        if isinstance(raw_w, dict):
            for k, v in raw_w.items():
                try:
                    weights[str(k)] = float(v)
                except (TypeError, ValueError):
                    pass
        return cls(
            city=str(data.get("city", "上海") or "上海"),
            district=str(data.get("district", "") or ""),
            community=str(data.get("community", "") or ""),
            address=str(data.get("address", "") or ""),
            lng=_opt_float(data.get("lng")),
            lat=_opt_float(data.get("lat")),
            layout=normalize_layout(str(data.get("layout", "一室一厅") or "一室一厅")),
            area=float(data.get("area", 30) or 30),
            decoration=str(data.get("decoration", "精装") or "精装"),
            building_age=int(data.get("building_age", 8) or 8),
            greenery=str(data.get("greenery", "良") or "良"),
            daylight=str(data.get("daylight", "明窗") or "明窗"),
            private_bath=bool(data.get("private_bath", True)),
            metro_band=str(data.get("metro_band", "500-800m") or "500-800m"),
            floor=str(data.get("floor", "中高楼层") or "中高楼层"),
            orientation=str(data.get("orientation", "南向") or "南向"),
            has_elevator=bool(data.get("has_elevator", True)),
            amenity=str(data.get("amenity", "一般配套") or "一般配套"),
            user_weights=weights,
            base_unit_price_override=float(data.get("base_unit_price_override", 0) or 0),
            search_mode=str(data.get("search_mode", "") or ""),
        )


@dataclass
class PremiumFactor:
    name: str
    pct: float
    weight: str
    reason: str
    key: str = ""
    coefficient: float = 1.0
    system_coef: float = 1.0
    user_weight: float = 1.0
    rank: int = 0
    weight_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TenantPersona:
    primary: str
    occupation: str
    affordability: str
    needs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LeaseStrategy:
    lease_term: str
    payment: str
    pricing: str
    differentiation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompetitorRef:
    name: str
    layout: str
    area: float  # 统一套内面积（与输入同口径）
    distance_m: float
    price: float
    unit_price: float  # 按套内计
    source: str
    address: str = ""
    lng: float | None = None
    lat: float | None = None
    area_basis: str = "套内"
    segment: str = "集中式公寓"
    community: str = ""
    area_listed: float = 0.0
    area_listed_basis: str = "套内"  # 原挂牌：套内 / 建筑
    as_of: str = ""

    @property
    def display_name(self) -> str:
        if self.community and self.community not in self.name:
            return f"{self.community} · {self.name}"
        return self.name

    @property
    def area_basis_label(self) -> str:
        listed = self.area_listed or self.area
        if self.area_listed_basis == "建筑":
            return f"原建筑{listed:g}㎡→套内{self.area:g}㎡"
        return f"原套内{listed:g}㎡"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["display_name"] = self.display_name
        d["area_basis_label"] = self.area_basis_label
        return d


@dataclass
class PricingPrediction:
    location: str
    layout: str
    area: float
    base_unit_price: float
    adjusted_unit_price: float
    total_premium_pct: float
    composite_score: float
    rent_min: float
    rent_mid: float
    rent_max: float
    persona: TenantPersona
    premium_factors: list[PremiumFactor]
    strategy: LeaseStrategy
    area_report: AreaMarketReport | None = None
    surrounding_avg_rent: float | None = None
    surrounding_avg_unit_price: float | None = None
    apt_avg_rent: float | None = None
    residential_avg_rent: float | None = None
    competitors: list[CompetitorRef] = field(default_factory=list)
    map_points: list[GeoPoint] = field(default_factory=list)
    formula: str = ""
    notes: list[str] = field(default_factory=list)
    data_as_of: str = ""
    rent_trend: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "layout": self.layout,
            "area": self.area,
            "area_basis": "套内",
            "base_unit_price": self.base_unit_price,
            "adjusted_unit_price": self.adjusted_unit_price,
            "total_premium_pct": self.total_premium_pct,
            "composite_score": self.composite_score,
            "rent_min": round(self.rent_min),
            "rent_mid": round(self.rent_mid),
            "rent_max": round(self.rent_max),
            "公式": self.formula,
            "数据截至": self.data_as_of,
            "租金走势": self.rent_trend.to_dict() if self.rent_trend else None,
            "2km片区": self.area_report.to_dict() if self.area_report else None,
            "周边均价_月租": self.surrounding_avg_rent,
            "周边均价_套内单价": self.surrounding_avg_unit_price,
            "公寓样本均价": self.apt_avg_rent,
            "民居样本均价": self.residential_avg_rent,
            "客户画像": self.persona.to_dict(),
            "溢价因子": [f.to_dict() for f in self.premium_factors],
            "租赁策略": self.strategy.to_dict(),
            "竞品": [c.to_dict() for c in self.competitors],
            "notes": self.notes,
        }


def _opt_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
