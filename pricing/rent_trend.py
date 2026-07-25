"""查询时点前后 6 个月租金曲线：历史指数回推 + 公开预测推演。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "shanghai_rent_index.json"


@dataclass
class TrendPoint:
    month: str  # YYYY-MM
    rent: float
    phase: str  # 历史回推 | 查询时点 | 前瞻推演
    index: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RentTrend:
    district: str
    anchor_rent: float
    as_of_month: str
    points: list[TrendPoint] = field(default_factory=list)
    history_note: str = ""
    forecast_note: str = ""
    disclaimer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "district": self.district,
            "anchor_rent": self.anchor_rent,
            "as_of_month": self.as_of_month,
            "points": [p.to_dict() for p in self.points],
            "history_note": self.history_note,
            "forecast_note": self.forecast_note,
            "disclaimer": self.disclaimer,
        }

    def to_chart_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "月份": p.month,
                "建议月租": round(p.rent),
                "阶段": p.phase,
            }
            for p in self.points
        ]


def _load_index() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _shift_month(ym: str, delta: int) -> str:
    y, m = map(int, ym.split("-"))
    m0 = y * 12 + (m - 1) + delta
    return f"{m0 // 12:04d}-{(m0 % 12) + 1:02d}"


def _pick_district(district: str, mapping: dict[str, Any]) -> str:
    d = (district or "").replace("区", "").strip() or "上海"
    if d in mapping:
        return d
    if "上海" in mapping:
        return "上海"
    return next(iter(mapping), "上海")


def build_rent_trend(
    anchor_rent: float,
    district: str,
    *,
    as_of: date | None = None,
    months_back: int = 6,
    months_forward: int = 6,
) -> RentTrend:
    """以当前建议中位租金为锚，回推 months_back、前瞻 months_forward。"""
    raw = _load_index()
    as_of = as_of or date.today()
    base_month = f"{as_of.year:04d}-{as_of.month:02d}"
    # 若指数库 base_month 与查询月不一致，仍以查询月为锚（指数相对 100）
    hist_all = raw.get("history_index") or {}
    dist_key = _pick_district(district, hist_all) if hist_all else (district or "上海")
    city_hist = hist_all.get("上海") or {}
    dist_hist = hist_all.get(dist_key) or city_hist

    forecast_all = raw.get("forecast_mom") or {}
    forecast = list(
        forecast_all.get(dist_key)
        or forecast_all.get("上海")
        or [0.0015] * months_forward
    )
    while len(forecast) < months_forward:
        forecast.append(forecast[-1] if forecast else 0.0015)

    meta = raw.get("meta") or {}
    # 当前指数：优先用库中该月，否则 100
    idx_now = float(dist_hist.get(base_month) or city_hist.get(base_month) or 100.0)
    if idx_now <= 0:
        idx_now = 100.0

    points: list[TrendPoint] = []
    # 历史：month = base - k
    for k in range(months_back, 0, -1):
        ym = _shift_month(base_month, -k)
        idx = float(dist_hist.get(ym) or city_hist.get(ym) or 0)
        if idx <= 0:
            # 缺月：用邻近线性近似（相对现价按每月 -0.3% 粗回推）
            idx = idx_now * ((1.003) ** k)
        rent = anchor_rent * (idx / idx_now)
        points.append(TrendPoint(month=ym, rent=round(rent, 1), phase="历史回推", index=round(idx, 2)))

    points.append(
        TrendPoint(
            month=base_month,
            rent=round(float(anchor_rent), 1),
            phase="查询时点",
            index=round(idx_now, 2),
        )
    )

    rent_f = float(anchor_rent)
    for i in range(months_forward):
        mom = float(forecast[i])
        rent_f *= 1.0 + mom
        ym = _shift_month(base_month, i + 1)
        points.append(
            TrendPoint(
                month=ym,
                rent=round(rent_f, 1),
                phase="前瞻推演",
                index=round(idx_now * (rent_f / float(anchor_rent)), 2),
            )
        )

    return RentTrend(
        district=dist_key,
        anchor_rent=round(float(anchor_rent), 1),
        as_of_month=base_month,
        points=points,
        history_note=str(meta.get("history_method") or "市/区指数回推"),
        forecast_note=str(meta.get("forecast_method") or "公开预测情景推演"),
        disclaimer=str(meta.get("disclaimer") or ""),
    )
