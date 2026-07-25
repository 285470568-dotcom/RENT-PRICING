"""定价计算引擎：板块梯度、修正单价、分户型定价、收入敏感性。"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from .models import AdjustmentFactors, CompetitorListing, ProjectInput, UnitType


@dataclass
class UnitPricing:
    name: str
    area: float
    count: int
    unit_price: float
    mid_rent: float
    min_rent: float
    max_rent: float
    competitor_avg_rent: float | None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "户型": self.name,
            "面积": self.area,
            "套数": self.count,
            "建议最低价": round(self.min_rent),
            "建议中位价": round(self.mid_rent),
            "建议最高价": round(self.max_rent),
            "单价": round(self.unit_price, 2),
            "单价区间": f"{round(self.min_rent / self.area, 1)}-{round(self.max_rent / self.area, 1)}"
            if self.area
            else "-",
            "竞品均价": round(self.competitor_avg_rent) if self.competitor_avg_rent else None,
            "备注": self.notes,
        }


@dataclass
class SensitivityRow:
    occupancy: float
    annual_income: float
    gap_vs_full: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "出租率": f"{int(self.occupancy * 100)}%",
            "年收入（万元）": round(self.annual_income / 10000, 2),
            "vs满租缺口（万元）": round(self.gap_vs_full / 10000, 2)
            if self.gap_vs_full
            else "-",
        }


@dataclass
class PricingResult:
    base_unit_price: float
    adjusted_unit_price: float
    total_adjustment_pct: float
    factor_breakdown: list[tuple[str, float]]
    segment_stats: dict[str, dict[str, float]]
    unit_pricings: list[UnitPricing]
    full_month_income: float
    full_year_income: float
    sensitivity: list[SensitivityRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_unit_price": self.base_unit_price,
            "adjusted_unit_price": self.adjusted_unit_price,
            "total_adjustment_pct": self.total_adjustment_pct,
            "factor_breakdown": [
                {"factor": k, "pct": v} for k, v in self.factor_breakdown
            ],
            "segment_stats": self.segment_stats,
            "unit_pricings": [u.to_dict() for u in self.unit_pricings],
            "full_month_income": self.full_month_income,
            "full_year_income": self.full_year_income,
            "sensitivity": [s.to_dict() for s in self.sensitivity],
        }


class PricingEngine:
    """按 SOP Step 3-6 执行定价与收入测算。"""

    def analyze_segments(
        self, listings: list[CompetitorListing]
    ) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = {}
        for level in ("高端", "中端", "低端"):
            prices = [x.unit_price for x in listings if x.segment == level and x.unit_price > 0]
            if prices:
                stats[level] = {
                    "min": round(min(prices), 2),
                    "max": round(max(prices), 2),
                    "avg": round(mean(prices), 2),
                    "count": float(len(prices)),
                }
            else:
                stats[level] = {"min": 0.0, "max": 0.0, "avg": 0.0, "count": 0.0}
        return stats

    def suggest_base_price(
        self,
        project: ProjectInput,
        listings: list[CompetitorListing],
    ) -> float:
        if project.base_unit_price > 0:
            return project.base_unit_price

        stats = self.analyze_segments(listings)
        segment = project.target_segment or "中端"
        if stats.get(segment, {}).get("avg", 0) > 0:
            return stats[segment]["avg"]

        all_prices = [x.unit_price for x in listings if x.unit_price > 0]
        if all_prices:
            return round(mean(all_prices), 2)
        return 0.0

    def adjusted_price(
        self, base: float, factors: AdjustmentFactors
    ) -> tuple[float, float]:
        total_pct = factors.total_pct()
        adjusted = base * (1 + total_pct / 100.0)
        return round(adjusted, 2), total_pct

    def price_units(
        self,
        units: list[UnitType],
        adjusted_unit_price: float,
        elasticity_low_pct: float,
        elasticity_high_pct: float,
        listings: list[CompetitorListing],
        special_product_pct: float = 0.0,
    ) -> list[UnitPricing]:
        results: list[UnitPricing] = []
        for unit in units:
            unit_price = adjusted_unit_price
            notes = ""
            if unit.is_special and special_product_pct:
                # 特殊产品形态已在全局因子中计入时避免重复；此处仅标注
                notes = "特殊产品形态，已含产品溢价因子"
            elif unit.is_special:
                notes = "建议单独评估双钥匙/LOFT溢价"

            mid = unit.area * unit_price
            low = mid * (1 - elasticity_low_pct / 100.0)
            high = mid * (1 + elasticity_high_pct / 100.0)
            comp_avg = self._competitor_avg_for_unit(unit, listings)

            results.append(
                UnitPricing(
                    name=unit.name,
                    area=unit.area,
                    count=unit.count,
                    unit_price=unit_price,
                    mid_rent=mid,
                    min_rent=low,
                    max_rent=high,
                    competitor_avg_rent=comp_avg,
                    notes=notes,
                )
            )
        return results

    def _competitor_avg_for_unit(
        self, unit: UnitType, listings: list[CompetitorListing]
    ) -> float | None:
        if not listings or unit.area <= 0:
            return None
        # 面积相近（±15%）的同类户型
        matches = []
        for item in listings:
            if item.area <= 0 or item.rent <= 0:
                continue
            if abs(item.area - unit.area) / unit.area <= 0.15:
                matches.append(item.rent)
            elif unit.name and unit.name in item.layout:
                matches.append(item.rent)
        if not matches:
            return None
        return round(mean(matches), 2)

    def income_sensitivity(
        self, unit_pricings: list[UnitPricing], rates: list[float] | None = None
    ) -> tuple[float, float, list[SensitivityRow]]:
        rates = rates or [1.0, 0.9, 0.8]
        full_month = sum(u.mid_rent * u.count for u in unit_pricings)
        full_year = full_month * 12
        rows = [
            SensitivityRow(
                occupancy=r,
                annual_income=full_year * r,
                gap_vs_full=full_year * (1 - r),
            )
            for r in rates
        ]
        return full_month, full_year, rows

    def run(
        self,
        project: ProjectInput,
        listings: list[CompetitorListing],
        factors: AdjustmentFactors,
    ) -> PricingResult:
        segment_stats = self.analyze_segments(listings)

        # 若未手动填板块梯度，用竞品统计回填展示用区间
        if project.high_segment_range == (0.0, 0.0) and segment_stats["高端"]["count"]:
            project.high_segment_range = (
                segment_stats["高端"]["min"],
                segment_stats["高端"]["max"],
            )
        if project.mid_segment_range == (0.0, 0.0) and segment_stats["中端"]["count"]:
            project.mid_segment_range = (
                segment_stats["中端"]["min"],
                segment_stats["中端"]["max"],
            )
        if project.low_segment_range == (0.0, 0.0) and segment_stats["低端"]["count"]:
            project.low_segment_range = (
                segment_stats["低端"]["min"],
                segment_stats["低端"]["max"],
            )

        base = self.suggest_base_price(project, listings)
        adjusted, total_pct = self.adjusted_price(base, factors)
        unit_pricings = self.price_units(
            units=project.units,
            adjusted_unit_price=adjusted,
            elasticity_low_pct=project.elasticity_low_pct,
            elasticity_high_pct=project.elasticity_high_pct,
            listings=listings,
            special_product_pct=factors.special_product,
        )
        month, year, sensitivity = self.income_sensitivity(unit_pricings)

        return PricingResult(
            base_unit_price=base,
            adjusted_unit_price=adjusted,
            total_adjustment_pct=total_pct,
            factor_breakdown=factors.items(),
            segment_stats=segment_stats,
            unit_pricings=unit_pricings,
            full_month_income=month,
            full_year_income=year,
            sensitivity=sensitivity,
        )
