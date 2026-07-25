"""数据模型：项目输入、竞品、调整因子。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class UnitType:
    """户型配置。"""

    name: str
    area: float  # ㎡
    count: int
    notes: str = ""
    is_special: bool = False  # 双钥匙/LOFT 等

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnitType:
        return cls(
            name=str(data.get("name", "")),
            area=float(data.get("area", 0) or 0),
            count=int(data.get("count", 0) or 0),
            notes=str(data.get("notes", "") or ""),
            is_special=bool(data.get("is_special", False)),
        )


@dataclass
class CompetitorListing:
    """竞品挂牌/成交记录。"""

    community: str
    layout: str
    area: float
    rent: float  # 月租金（元）
    building_age: int | None = None
    decoration: str = ""
    floor: str = ""
    orientation: str = ""
    segment: str = "中端"  # 高端/中端/低端
    source: str = ""
    source_url: str = ""
    notes: str = ""

    @property
    def unit_price(self) -> float:
        if self.area <= 0:
            return 0.0
        return round(self.rent / self.area, 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["unit_price"] = self.unit_price
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompetitorListing:
        return cls(
            community=str(data.get("community", "")),
            layout=str(data.get("layout", "")),
            area=float(data.get("area", 0) or 0),
            rent=float(data.get("rent", 0) or 0),
            building_age=_optional_int(data.get("building_age")),
            decoration=str(data.get("decoration", "") or ""),
            floor=str(data.get("floor", "") or ""),
            orientation=str(data.get("orientation", "") or ""),
            segment=str(data.get("segment", "中端") or "中端"),
            source=str(data.get("source", "") or ""),
            source_url=str(data.get("source_url", "") or ""),
            notes=str(data.get("notes", "") or ""),
        )


@dataclass
class AdjustmentFactors:
    """定价修正因子（百分比，正为溢价，负为折旧）。"""

    metro: float = 0.0
    decoration: float = 0.0
    building_age: float = 0.0
    elevator: float = 0.0
    amenity: float = 0.0
    special_product: float = 0.0
    other: float = 0.0
    other_label: str = ""

    def total_pct(self) -> float:
        return (
            self.metro
            + self.decoration
            + self.building_age
            + self.elevator
            + self.amenity
            + self.special_product
            + self.other
        )

    def items(self) -> list[tuple[str, float]]:
        rows = [
            ("地铁溢价", self.metro),
            ("装修溢价", self.decoration),
            ("房龄折旧", self.building_age),
            ("电梯溢价", self.elevator),
            ("配套溢价", self.amenity),
            ("产品形态溢价", self.special_product),
        ]
        if self.other != 0 or self.other_label:
            label = self.other_label or "其他调整"
            rows.append((label, self.other))
        return rows

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdjustmentFactors:
        return cls(
            metro=float(data.get("metro", 0) or 0),
            decoration=float(data.get("decoration", 0) or 0),
            building_age=float(data.get("building_age", 0) or 0),
            elevator=float(data.get("elevator", 0) or 0),
            amenity=float(data.get("amenity", 0) or 0),
            special_product=float(data.get("special_product", 0) or 0),
            other=float(data.get("other", 0) or 0),
            other_label=str(data.get("other_label", "") or ""),
        )


@dataclass
class ProjectInput:
    """甲方输入 + 项目基本面。"""

    project_name: str = ""
    address: str = ""
    district: str = ""
    district_type: str = "次核心"
    metro_line: str = ""
    metro_station: str = ""
    metro_distance_m: int | None = None
    building_year: int | None = None
    property_type: str = "公寓"
    decoration: str = "拎包入住"
    has_elevator: bool = True
    plot_ratio: str = ""
    property_fee: str = ""
    total_units: int | None = None
    competitor_radius: str = "周边1km范围内同类小区"
    target_tenants: str = ""
    constraints: str = ""
    units: list[UnitType] = field(default_factory=list)
    high_segment_range: tuple[float, float] = (0.0, 0.0)
    mid_segment_range: tuple[float, float] = (0.0, 0.0)
    low_segment_range: tuple[float, float] = (0.0, 0.0)
    target_segment: str = "中端"
    base_unit_price: float = 0.0
    elasticity_low_pct: float = 8.0
    elasticity_high_pct: float = 8.0
    risks: list[str] = field(default_factory=list)
    strategy_lease: str = ""
    strategy_payment: str = ""
    strategy_pricing: str = ""
    strategy_diff: str = ""
    tenant_profile: dict[str, str] = field(default_factory=dict)
    research_date: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def building_age(self) -> int | None:
        if self.building_year is None:
            return None
        return max(0, date.today().year - self.building_year)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["building_age"] = self.building_age
        d["units"] = [u.to_dict() for u in self.units]
        d["high_segment_range"] = list(self.high_segment_range)
        d["mid_segment_range"] = list(self.mid_segment_range)
        d["low_segment_range"] = list(self.low_segment_range)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectInput:
        units = [UnitType.from_dict(u) for u in data.get("units", []) or []]
        return cls(
            project_name=str(data.get("project_name", "") or ""),
            address=str(data.get("address", "") or ""),
            district=str(data.get("district", "") or ""),
            district_type=str(data.get("district_type", "次核心") or "次核心"),
            metro_line=str(data.get("metro_line", "") or ""),
            metro_station=str(data.get("metro_station", "") or ""),
            metro_distance_m=_optional_int(data.get("metro_distance_m")),
            building_year=_optional_int(data.get("building_year")),
            property_type=str(data.get("property_type", "公寓") or "公寓"),
            decoration=str(data.get("decoration", "拎包入住") or "拎包入住"),
            has_elevator=bool(data.get("has_elevator", True)),
            plot_ratio=str(data.get("plot_ratio", "") or ""),
            property_fee=str(data.get("property_fee", "") or ""),
            total_units=_optional_int(data.get("total_units")),
            competitor_radius=str(
                data.get("competitor_radius", "周边1km范围内同类小区") or ""
            ),
            target_tenants=str(data.get("target_tenants", "") or ""),
            constraints=str(data.get("constraints", "") or ""),
            units=units,
            high_segment_range=_pair(data.get("high_segment_range")),
            mid_segment_range=_pair(data.get("mid_segment_range")),
            low_segment_range=_pair(data.get("low_segment_range")),
            target_segment=str(data.get("target_segment", "中端") or "中端"),
            base_unit_price=float(data.get("base_unit_price", 0) or 0),
            elasticity_low_pct=float(data.get("elasticity_low_pct", 8) or 8),
            elasticity_high_pct=float(data.get("elasticity_high_pct", 8) or 8),
            risks=list(data.get("risks", []) or []),
            strategy_lease=str(data.get("strategy_lease", "") or ""),
            strategy_payment=str(data.get("strategy_payment", "") or ""),
            strategy_pricing=str(data.get("strategy_pricing", "") or ""),
            strategy_diff=str(data.get("strategy_diff", "") or ""),
            tenant_profile=dict(data.get("tenant_profile", {}) or {}),
            research_date=str(data.get("research_date") or date.today().isoformat()),
        )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pair(value: Any) -> tuple[float, float]:
    if not value:
        return (0.0, 0.0)
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (float(value[0] or 0), float(value[1] or 0))
    return (0.0, 0.0)
