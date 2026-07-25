"""SOP Step 4 定价调整因子默认区间。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorRange:
    """调整因子的建议区间（百分比）。"""

    key: str
    label: str
    direction: str  # premium / discount
    min_pct: float
    max_pct: float
    weight: str  # 极高 / 高 / 中 / 低
    tip: str


DEFAULT_FACTORS: list[FactorRange] = [
    FactorRange(
        key="metro_near",
        label="地铁距离（<500m）",
        direction="premium",
        min_pct=5.0,
        max_pct=10.0,
        weight="高",
        tip="步行约6分钟内到站，核心溢价因子",
    ),
    FactorRange(
        key="metro_mid",
        label="地铁距离（500-1000m）",
        direction="premium",
        min_pct=3.0,
        max_pct=5.0,
        weight="中",
        tip="可接受通勤半径，中等溢价",
    ),
    FactorRange(
        key="furnished",
        label="精装拎包入住",
        direction="premium",
        min_pct=5.0,
        max_pct=8.0,
        weight="中",
        tip="相对毛坯/简装的装修溢价",
    ),
    FactorRange(
        key="old_building",
        label="房龄>15年老小区",
        direction="discount",
        min_pct=10.0,
        max_pct=15.0,
        weight="高",
        tip="设施老化、客群支付意愿下降",
    ),
    FactorRange(
        key="elevator",
        label="电梯房（vs楼梯房）",
        direction="premium",
        min_pct=5.0,
        max_pct=8.0,
        weight="中",
        tip="高层/中高层通勤便利溢价",
    ),
    FactorRange(
        key="amenity",
        label="特殊配套（商圈/学校/医院）",
        direction="premium",
        min_pct=3.0,
        max_pct=5.0,
        weight="低",
        tip="生活便利与刚需配套溢价",
    ),
    FactorRange(
        key="special_product",
        label="产品形态差异（双钥匙/LOFT）",
        direction="premium",
        min_pct=20.0,
        max_pct=40.0,
        weight="极高",
        tip="稀缺产品形态，按户型单独评估",
    ),
]

# 板块属性选项
DISTRICT_TYPES = ["核心", "次核心", "次新", "新兴", "老城"]

# 装修标准
DECORATION_LEVELS = ["毛坯", "简装", "精装", "拎包入住"]

# 物业类型
PROPERTY_TYPES = ["高层", "多层", "公寓", "别墅", "其他"]

# 板块层级
SEGMENT_LEVELS = ["高端", "中端", "低端"]

# 搜索平台建议（SOP Step 2）
SEARCH_PLATFORMS = [
    {"platform": "58同城", "query": "[小区名] 租房", "use": "真实挂牌价"},
    {"platform": "安居客", "query": "[小区名] [户型] 租金", "use": "价格区间验证"},
    {"platform": "房天下", "query": "[板块名] 租房", "use": "板块均价参照"},
    {"platform": "贝壳", "query": "[小区名]", "use": "成交参考价（如有）"},
]
