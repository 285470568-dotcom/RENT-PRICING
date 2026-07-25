"""上海独卫公寓租金研判 —— 2km 片区分析 + 六大因子乘法定价。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pricing.baidu_map import BaiduMapClient, get_ak, render_baidu_map_html
from pricing.competitors import RADIUS_2KM, load_competitors
from pricing.predictor import RentPredictor
from pricing.shanghai_market import (
    AMENITY_OPTIONS,
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
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Noto+Serif+SC:wght@500;600&family=Outfit:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: Outfit, "Noto Serif SC", serif !important; color:#1a1814; }
.stApp { background: linear-gradient(180deg,#f7f4ee 0%,#f3efe6 100%); }
h1,h2,h3,.hero-title { font-family: "Cormorant Garamond","Noto Serif SC",serif !important; font-weight:600 !important; color:#141210 !important; }
.hero { padding:0.2rem 0 1rem; border-bottom:1px solid rgba(40,32,22,.12); margin-bottom:1rem; }
.hero-kicker { font-size:.72rem; letter-spacing:.22em; text-transform:uppercase; color:#6e6456; }
.hero-title { font-size:2.2rem !important; margin:0 !important; }
.hero-sub { margin-top:.4rem; color:#5c554a; font-size:.92rem; max-width:46rem; }
.section-label { font-size:.68rem; letter-spacing:.18em; text-transform:uppercase; color:#7a7062; margin:.5rem 0 .55rem; }
div[data-testid="stSidebar"] { background:#161411; }
div[data-testid="stSidebar"] * { color:#efe8dc !important; }
.stButton > button { border-radius:0 !important; background:#1c1915 !important; color:#f4efe6 !important; border:1px solid #1c1915 !important; letter-spacing:.06em; }
[data-testid="stMetricValue"] { font-family:"Cormorant Garamond","Noto Serif SC",serif !important; }
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
        ak_input = st.text_input("百度地图 AK（可选）", value=get_ak(), type="password")
        if ak_input:
            st.session_state["BAIDU_MAP_AK_RUNTIME"] = ak_input
            os.environ["BAIDU_MAP_AK"] = ak_input
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
    return st.session_state.get("BAIDU_MAP_AK_RUNTIME") or get_ak()


def _search_address(ak: str) -> None:
    st.markdown('<div class="section-label">区位检索</div>', unsafe_allow_html=True)
    q = st.text_input(
        "地址关键词",
        value=st.session_state.get("search_q", "宜山路"),
        key="search_q",
        placeholder="任意关键词：路名/小区/机构/商圈",
        help="输入后点检索，将在「选择区位」列出上海匹配的多处地址供选择",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("检索地址", use_container_width=True):
            # 仅在主动检索时解除旧锁定
            st.session_state.geo_confirmed = False
            prefer = st.session_state.get("search_prefer", "")
            client = BaiduMapClient(ak=ak if "模糊" not in prefer or "自动" in prefer else "")
            limit = 30
            if prefer.startswith("仅模糊"):
                hits = client._fuzzy_suggest(q, limit=limit)
                for h in hits:
                    h["mode"] = h.get("mode") or "fuzzy"
                mode = "fuzzy"
            elif prefer.startswith("仅百度"):
                if not ak:
                    hits, mode = client.suggest(q, limit=limit)
                    st.warning("无 AK，已用本地/模糊匹配")
                else:
                    try:
                        place = client._baidu_place_search(q, limit=limit)
                        sug = client._baidu_suggest(q, limit=limit)
                        from pricing.baidu_map import _merge_places

                        hits = _merge_places(place + sug, limit=limit)
                        for h in hits:
                            h["mode"] = "baidu"
                        mode = "baidu"
                        if not hits:
                            hits, mode = client.suggest(q, limit=limit)
                            st.info("百度无结果，已本地补全")
                    except Exception as exc:
                        hits = client._fuzzy_suggest(q, limit=limit)
                        for h in hits:
                            h["mode"] = h.get("mode") or "fuzzy"
                        mode = "fuzzy"
                        st.warning(f"百度失败，已本地/模糊：{exc}")
            else:
                hits, mode = client.suggest(q, limit=limit)
            st.session_state.suggests = hits
            st.session_state.search_mode = mode
            if hits:
                st.success(f"找到 {len(hits)} 处上海地址，请在下方选择")
            else:
                st.error("无结果")
    with c2:
        if st.session_state.geo_confirmed:
            st.success("已锁定 · 将分析该点 2km 片区")
        else:
            st.caption(f"模式：{st.session_state.get('search_mode') or '—'}，请确认地址")

    suggests = st.session_state.suggests or []
    if suggests:
        labels = []
        for s in suggests:
            dist = s.get("district") or "上海"
            mode = s.get("mode") or ""
            if mode == "baidu":
                tag = "百度"
            elif mode == "catalog":
                tag = "名录"
            elif mode == "district" or s.get("approx"):
                tag = "分区候选"
            elif s.get("synthetic"):
                tag = "按输入定位"
            else:
                tag = "模糊"
            addr = s.get("address") or ""
            labels.append(f"[{dist}] {s['name']} ｜ {addr}  ·{tag}")
        st.caption(f"共 {len(labels)} 条上海地址可选，请选择后确认")
        choice = st.selectbox("选择区位", labels, key="geo_choice")
        chosen = suggests[labels.index(choice)]
        if st.button("确认使用该地址", type="primary", use_container_width=True):
            name = chosen.get("name", "")
            addr = chosen.get("address") or f"上海市{name}"
            dist = (
                chosen.get("district")
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
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("预测最低", f"¥{round(pred.rent_min):,}")
    m2.metric("预测中位", f"¥{round(pred.rent_mid):,}")
    m3.metric("预测最高", f"¥{round(pred.rent_max):,}")
    m4.metric("套内单价", f"{pred.adjusted_unit_price}", delta=f"{pred.total_premium_pct:+g}%")
    m5.metric("组合评分", f"{pred.composite_score}")
    st.caption(pred.formula)

    # 2km 片区分析（核心新增）
    st.markdown(f"#### 附近片区租赁价格（{int(RADIUS_2KM)}m 内）")
    st.caption(
        "面积口径：本项目输入为【套内面积】；下列均价/单价均已统一到【套内㎡】。"
        "若竞品原挂牌为建筑面积，已按 ×0.78 折算套内后再参与对比。"
    )
    rep = pred.area_report
    if rep and rep.sample_count:
        note = getattr(rep, "area_basis_note", "") or ""
        if note:
            st.info(note)
        c1, c2, c3 = st.columns(3)
        o, a, r = rep.overall, rep.apartment, rep.residential
        with c1:
            st.markdown("**综合（套内口径）**")
            st.write(
                f"样本 {o.get('count',0)}｜中位 ¥{o.get('median_rent','—')}｜"
                f"均价 ¥{o.get('avg_rent','—')}｜套内单价 {o.get('avg_unit','—')} 元/㎡"
            )
            st.caption(f"区间 ¥{o.get('min_rent','—')}–{o.get('max_rent','—')}")
        with c2:
            st.markdown("**集中式公寓（套内口径）**")
            if a.get("count"):
                st.write(
                    f"样本 {a['count']}｜中位 ¥{a['median_rent']}｜均价 ¥{a['avg_rent']}｜"
                    f"套内单价 {a.get('avg_unit')} 元/㎡"
                )
                st.caption(f"区间 ¥{a['min_rent']}–{a['max_rent']}")
            else:
                st.write("暂无公寓样本")
        with c3:
            st.markdown("**分散式民居（套内口径）**")
            if r.get("count"):
                st.write(
                    f"样本 {r['count']}｜中位 ¥{r['median_rent']}｜均价 ¥{r['avg_rent']}｜"
                    f"套内单价 {r.get('avg_unit')} 元/㎡"
                )
                st.caption(f"区间 ¥{r['min_rent']}–{r['max_rent']}｜民居多为建筑面积已折算")
            else:
                st.write("暂无民居样本")
        for line in rep.analysis_lines:
            st.markdown(f"- {line}")
    else:
        st.warning("2km 内暂无样本，请确认定位。")

    left, right = st.columns([1.05, 0.95])
    with left:
        st.markdown("#### 客户画像")
        p = pred.persona
        st.markdown(
            f"| | |\n|--|--|\n| 主力客群 | {p.primary} |\n| 职业 | {p.occupation} |\n"
            f"| 支付能力 | {p.affordability} |\n| 诉求 | {'；'.join(p.needs)} |"
        )
        st.markdown("#### 六大溢价因子（乘法）")
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
        st.markdown("#### 租赁策略")
        s = pred.strategy
        st.markdown(
            f"1. **租期**：{s.lease_term}\n2. **付款**：{s.payment}\n"
            f"3. **定价**：{s.pricing}\n4. **差异化**：{s.differentiation}"
        )

    with right:
        st.markdown("#### 电子地图（目标+2km竞品）")
        if pred.map_points:
            html = render_baidu_map_html(
                pred.map_points[0], pred.map_points[1:], ak=ak or None, height=380
            )
            components.html(html, height=400, scrolling=True)
        else:
            st.info("锁定地址并生成后显示地图")

    # 竞品明细单独全宽，避免挤在右栏看不到
    st.markdown("#### 2km 竞品明细（公寓+民居）")
    st.caption(
        "「原挂牌口径」标明建筑/套内；请用「套内㎡(对比用)」与输入套内面积对照。"
    )
    comps = list(getattr(pred, "competitors", None) or [])
    near = [c for c in comps if float(getattr(c, "distance_m", 1e9) or 1e9) <= RADIUS_2KM]
    st.write(f"共 **{len(near)}** 条（2km 内） / 原始返回 {len(comps)} 条")
    if near:
        rows = []
        for c in sorted(near, key=lambda x: float(getattr(x, "distance_m", 0) or 0)):
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
        return rep is not None and not hasattr(rep, "area_basis_note")

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
