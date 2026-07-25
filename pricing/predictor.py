"""上海独卫公寓：六大因子乘法定价 + 2km 片区分析。"""

from __future__ import annotations

from .competitors import (
    RADIUS_2KM,
    build_area_report,
    find_nearby_2km,
    load_competitors,
    surrounding_stats,
    to_map_points,
)
from .shanghai_market import (
    DISTRICT_TIER,
    USER_ADJUSTABLE_FACTORS,
    age_coefficient,
    amenity_coefficient,
    apply_user_weight,
    area_layout_coefficient,
    decoration_coefficient,
    district_base_interior_price,
    floor_orient_coefficient,
    infer_district,
    metro_coefficient,
    resolve_plate_adjust,
)
from .rent_trend import build_rent_trend
from .simple_models import (
    DEFAULT_USER_WEIGHTS,
    LeaseStrategy,
    PremiumFactor,
    PricingPrediction,
    SimplePricingInput,
    TenantPersona,
)


class RentPredictor:
    ELASTICITY_LOW = 0.06
    ELASTICITY_HIGH = 0.08

    def predict(self, inp: SimplePricingInput) -> PricingPrediction:
        inp.private_bath = True
        weights = {**DEFAULT_USER_WEIGHTS, **(inp.user_weights or {})}

        base = self._base_price(inp)
        factors, product = self._factors_multiplicative(inp, weights)
        adjusted = round(base * product, 2)
        total_pct = round((product - 1.0) * 100.0, 2)
        score = round(min(100.0, max(0.0, 70 + total_pct * 0.9)), 1)

        mid = inp.area * adjusted
        low = mid * (1 - self.ELASTICITY_LOW)
        high = mid * (1 + self.ELASTICITY_HIGH)

        comps = []
        area_report = None
        if inp.lng is not None and inp.lat is not None:
            load_competitors()
            comps = find_nearby_2km(
                inp.lng,
                inp.lat,
                inp.layout,
                inp.area,
                district=infer_district(
                    inp.address, inp.community, inp.district, fallback="徐汇"
                ),
            )
            # 硬过滤：只保留 2km 内
            comps = [c for c in comps if c.distance_m <= RADIUS_2KM]
            area_report = build_area_report(comps, RADIUS_2KM)

            # 用片区中位套内单价微调中枢（避免脱离市场）
            if area_report and area_report.overall.get("median_unit"):
                market_u = float(area_report.overall["median_unit"])
                # 预测中位靠近片区：70%模型 + 30%片区
                blended_unit = adjusted * 0.7 + market_u * 0.3
                mid = inp.area * blended_unit
                low = mid * (1 - self.ELASTICITY_LOW)
                high = mid * (1 + self.ELASTICITY_HIGH)
                adjusted = round(blended_unit, 2)

        avg_rent, avg_unit, apt_avg, resi_avg = surrounding_stats(comps)
        persona = self._persona(inp, mid)
        strategy = self._strategy(inp, product, avg_rent, apt_avg, resi_avg, area_report)
        coef_parts = " × ".join(
            f"{f.name}({f.coefficient:g})" for f in factors if f.coefficient != 1 or f.key
        )
        formula = (
            f"建议租金 ≈ {inp.area:g}㎡ × 板块基准{base:g} × Π系数"
            f"（乘积={product:g}）→ 单价{adjusted:g}；"
            f"并与2km片区中位单价混合锚定"
        )

        notes = self._notes(inp, base, product, score, area_report)
        map_points = []
        if inp.lng is not None and inp.lat is not None:
            map_points = to_map_points(
                inp.community or "目标项目",
                inp.address or inp.location_label(),
                inp.lng,
                inp.lat,
                comps,
            )

        data_as_of = ""
        if area_report and getattr(area_report, "data_as_of", ""):
            data_as_of = area_report.data_as_of
        else:
            dates = [getattr(c, "as_of", "") for c in comps if getattr(c, "as_of", "")]
            data_as_of = max(dates) if dates else ""

        trend = build_rent_trend(mid, inp.district or "上海")

        return PricingPrediction(
            location=inp.location_label(),
            layout=inp.layout,
            area=inp.area,
            base_unit_price=base,
            adjusted_unit_price=adjusted,
            total_premium_pct=total_pct,
            composite_score=score,
            rent_min=low,
            rent_mid=mid,
            rent_max=high,
            persona=persona,
            premium_factors=factors,
            strategy=strategy,
            area_report=area_report,
            surrounding_avg_rent=avg_rent,
            surrounding_avg_unit_price=avg_unit,
            apt_avg_rent=apt_avg,
            residential_avg_rent=resi_avg,
            competitors=comps,
            map_points=map_points,
            formula=formula,
            notes=notes,
            data_as_of=data_as_of,
            rent_trend=trend,
        )

    def _base_price(self, inp: SimplePricingInput) -> float:
        if inp.base_unit_price_override > 0:
            return float(inp.base_unit_price_override)
        text = f"{inp.address}{inp.community}{inp.district}"
        # 强制用地址推断区，防止旧 district=浦东 污染
        inp.district = infer_district(inp.address, inp.community, inp.district, fallback="徐汇")
        return district_base_interior_price(inp.district, text)

    def _factors_multiplicative(
        self, inp: SimplePricingInput, weights: dict[str, float]
    ) -> tuple[list[PremiumFactor], float]:
        text = f"{inp.district}{inp.address}{inp.community}"
        # 地址/小区中的「XX区」优先，避免会话里残留的旧 district（如浦东）覆盖长宁
        district = infer_district(inp.address, inp.community, inp.district, fallback="徐汇")
        # 写回，保证后续竞品片区一致
        inp.district = district
        tier = DISTRICT_TIER.get(district, "近郊")
        plate, padj = resolve_plate_adjust(f"{inp.address}{inp.community}{text}")

        meta = {k: (n, w) for k, n, w in USER_ADJUSTABLE_FACTORS}

        raw = {
            "metro": metro_coefficient(inp.metro_band),
            "decoration": decoration_coefficient(inp.decoration),
            "building_age": age_coefficient(inp.building_age, inp.has_elevator),
            "area_layout": area_layout_coefficient(inp.area, inp.layout),
            "floor_orient": floor_orient_coefficient(inp.floor, inp.orientation),
            "amenity": amenity_coefficient(inp.amenity),
        }
        tips = {
            "metro": f"{inp.metro_band}",
            "decoration": f"{inp.decoration}拎包口径" if inp.decoration == "精装" else inp.decoration,
            "building_age": f"房龄{inp.building_age}年"
            + ("·电梯" if inp.has_elevator else "·楼梯房"),
            "area_layout": f"{inp.layout}/{inp.area:g}㎡套内",
            "floor_orient": f"{inp.floor}·{inp.orientation}",
            "amenity": inp.amenity,
        }

        factors: list[PremiumFactor] = [
            PremiumFactor(
                name="板块基准",
                pct=0.0,
                weight="锚点",
                reason=f"{district}（{tier}）"
                + (f"·{plate}{padj:+g}" if plate else "")
                + "；套内独卫锚点，尚未乘交通/装修等系数",
                key="plate",
                coefficient=1.0,
                system_coef=1.0,
            )
        ]

        product = 1.0
        rank_map = {1: "metro", 2: "decoration", 3: "building_age", 4: "area_layout", 5: "floor_orient", 6: "amenity"}
        # preserve order by rank
        for rank, key in rank_map.items():
            sys_c = raw[key]
            uw = float(weights.get(key, 1.0))
            eff = apply_user_weight(sys_c, uw)
            product *= eff
            name, w_pct = meta[key]
            factors.append(
                PremiumFactor(
                    name=f"{rank}.{name}",
                    pct=round((eff - 1) * 100, 2),
                    weight=f"调研权重约{w_pct*100:.0f}%",
                    reason=(
                        f"{tips[key]}｜系统系数{sys_c:g} → 用户权重{uw:g} → 生效{eff:g}"
                    ),
                    key=key,
                    coefficient=eff,
                    system_coef=sys_c,
                    user_weight=uw,
                    rank=rank,
                    weight_pct=w_pct * 100,
                )
            )

        return factors, round(product, 4)

    def _persona(self, inp: SimplePricingInput, mid: float) -> TenantPersona:
        if inp.area < 28 or "开间" in (inp.layout or "") or "STUDIO" in (inp.layout or "").upper():
            primary = "沪漂白领 / 工作1-4年青年（独卫+通勤刚需）"
            occupation = "金融、互联网、咨询、设计"
            needs = ["独卫", "近地铁", "精装即住"]
        elif inp.area < 45:
            primary = "年轻情侣 / 高质量单身"
            occupation = "双人白领、外企"
            needs = ["独卫", "采光朝向", "配套便利", "年租"]
        else:
            primary = "小家庭 / 企业中管短居"
            occupation = "双职工、派驻"
            needs = ["套内空间", "独卫", "配套与安静"]
        if inp.metro_band == "距站<500m":
            needs.insert(0, "地铁步行可达")
        affordability = (
            f"月租约 {round(mid * 0.92):.0f}-{round(mid * 1.08):.0f} 元；"
            f"收入大约 {round(mid / 0.30):.0f}-{round(mid / 0.22):.0f} 元/月"
        )
        return TenantPersona(primary, occupation, affordability, needs)

    def _strategy(self, inp, product, avg_rent, apt_avg, resi_avg, area_report) -> LeaseStrategy:
        lease = "主推12个月；淡季可6个月"
        payment = "押一付三为主；长约可押一付六换2-3%折扣"
        if product >= 1.25:
            pricing = "高开低走：贴近预测上限试探，10天无高质量带看回落中位"
        elif product <= 0.95:
            pricing = "渗透定价：贴近下限去化，强调性价比与独卫"
        else:
            pricing = "平进平出：以2km片区中位与模型中位交叉定价，每周按带看微调±3%"
        diff = "对照2km内公寓与民居价差，讲清地铁/装修/独卫溢价"
        if area_report and area_report.analysis_lines:
            diff += f"；{area_report.analysis_lines[0]}"
        return LeaseStrategy(lease, payment, pricing, diff)

    def _notes(self, inp, base, product, score, area_report) -> list[str]:
        notes = [
            "定价公式：面积 × 板块基准单价 × 地铁×装修×房龄×面积户型×楼层朝向×配套。",
            f"板块基准 {base} 元/㎡·月；系数乘积 {product:g}；组合评分 {score}。",
            "竞品严格限制在搜索点 2km 内；含集中式公寓与分散式民居。",
            "面积口径：输入为套内；竞品原挂牌若为建筑面积，按×0.78折套内后比价，明细中会标注原口径。",
            "真实挂牌优先，样本不足时以同片区密维样本补齐并标注校准来源。",
            "产品默认独立卫浴。",
        ]
        if area_report:
            notes.extend(area_report.analysis_lines)
        if inp.search_mode:
            notes.append(f"区位检索模式：{inp.search_mode}。")
        return notes
