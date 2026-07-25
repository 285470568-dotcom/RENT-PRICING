"""CLI：上海公寓租金研判（2km + Top6）。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pricing.competitors import load_competitors
from pricing.predictor import RentPredictor
from pricing.simple_models import SimplePricingInput


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=Path, default=Path("data/sample_shanghai.json"))
    parser.add_argument("-o", "--output", type=Path, default=Path("outputs/上海公寓租金研判.json"))
    args = parser.parse_args()

    load_competitors()
    inp = SimplePricingInput.from_dict(json.loads(args.input.read_text(encoding="utf-8")))
    pred = RentPredictor().predict(inp)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"input": inp.to_dict(), "output": pred.to_dict()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"区位: {pred.location}")
    print(f"租金: {round(pred.rent_min)} – {round(pred.rent_mid)} – {round(pred.rent_max)}")
    print(f"公式系数乘积影响: {pred.total_premium_pct:+g}%  评分:{pred.composite_score}")
    if pred.area_report:
        print(f"2km样本: {pred.area_report.sample_count}")
        for line in pred.area_report.analysis_lines:
            print(" ", line)
    print("竞品(距离):")
    for c in sorted(pred.competitors, key=lambda x: x.distance_m)[:8]:
        print(
            f"  {int(c.distance_m)}m | {c.segment} | 小区/项目:{c.community or '-'} | "
            f"{c.name} | ¥{c.price}"
        )
        assert c.distance_m <= 2000
        assert c.community or c.name
    print(f"已写入: {args.output}")


if __name__ == "__main__":
    main()
