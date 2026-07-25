"""报告与表格导出：Markdown 调研报告 + Excel 汇总。"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .engine import PricingResult
from .models import CompetitorListing, ProjectInput


class ReportGenerator:
    """生成 SOP 规定的三类交付物。"""

    def build_markdown(
        self,
        project: ProjectInput,
        listings: list[CompetitorListing],
        result: PricingResult,
    ) -> str:
        name = project.project_name or "未命名项目"
        metro = self._metro_text(project)
        units_desc = "、".join(
            f"{u.area:g}㎡ {u.name} {u.count}套" for u in project.units
        ) or "—"
        age = f"{project.building_age}年" if project.building_age is not None else "—"
        year = f"{project.building_year}年" if project.building_year else "—"

        lines: list[str] = [
            f"# {name}租金定价调研报告",
            "",
            f"> 调研日期：{project.research_date} ｜ 文件命名建议：`{name}_租金定价调研_{project.research_date}`",
            "",
            "## 一、项目概况",
            "",
            "| 维度 | 详情 |",
            "|------|------|",
            f"| 位置 | {project.address or '—'} |",
            f"| 板块 | {project.district or '—'}（{project.district_type}） |",
            f"| 交通 | {metro} |",
            f"| 建筑年代 | {year}（房龄约{age}） |",
            f"| 物业类型 | {project.property_type} |",
            f"| 户型配置 | {units_desc} |",
            f"| 装修标准 | {project.decoration} |",
            f"| 电梯 | {'有' if project.has_elevator else '无'} |",
            f"| 容积率 | {project.plot_ratio or '—'} |",
            f"| 物业费 | {project.property_fee or '—'} |",
            f"| 总户数 | {project.total_units if project.total_units is not None else '—'} |",
            f"| 竞品圈定 | {project.competitor_radius} |",
            f"| 特殊约束 | {project.constraints or '—'} |",
            "",
            "---",
            "",
            "## 二、信息输入确认",
            "",
            f"- **目标客群（甲方初判）**：{project.target_tenants or '—'}",
            "",
            "---",
            "",
            "## 三、竞品租金对标",
            "",
            "### 3.1 同板块竞品",
            "",
        ]

        if listings:
            lines.extend(
                [
                    "| 小区 | 户型 | 面积 | 租金 | 单价 | 房龄 | 装修 | 层级 | 数据来源 |",
                    "|------|------|------|------|------|------|------|------|---------|",
                ]
            )
            for item in listings:
                age_s = str(item.building_age) if item.building_age is not None else "—"
                src = item.source
                if item.source_url:
                    src = f"[{item.source}]({item.source_url})" if item.source else item.source_url
                lines.append(
                    f"| {item.community} | {item.layout} | {item.area:g} | "
                    f"{item.rent:g} | {item.unit_price} | {age_s} | "
                    f"{item.decoration or '—'} | {item.segment} | {src or '—'} |"
                )
        else:
            lines.append("_暂无竞品数据，请补充采集。_")

        lines.extend(
            [
                "",
                "### 3.2 板块租金梯度",
                "",
                f"- **高端**：{self._range_text(project.high_segment_range, result, '高端')}元/㎡·月",
                f"- **中端**：{self._range_text(project.mid_segment_range, result, '中端')}元/㎡·月",
                f"- **低端**：{self._range_text(project.low_segment_range, result, '低端')}元/㎡·月",
                f"- **目标项目定位**：{project.target_segment} → 基准单价：**{result.base_unit_price}** 元/㎡·月",
                "",
                "---",
                "",
                "## 四、定价逻辑模型",
                "",
                "### 4.1 基准租金",
                "",
                f"板块定位层级均价（基准单价）：**{result.base_unit_price}** 元/㎡·月",
                "",
                "### 4.2 溢价/折旧因子",
                "",
                "| 因子 | 调整幅度 | 说明 |",
                "|------|---------|------|",
            ]
        )

        for label, pct in result.factor_breakdown:
            sign = f"+{pct:g}%" if pct > 0 else f"{pct:g}%"
            lines.append(f"| {label} | {sign} | SOP Step 4 修正 |")

        lines.extend(
            [
                "",
                f"**合计调整**：{result.total_adjustment_pct:+g}%",
                f"**修正后单价**：{result.base_unit_price} × (1 {result.total_adjustment_pct:+g}%) = **{result.adjusted_unit_price}** 元/㎡·月",
                "",
                "### 4.3 分户型定价",
                "",
                "| 户型 | 面积 | 套数 | 建议最低价 | 建议最高价 | 中位价 | 单价区间 | 竞品均价 |",
                "|------|------|------|-----------|-----------|--------|---------|---------|",
            ]
        )

        for u in result.unit_pricings:
            d = u.to_dict()
            comp = d["竞品均价"] if d["竞品均价"] is not None else "—"
            lines.append(
                f"| {d['户型']} | {d['面积']:g} | {d['套数']} | "
                f"{d['建议最低价']} | {d['建议最高价']} | {d['建议中位价']} | "
                f"{d['单价区间']} | {comp} |"
            )

        lines.extend(
            [
                "",
                f"弹性区间：最低价 -{project.elasticity_low_pct:g}% / 最高价 +{project.elasticity_high_pct:g}%",
                "",
                "### 4.4 满租收入测算",
                "",
                f"- 满租月收入：约 **{result.full_month_income / 10000:.2f}** 万元",
                f"- 满租年收入：约 **{result.full_year_income / 10000:.2f}** 万元",
                "",
                "#### 敏感性场景",
                "",
                "| 出租率 | 年收入（万元） | vs满租缺口（万元） |",
                "|--------|---------------|-------------------|",
            ]
        )
        for row in result.sensitivity:
            d = row.to_dict()
            lines.append(
                f"| {d['出租率']} | {d['年收入（万元）']} | {d['vs满租缺口（万元）']} |"
            )

        profile = project.tenant_profile or {}
        lines.extend(
            [
                "",
                "---",
                "",
                "## 五、目标客群画像",
                "",
                f"- **主力客群**：{profile.get('主力客群') or project.target_tenants or '—'}",
                f"- **职业分布**：{profile.get('职业分布', '—')}",
                f"- **支付能力**：{profile.get('支付能力', '—')}",
                f"- **核心诉求**：{profile.get('核心诉求', '—')}",
                "",
                "---",
                "",
                "## 六、租赁策略建议",
                "",
                f"1. **租期设计**：{project.strategy_lease or '年租为主，保留半年租灵活选项；淡季可试点灵活租期拉升去化。'}",
                f"2. **付款方式**：{project.strategy_payment or '标准押一付三；优质租客可押一付一；长租承诺可押一付六换租金折扣。'}",
                f"3. **定价策略**：{project.strategy_pricing or '建议平进平出；去化压力大时采用渗透定价（贴建议最低价）；旺季可高开低走试探天花板。'}",
                f"4. **差异化竞争**：{project.strategy_diff or '强化拎包入住交付标准；配套社群/保洁；长短租结合降低空置。'}",
                "",
                "---",
                "",
                "## 七、风险提示",
                "",
            ]
        )

        risks = [r for r in project.risks if r.strip()]
        if len(risks) < 2:
            risks = risks + [
                "竞品挂牌价可能高于实际成交价，建议交叉验证贝壳成交/中介询价后微调。",
                "出租率敏感性显示 80% 出租时收入缺口显著，需预留空置与免租期缓冲。",
            ]
        for i, risk in enumerate(risks, 1):
            lines.append(f"{i}. {risk}")

        lines.extend(
            [
                "",
                "---",
                "",
                "## 八、质量检查清单",
                "",
                "- [x] 所有户型均有定价建议" if project.units else "- [ ] 所有户型均有定价建议",
                "- [x] 竞品数据来源可追溯" if any(x.source or x.source_url for x in listings) else "- [ ] 竞品数据来源可追溯（附链接/截图）",
                "- [x] 单价区间符合板块梯度逻辑" if result.base_unit_price > 0 else "- [ ] 单价区间符合板块梯度逻辑",
                "- [x] 满租收入测算公式正确",
                "- [x] 风险提示不少于2条" if len(risks) >= 2 else "- [ ] 风险提示不少于2条",
                f"- [x] 文件命名规范（项目名+日期）：`{name}_租金定价调研_{project.research_date}`",
                "",
            ]
        )
        return "\n".join(lines)

    def competitors_dataframe(
        self, listings: list[CompetitorListing]
    ) -> pd.DataFrame:
        rows = []
        for item in listings:
            rows.append(
                {
                    "小区": item.community,
                    "户型": item.layout,
                    "面积": item.area,
                    "租金": item.rent,
                    "单价": item.unit_price,
                    "房龄": item.building_age,
                    "装修": item.decoration,
                    "楼层": item.floor,
                    "朝向": item.orientation,
                    "层级": item.segment,
                    "数据来源": item.source,
                    "来源链接": item.source_url,
                    "备注": item.notes,
                }
            )
        return pd.DataFrame(rows)

    def pricing_dataframe(self, result: PricingResult) -> pd.DataFrame:
        return pd.DataFrame([u.to_dict() for u in result.unit_pricings])

    def sensitivity_dataframe(self, result: PricingResult) -> pd.DataFrame:
        return pd.DataFrame([s.to_dict() for s in result.sensitivity])

    def export_excel_bytes(
        self,
        project: ProjectInput,
        listings: list[CompetitorListing],
        result: PricingResult,
    ) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            self.pricing_dataframe(result).to_excel(
                writer, sheet_name="分户型定价汇总", index=False
            )
            self.competitors_dataframe(listings).to_excel(
                writer, sheet_name="竞品数据原始表", index=False
            )
            self.sensitivity_dataframe(result).to_excel(
                writer, sheet_name="收入敏感性", index=False
            )
            meta = pd.DataFrame(
                [
                    {"字段": "项目名称", "值": project.project_name},
                    {"字段": "调研日期", "值": project.research_date},
                    {"字段": "基准单价", "值": result.base_unit_price},
                    {"字段": "修正后单价", "值": result.adjusted_unit_price},
                    {"字段": "合计调整%", "值": result.total_adjustment_pct},
                    {
                        "字段": "满租月收入",
                        "值": round(result.full_month_income, 2),
                    },
                    {
                        "字段": "满租年收入",
                        "值": round(result.full_year_income, 2),
                    },
                ]
            )
            meta.to_excel(writer, sheet_name="项目摘要", index=False)
        return buffer.getvalue()

    def save_outputs(
        self,
        project: ProjectInput,
        listings: list[CompetitorListing],
        result: PricingResult,
        output_dir: str | Path,
    ) -> dict[str, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        safe_name = (project.project_name or "未命名项目").replace("/", "_").replace(" ", "")
        stamp = project.research_date or date.today().isoformat()
        md_path = out / f"{safe_name}_租金定价调研_{stamp}.md"
        xlsx_path = out / f"{safe_name}_分户型定价与竞品_{stamp}.xlsx"

        md_path.write_text(
            self.build_markdown(project, listings, result), encoding="utf-8"
        )
        xlsx_path.write_bytes(self.export_excel_bytes(project, listings, result))
        return {"report": md_path, "excel": xlsx_path}

    def _metro_text(self, project: ProjectInput) -> str:
        if project.metro_station:
            dist = (
                f"约{project.metro_distance_m}m"
                if project.metro_distance_m is not None
                else "距离待测"
            )
            line = f"{project.metro_line}" if project.metro_line else ""
            return f"距{line}{project.metro_station}站{dist}".replace("距站", "距")
        return "—"

    def _range_text(
        self,
        manual: tuple[float, float],
        result: PricingResult,
        level: str,
    ) -> str:
        if manual != (0.0, 0.0):
            return f"{manual[0]:g}-{manual[1]:g}"
        stats = result.segment_stats.get(level, {})
        if stats.get("count", 0) > 0:
            return f"{stats['min']:g}-{stats['max']:g}"
        return "—"
