# 上海公寓租金研判

## 核心能力

- **2km 片区分析**：只使用搜索点 2km 内样本；输出综合 / 公寓 / 民居的中位、均价、单价与解读
- **六大因子乘法定价**（调研权重）：地铁 → 装修 → 房龄 → 面积户型 → 楼层朝向 → 配套
- 公式：`面积 × 板块基准单价 × Π(各因子生效系数)`，再与片区中位单价混合锚定
- 用户可调各因子权重；默认独卫、套内面积

## 竞品数据更新（保持最新）

1. 按模板填写 CSV：`data/inbox/competitors_template.csv`（可另存为新文件放进 `data/inbox/`）
2. 运行：

```bash
source .venv/bin/activate
python scripts/refresh_competitors.py
```

3. 主库 `data/shanghai_competitors.json` 会更新，并写入 `as_of`；界面显示「数据截至」。

## 租金走势曲线

输出结果含查询时点 **前后各 6 个月** 建议月租曲线：
- 历史：市/区租金指数回推（`data/shanghai_rent_index.json`）
- 前瞻：公开预测温和修复情景月环比推演

## 百度地图 AK（推荐预设，用户不用每次填）

密钥**不要**提交到 Git。任选一种写入后，侧栏会显示「已内置」：

1. `.streamlit/secrets.toml`（推荐）

```toml
BAIDU_MAP_AK = "你的AK"
```

2. 仓库根目录 `.baidu_ak`（单行 AK）
3. 环境变量 `BAIDU_MAP_AK`
4. Streamlit Cloud：App settings → Secrets 同上

示例文件：`.streamlit/secrets.toml.example`

## 本地运行

```bash
source .venv/bin/activate
streamlit run app.py
```

浏览器打开 http://localhost:8501

## 发布与「改完即更新」

推荐两条线，可同时用：

### A. 本机隧道（即时同步，适合联调）

电脑开着、本地 `streamlit run app.py` 在跑时，用公网隧道暴露 `8501`。  
在 Cursor 里改代码 → Streamlit 热更新 → **外网立刻就是最新版**。  
电脑休眠/关机后外网不可用。

```bash
# 示例：cloudflared 临时隧道
cloudflared tunnel --url http://localhost:8501
```

### B. Streamlit Community Cloud（7×24，适合正式分享）

1. 把本仓库推到 GitHub（公开或私有均可）
2. 打开 https://share.streamlit.io → New app → 选仓库、`main`、入口 `app.py`
3. （可选）在 App settings → Secrets 写入：

```toml
BAIDU_MAP_AK = "你的百度地图AK"
```

之后工作流：

```
Cursor 里改代码 → git commit → git push → Cloud 自动重新部署（约 1–3 分钟）
```

这样外网链接长期有效，且每次 push 后自动变成最新版。

## 依赖

见 `requirements.txt`。入口文件：`app.py`。
