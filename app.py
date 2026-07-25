"""上海独卫公寓租金研判 —— 2km 片区分析 + 六大因子乘法定价。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pricing.baidu_map import BaiduMapClient, ak_configured, get_ak, render_baidu_map_html
from pricing.competitors import RADIUS_2KM, load_competitors
from pricing.predictor import RentPredictor
from pricing.rent_trend import build_rent_trend
from pricing.shanghai_market import (
    AMENITY_OPTIONS,
    DISTRICT_NAMES,
    FLOOR_OPTIONS,
    METRO_OPTIONS,
    ORIENT_OPTIONS,
    SHANGHAI_FACTOR_RULES,
    USER_ADJUSTABLE_FACTORS,
    infer_district,
)
from pricing.simple_models import (
    DECORATION_SIMPLE,
    DEFAULT_USER_WEIGHTS,
    LAYOUT_OPTIONS,
    PricingPrediction,
    SimplePricingInput,
    normalize_layout,
)

ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "data" / "sample_shanghai.json"

st.set_page_config(
    page_title="上海公寓租金研判",
    page_icon="◇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@200;300;400;500&display=swap');
:root {
  --ink: #2a2620;
  --muted: #7a7268;
  --line: rgba(42,38,32,.12);
  --paper: #f8f5ef;
  --paper2: #f3efe6;
  --accent: #3d3429;
  --song: "Songti SC", "STSong", "Noto Serif SC", "SimSun", serif;
}
html, body, [class*="css"], .stApp, .stMarkdown, .stText, label, p, span, div {
  font-family: var(--song) !important;
  font-weight: 300 !important;
  color: var(--ink);
  letter-spacing: .02em;
}
.stApp { background: linear-gradient(180deg, var(--paper) 0%, var(--paper2) 100%); }
h1,h2,h3,h4,.hero-title,.out-h {
  font-family: var(--song) !important;
  font-weight: 400 !important;
  color: var(--accent) !important;
  letter-spacing: .08em !important;
}
.hero { padding: .35rem 0 1.1rem; border-bottom: 1px solid var(--line); margin-bottom: 1.1rem; }
.hero-kicker { font-size: .7rem; letter-spacing: .28em; color: var(--muted); font-weight: 300 !important; }
.hero-title { font-size: 2.05rem !important; margin: .25rem 0 0 !important; font-weight: 400 !important; }
.hero-sub { margin-top: .45rem; color: var(--muted); font-size: .92rem; max-width: 42rem; font-weight: 300 !important; line-height: 1.7; }
.section-label {
  font-size: .68rem; letter-spacing: .22em; text-transform: uppercase;
  color: var(--muted); margin: .85rem 0 .65rem; font-weight: 300 !important;
}
.out-wrap { margin-top: .2rem; }
.out-meta { color: var(--muted); font-size: .84rem; margin: 0 0 .9rem; font-weight: 300 !important; }
.metric-row {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 0;
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  margin: 0 0 1.1rem;
}
.metric-cell { padding: .85rem 1rem .9rem; border-right: 1px solid var(--line); }
.metric-cell:last-child { border-right: none; }
.metric-label { font-size: .72rem; color: var(--muted); letter-spacing: .14em; margin-bottom: .35rem; }
.metric-value { font-size: 1.55rem; font-weight: 400 !important; line-height: 1.2; letter-spacing: .04em; }
.metric-delta { font-size: .78rem; color: var(--muted); margin-top: .25rem; }
.out-formula { color: var(--muted); font-size: .82rem; line-height: 1.65; margin: 0 0 1.35rem; }
.out-h {
  font-size: 1.05rem !important; margin: 1.35rem 0 .55rem !important;
  padding-bottom: .35rem; border-bottom: 1px solid var(--line);
}
.out-note { color: var(--muted); font-size: .82rem; line-height: 1.65; margin: 0 0 .75rem; }
.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.1rem; margin: .4rem 0 1rem; }
.stat-block { padding: .15rem 0; }
.stat-title { font-size: .78rem; letter-spacing: .12em; color: var(--muted); margin-bottom: .35rem; }
.stat-body { font-size: .92rem; line-height: 1.7; font-weight: 300 !important; }
.analysis-list { margin: .2rem 0 1rem; padding: 0; list-style: none; }
.analysis-list li {
  position: relative; padding: .35rem 0 .35rem 1rem; color: var(--ink);
  font-size: .9rem; line-height: 1.7; border-bottom: 1px solid rgba(42,38,32,.06);
}
.analysis-list li::before { content: "·"; position: absolute; left: 0; color: var(--muted); }
.kv { width: 100%; border-collapse: collapse; margin: .2rem 0 .8rem; }
.kv th, .kv td {
  text-align: left; vertical-align: top; padding: .55rem 0;
  border-bottom: 1px solid rgba(42,38,32,.08); font-weight: 300 !important;
  font-size: .9rem; line-height: 1.65;
}
.kv th { width: 5.5rem; color: var(--muted); letter-spacing: .08em; font-weight: 300 !important; }
.strategy-ol { margin: .2rem 0 .8rem; padding-left: 1.1rem; }
.strategy-ol li { margin: .35rem 0; line-height: 1.7; font-size: .92rem; }
div[data-testid="stSidebar"] { background: #1a1713; }
div[data-testid="stSidebar"] * { color: #efe8dc !important; font-family: var(--song) !important; font-weight: 300 !important; }
.stButton > button {
  border-radius: 0 !important; background: #1c1915 !important; color: #f4efe6 !important;
  border: 1px solid #1c1915 !important; letter-spacing: .12em; font-family: var(--song) !important; font-weight: 300 !important;
}
[data-testid="stMetricValue"], [data-testid="stDataFrame"] {
  font-family: var(--song) !important; font-weight: 300 !important;
}
@media (max-width: 900px) {
  .metric-row, .stat-grid { grid-template-columns: 1fr 1fr; }
  .metric-cell { border-bottom: 1px solid var(--line); }
}
"""


def _init() -> None:
    load_competitors()
    st.session_state.setdefault("geo_confirmed", False)
    st.session_state.setdefault("suggests", [])
    st.session_state.setdefault("search_mode", "")
    st.session_state.setdefault("user_weights", dict(DEFAULT_USER_WEIGHTS))


def _apply_sample() -> None:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    for k, v in data.items():
        if k == "user_weights" and isinstance(v, dict):
            st.session_state.user_weights = {**DEFAULT_USER_WEIGHTS, **v}
        else:
            st.session_state[k] = v
    st.session_state.geo_confirmed = bool(data.get("lng") and data.get("lat"))
    st.session_state.suggests = []
    st.session_state.search_mode = data.get("search_mode", "fuzzy")


def _sidebar() -> str:
    with st.sidebar:
        st.markdown("### Shanghai Rent")
        st.caption("2km片区 · Top6因子 · 乘法模型")
        prefer = st.radio(
            "检索偏好",
            ["自动（百度优先，失败则模糊）", "仅模糊匹配", "仅百度地图"],
            index=0,
        )
        st.session_state.search_prefer = prefer
        if ak_configured():
            st.caption("百度定位：已内置（无需填写 AK）")
        else:
            ak_input = st.text_input("百度地图 AK", value="", type="password", help="也可写入 .streamlit/secrets.toml 常态化预设")
            if ak_input:
                st.session_state["BAIDU_MAP_AK_RUNTIME"] = ak_input
                os.environ["BAIDU_MAP_AK"] = ak_input
            else:
                st.caption("未配置 AK 时只能匹配本地名录")
        if st.button("填充徐汇示例", use_container_width=True):
            _apply_sample()
            st.rerun()
        st.divider()
        st.markdown("**六大影响因子（调研权重）**")
        for rule in SHANGHAI_FACTOR_RULES:
            with st.expander(f"{rule.rank}. {rule.name} · {rule.weight_pct:g}%"):
                st.caption(rule.criteria)
                for label, coef, tip in rule.levels:
                    st.write(f"· {label}：×{coef:g} — {tip}")
    return get_ak()


def _search_address(ak: str) -> None:
    st.markdown('<div class="section-label">区位检索</div>', unsafe_allow_html=True)
    st.caption(
        "请填写 **行政区 + 路名/小区/机构**（门牌号可选）。"
        + (
            "已启用百度定位。"
            if ak_configured()
            else "当前未内置百度 AK，定位能力有限。"
        )
    )
    dist_opts = ["（请选择行政区）", *DISTRICT_NAMES]
    cur_dist = st.session_state.get("search_district", "")
    dist_index = dist_opts.index(cur_dist) if cur_dist in dist_opts else 0
    c_dist, c_road, c_no = st.columns([1.1, 1.6, 0.9])
    with c_dist:
        search_district = st.selectbox("行政区（必选）", dist_opts, index=dist_index, key="search_district_ui")
    with c_road:
        q = st.text_input(
            "路名 / 小区 / 机构（必填）",
            value=st.session_state.get("search_q", ""),
            key="search_q",
            placeholder="如：宜山路、漕溪北路、某某小区",
        )
    with c_no:
        number = st.text_input(
            "门牌号（可选）",
            value=st.session_state.get("search_number", ""),
            key="search_number",
            placeholder="如：455号",
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("检索地址", use_container_width=True):
            st.session_state.geo_confirmed = False
            district = "" if search_district.startswith("（") else search_district
            st.session_state.search_district = district
            if not district:
                st.error("请先选择行政区")
                st.session_state.suggests = []
            elif not (q or "").strip() and not (number or "").strip():
                st.error("请填写路名/小区/机构，或门牌号")
                st.session_state.suggests = []
            else:
                prefer = st.session_state.get("search_prefer", "")
                use_ak = ak if (not prefer.startswith("仅模糊")) else ""
                if prefer.startswith("仅百度") and not ak:
                    st.warning("无百度 AK，无法做精准检索；请在侧栏填写 AK，或改用自动/模糊")
                client = BaiduMapClient(ak=use_ak)
                limit = 20
                hits, mode = client.suggest(
                    (q or "").strip(),
                    limit=limit,
                    district=district,
                    number=(number or "").strip(),
                    allow_approx=False,
                )
                # 仅模糊：只用本地强匹配
                if prefer.startswith("仅模糊"):
                    hits = client._fuzzy_suggest(
                        f"{(q or '').strip()}{(number or '').strip()}".strip(),
                        limit=limit,
                        district=district,
                    )
                    for h in hits:
                        h["mode"] = h.get("mode") or "fuzzy"
                    mode = "fuzzy"

                st.session_state.suggests = hits
                st.session_state.search_mode = mode
                if hits:
                    st.success(f"找到 {len(hits)} 处相关地址")
                else:
                    if not ak:
                        st.error(
                            "本地库未收录该地址，且未配置百度地图 AK，所以无法定位。"
                            "请点左上角展开侧栏，填写百度地图 AK 后再检索——"
                            "不是您输入格式有问题。"
                        )
                    else:
                        st.error(
                            "百度未返回匹配点。可尝试：去掉多余空格、确认行政区是否正确，"
                            "或把路名与门牌分填在两个框里。"
                        )
    with c2:
        if st.session_state.geo_confirmed:
            st.success("已锁定 · 将分析该点 2km 片区")
        else:
            st.caption(f"模式：{st.session_state.get('search_mode') or '—'}，请确认地址")

    suggests = [
        s
        for s in (st.session_state.suggests or [])
        if not s.get("approx") and s.get("mode") != "district"
    ]
    if suggests:
        labels = []
        for s in suggests:
            dist = s.get("district") or "上海"
            mode = s.get("mode") or ""
            tag = {
                "geocode": "地理编码",
                "baidu": "百度",
                "catalog": "名录",
                "fuzzy": "本地匹配",
            }.get(mode, mode or "匹配")
            conf = s.get("confidence")
            conf_s = f" ·置信{conf:g}" if isinstance(conf, (int, float)) and conf else ""
            addr = s.get("address") or ""
            labels.append(f"[{dist}] {s['name']} ｜ {addr}  ·{tag}{conf_s}")
        st.caption(f"共 {len(labels)} 条可选（仅展示强相关结果）")
        choice = st.selectbox("选择区位", labels, key="geo_choice")
        chosen = suggests[labels.index(choice)]
        if st.button("确认使用该地址", type="primary", use_container_width=True):
            name = chosen.get("name", "")
            addr = chosen.get("address") or f"上海市{name}"
            dist = (
                chosen.get("district")
                or st.session_state.get("search_district")
                or infer_district(addr, name, q, fallback="")
            )
            st.session_state.address = addr
            st.session_state.community = name
            st.session_state.district = dist
            st.session_state.lng = chosen["lng"]
            st.session_state.lat = chosen["lat"]
            st.session_state.search_mode = chosen.get("mode") or st.session_state.get(
                "search_mode", "fuzzy"
            )
            st.session_state.geo_confirmed = True
            st.rerun()

    if st.session_state.geo_confirmed:
        st.markdown(
            f"**已选** {st.session_state.get('community')}  \n"
            f"行政区：**{st.session_state.get('district') or '未识别'}**  \n"
            f"{st.session_state.get('address')}  \n"
            f"`{st.session_state.get('lng'):.5f}, {st.session_state.get('lat'):.5f}`"
        )


def _collect_input() -> SimplePricingInput:
    st.markdown('<div class="section-label">产品条件</div>', unsafe_allow_html=True)
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    with r1c1:
        layout_opts = list(LAYOUT_OPTIONS) or ["LOFT", "开间STUDIO", "一室一厅", "两室一厅"]
        layout_default = normalize_layout(str(st.session_state.get("layout", "一室一厅") or "一室一厅"))
        if layout_default not in layout_opts:
            layout_default = "一室一厅" if "一室一厅" in layout_opts else layout_opts[0]
        layout = st.selectbox("户型", layout_opts, index=layout_opts.index(layout_default))
        area = st.number_input("套内面积㎡", 10.0, 120.0, float(st.session_state.get("area", 30)), 1.0)
        st.caption("输入口径：套内面积（非建筑面积）")
    with r1c2:
        decoration = st.radio(
            "装修",
            DECORATION_SIMPLE,
            index=0 if st.session_state.get("decoration", "精装") == "精装" else 1,
            horizontal=True,
        )
        metro_band = st.selectbox(
            "地铁距离",
            METRO_OPTIONS,
            index=METRO_OPTIONS.index(st.session_state.get("metro_band", "500-800m"))
            if st.session_state.get("metro_band", "500-800m") in METRO_OPTIONS
            else 1,
        )
    with r1c3:
        building_age = st.number_input("楼龄（年）", 0, 50, int(st.session_state.get("building_age", 8)))
        has_elevator = st.checkbox("电梯房", value=bool(st.session_state.get("has_elevator", True)))
        floor = st.selectbox(
            "楼层",
            FLOOR_OPTIONS,
            index=FLOOR_OPTIONS.index(st.session_state.get("floor", "中高楼层"))
            if st.session_state.get("floor", "中高楼层") in FLOOR_OPTIONS
            else 0,
        )
    with r1c4:
        orientation = st.selectbox(
            "朝向",
            ORIENT_OPTIONS,
            index=ORIENT_OPTIONS.index(st.session_state.get("orientation", "南向"))
            if st.session_state.get("orientation", "南向") in ORIENT_OPTIONS
            else 1,
        )
        amenity = st.selectbox(
            "周边配套",
            AMENITY_OPTIONS,
            index=AMENITY_OPTIONS.index(st.session_state.get("amenity", "一般配套"))
            if st.session_state.get("amenity", "一般配套") in AMENITY_OPTIONS
            else 1,
        )

    st.markdown('<div class="section-label">六大因子用户权重（×调研系数）</div>', unsafe_allow_html=True)
    st.caption("生效系数 = 1 + (系统系数−1)×权重；1.0=调研全幅")
    uw = dict(st.session_state.get("user_weights") or DEFAULT_USER_WEIGHTS)
    cols = st.columns(6)
    for col, (key, name, w) in zip(cols, USER_ADJUSTABLE_FACTORS):
        with col:
            uw[key] = st.slider(name, 0.0, 2.0, float(uw.get(key, 1.0)), 0.1, help=f"调研权重约{w*100:.0f}%")
    st.session_state.user_weights = uw

    return SimplePricingInput(
        city="上海",
        district=str(st.session_state.get("district", "")),
        community=str(st.session_state.get("community", "")),
        address=str(st.session_state.get("address", "")),
        lng=st.session_state.get("lng"),
        lat=st.session_state.get("lat"),
        layout=layout,
        area=float(area),
        decoration=decoration,
        building_age=int(building_age),
        metro_band=metro_band,
        floor=floor,
        orientation=orientation,
        has_elevator=has_elevator,
        amenity=amenity,
        private_bath=True,
        user_weights=uw,
        search_mode=str(st.session_state.get("search_mode", "")),
    )


def _render_outputs(pred: PricingPrediction, ak: str) -> None:
    st.markdown('<div class="section-label">输出结果</div>', unsafe_allow_html=True)
    as_of = getattr(pred, "data_as_of", "") or ""
    meta = f"租金样本截至 {as_of}" if as_of else "租金样本时点未标注"
    st.markdown(f'<p class="out-meta">{meta} · 口径：套内面积</p>', unsafe_allow_html=True)

    delta = f"{pred.total_premium_pct:+g}% 相对基准"
    st.markdown(
        f"""
<div class="metric-row">
  <div class="metric-cell"><div class="metric-label">预测最低</div><div class="metric-value">¥{round(pred.rent_min):,}</div></div>
  <div class="metric-cell"><div class="metric-label">预测中位</div><div class="metric-value">¥{round(pred.rent_mid):,}</div></div>
  <div class="metric-cell"><div class="metric-label">预测最高</div><div class="metric-value">¥{round(pred.rent_max):,}</div></div>
  <div class="metric-cell"><div class="metric-label">套内单价</div><div class="metric-value">{pred.adjusted_unit_price:g}</div><div class="metric-delta">{delta}</div></div>
  <div class="metric-cell"><div class="metric-label">组合评分</div><div class="metric-value">{pred.composite_score:g}</div></div>
</div>
<p class="out-formula">{pred.formula}</p>
""",
        unsafe_allow_html=True,
    )

    trend = getattr(pred, "rent_trend", None)
    if not trend or not getattr(trend, "points", None):
        dist = (
            str(st.session_state.get("district") or "")
            or infer_district(getattr(pred, "location", ""), fallback="上海")
            or "上海"
        )
        trend = build_rent_trend(float(getattr(pred, "rent_mid", 0) or 0), dist)
    if trend and getattr(trend, "points", None):
        st.markdown('<div class="out-h">租金走势 · 查询时点 ±6 个月</div>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="out-note">历史：{trend.history_note}<br/>前瞻：{trend.forecast_note}</p>',
            unsafe_allow_html=True,
        )
        rows = trend.to_chart_rows()
        chart_df = pd.DataFrame(
            {"建议月租(元)": [r["建议月租"] for r in rows]},
            index=[r["月份"] for r in rows],
        )
        st.line_chart(chart_df)
        with st.expander("查看分月明细", expanded=False):
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if trend.disclaimer:
            st.markdown(f'<p class="out-note">{trend.disclaimer}</p>', unsafe_allow_html=True)
    else:
        st.warning("租金走势暂不可用，请重新点击「生成研判」。")

    st.markdown(
        f'<div class="out-h">附近片区租赁价格 · {int(RADIUS_2KM)}m 内</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="out-note">均价/单价已统一为套内㎡；原建筑面积挂牌已按 ×0.78 折算。</p>',
        unsafe_allow_html=True,
    )
    rep = pred.area_report
    if rep and rep.sample_count:
        o, a, r = rep.overall, rep.apartment, rep.residential

        def _stat_html(title: str, d: dict) -> str:
            if not d.get("count"):
                return (
                    f'<div class="stat-block"><div class="stat-title">{title}</div>'
                    f'<div class="stat-body">暂无样本</div></div>'
                )
            return (
                f'<div class="stat-block"><div class="stat-title">{title}</div>'
                f'<div class="stat-body">样本 {d.get("count")}　中位 ¥{d.get("median_rent","—")}<br/>'
                f'均价 ¥{d.get("avg_rent","—")}　套内单价 {d.get("avg_unit","—")} 元/㎡<br/>'
                f'<span style="color:#7a7268">区间 ¥{d.get("min_rent","—")}–{d.get("max_rent","—")}</span>'
                f"</div></div>"
            )

        st.markdown(
            '<div class="stat-grid">'
            + _stat_html("综合", o)
            + _stat_html("集中式公寓", a)
            + _stat_html("分散式民居", r)
            + "</div>",
            unsafe_allow_html=True,
        )
        lines = "".join(f"<li>{line}</li>" for line in (rep.analysis_lines or []))
        if lines:
            st.markdown(f'<ul class="analysis-list">{lines}</ul>', unsafe_allow_html=True)
    else:
        st.warning("2km 内暂无样本，请确认定位。")

    left, right = st.columns([1.08, 0.92], gap="large")
    with left:
        st.markdown('<div class="out-h">客户画像</div>', unsafe_allow_html=True)
        p = pred.persona
        st.markdown(
            f"""
<table class="kv">
  <tr><th>主力客群</th><td>{p.primary}</td></tr>
  <tr><th>职业</th><td>{p.occupation}</td></tr>
  <tr><th>支付能力</th><td>{p.affordability}</td></tr>
  <tr><th>诉求</th><td>{'；'.join(p.needs)}</td></tr>
</table>
""",
            unsafe_allow_html=True,
        )
        st.markdown('<div class="out-h">六大溢价因子</div>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "排名": str(f.rank) if f.rank is not None else "—",
                        "因子": f.name,
                        "调研权重": f"{f.weight_pct:g}%" if f.weight_pct else str(f.weight),
                        "系统系数": f.system_coef,
                        "用户权重": f.user_weight,
                        "生效系数": f.coefficient,
                        "说明": f.reason,
                    }
                    for f in pred.premium_factors
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown('<div class="out-h">租赁策略</div>', unsafe_allow_html=True)
        s = pred.strategy
        st.markdown(
            f"""
<ol class="strategy-ol">
  <li>租期 — {s.lease_term}</li>
  <li>付款 — {s.payment}</li>
  <li>定价 — {s.pricing}</li>
  <li>差异化 — {s.differentiation}</li>
</ol>
""",
            unsafe_allow_html=True,
        )

    with right:
        st.markdown('<div class="out-h">电子地图</div>', unsafe_allow_html=True)
        st.markdown('<p class="out-note">目标点与 2km 内竞品</p>', unsafe_allow_html=True)
        if pred.map_points:
            html = render_baidu_map_html(
                pred.map_points[0], pred.map_points[1:], ak=ak or None, height=380
            )
            components.html(html, height=400, scrolling=True)
        else:
            st.info("锁定地址并生成后显示地图")

    st.markdown('<div class="out-h">2km 竞品明细</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="out-note">对照「套内㎡(对比用)」与输入套内面积；「原挂牌口径」区分建筑/套内。</p>',
        unsafe_allow_html=True,
    )
    comps = list(getattr(pred, "competitors", None) or [])
    near = [c for c in comps if float(getattr(c, "distance_m", 1e9) or 1e9) <= RADIUS_2KM]
    st.markdown(
        f'<p class="out-meta">共 {len(near)} 条（2km 内） / 原始返回 {len(comps)} 条</p>',
        unsafe_allow_html=True,
    )
    if near:
        rows = []
        for c in sorted(near, key=lambda x: float(getattr(c, "distance_m", 0) or 0)):
            listed_basis = getattr(c, "area_listed_basis", None) or (
                "建筑" if "建筑" in str(getattr(c, "area_basis", "")) else "套内"
            )
            listed = getattr(c, "area_listed", None) or getattr(c, "area", 0)
            interior = getattr(c, "area", 0)
            try:
                basis_label = c.area_basis_label  # type: ignore[attr-defined]
            except Exception:
                basis_label = (
                    f"原建筑{listed:g}㎡→套内{interior:g}㎡"
                    if listed_basis == "建筑"
                    else f"原套内{interior:g}㎡"
                )
            rows.append(
                {
                    "距离m": int(float(c.distance_m)),
                    "类型": getattr(c, "segment", ""),
                    "所在小区/项目": getattr(c, "community", None) or c.name,
                    "房源名称": c.name,
                    "户型": getattr(c, "layout", ""),
                    "原挂牌口径": listed_basis,
                    "原挂牌面积㎡": listed,
                    "套内㎡(对比用)": interior,
                    "面积说明": basis_label,
                    "月租": round(float(c.price)),
                    "套内单价": getattr(c, "unit_price", ""),
                    "数据截至": getattr(c, "as_of", "") or "—",
                    "来源": getattr(c, "source", ""),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        far_n = len(comps) - len(near)
        if far_n > 0:
            st.caption(f"已排除 {far_n} 条超出2km的样本")
    else:
        st.warning("无2km内竞品。请确认已锁定地址并重新点击「生成研判」。")

    with st.expander("模型说明"):
        for n in pred.notes:
            st.write(f"- {n}")

    st.download_button(
        "下载研判 JSON",
        data=json.dumps({"output": pred.to_dict()}, ensure_ascii=False, indent=2),
        file_name="上海公寓租金研判.json",
        mime="application/json",
    )



def main() -> None:
    _init()
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    ak = _sidebar()
    st.markdown(
        """
<div class="hero">
  <div class="hero-kicker">2km Market · Top6 Multiplicative Factors</div>
  <h1 class="hero-title">上海公寓租金研判</h1>
  <div class="hero-sub">严格分析搜索点 2km 内公寓与民居租金；按地铁/装修/房龄/面积户型/楼层朝向/配套六大因子乘法定价。</div>
</div>
""",
        unsafe_allow_html=True,
    )
    _search_address(ak)
    st.divider()
    inp = _collect_input()
    can_run = bool(st.session_state.get("geo_confirmed"))
    clicked = st.button(
        "生成研判",
        type="primary",
        use_container_width=True,
        disabled=not can_run,
        key="btn_generate",
    )
    if not can_run:
        st.caption("请先检索并确认地址后，再生成研判。")

    def _pred_is_stale(pred: object) -> bool:
        rep = getattr(pred, "area_report", None)
        if rep is not None and not hasattr(rep, "area_basis_note"):
            return True
        # 无租金走势曲线的旧缓存也要重算
        if not getattr(pred, "rent_trend", None):
            return True
        return False

    if clicked:
        if not can_run:
            st.error("尚未锁定区位，请先确认地址。")
        else:
            try:
                with st.spinner("正在分析 2km 片区并测算租金…"):
                    st.session_state.last_pred = RentPredictor().predict(inp)
                st.success("研判完成")
            except Exception as exc:
                st.exception(exc)

    # 旧版缓存：有区位则自动重算，不再 stop 阻断按钮
    if "last_pred" in st.session_state and _pred_is_stale(st.session_state.last_pred):
        if can_run:
            try:
                st.session_state.last_pred = RentPredictor().predict(inp)
            except Exception as exc:
                del st.session_state.last_pred
                st.error(f"自动刷新旧结果失败：{exc}")
        else:
            del st.session_state.last_pred

    if "last_pred" in st.session_state:
        st.divider()
        _render_outputs(st.session_state.last_pred, ak)


if __name__ == "__main__":
    main()
