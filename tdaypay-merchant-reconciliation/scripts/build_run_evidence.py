"""Build a privacy-conscious Markdown evidence record for one reconciliation run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def yn(value: Any) -> str:
    return "是" if value else "否"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Reconciliation JSON")
    parser.add_argument("--verification", required=True, help="Verification JSON")
    parser.add_argument("--output", required=True, help="Markdown evidence output")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    verification = json.loads(Path(args.verification).read_text(encoding="utf-8"))
    if verification.get("Verification") != "PASS":
        raise ValueError("verification report is not PASS")

    meta = data["meta"]
    summary = data["summary"]
    source_suffix = Path(str(meta.get("source_file", ""))).suffix.lower() or "未知"
    order_job_count = len(meta.get("order_exports", []))
    flow_job_count = len(meta.get("flow_exports", []))

    counts = [
        ("我方成功订单", summary["ours_count"]),
        ("TDayPay 成功订单", summary["tdaypay_success_count"]),
        ("双方匹配订单", summary["matched_count"]),
        ("我方有、TDayPay 无", summary["ours_only_count"]),
        ("TDayPay 有、我方无", summary["tdaypay_only_count"]),
        ("字段差异订单", summary["field_discrepancy_count"]),
        ("TDayPay 明确未结算", summary["unsettled_count"]),
        ("结算状态待核实", summary.get("settlement_unknown_count", 0)),
        ("未查到指定流水", summary["missing_flow_count"]),
        ("流水观察期未结束", summary.get("pending_flow_observation_count", 0)),
        ("指定口径流水", summary["flow_raw_count"]),
    ]

    lines = [
        "# TDayPay 商户对账运行证据",
        "",
        "> 本记录仅保留范围、计数和校验结论，不包含完整订单号、手机号、邮箱、账户信息、凭证或临时下载链接。",
        "",
        "## 运行范围",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| 源文件类型 | {source_suffix} |",
        f"| 币种 | {meta['currency']} |",
        f"| 订单日期 | {meta['period_start']} 至 {meta['period_end']}（含） |",
        f"| 业务时区 | {meta['business_time_zone']} |",
        f"| 查询完成时间（UTC） | {meta.get('as_of_utc', '')} |",
        f"| 流水口径 | {meta['flow_funding_domain']} + {meta['flow_account_type']} |",
        f"| 流水实际查询日期 | {meta['flow_period_start']} 至 {meta['flow_period_end']}（含） |",
        f"| 流水目标截止日期 | {meta.get('flow_target_end', meta['flow_period_end'])} |",
        f"| 三日观察窗口全部结束 | {yn(meta.get('flow_window_complete', False))} |",
        f"| 订单导出任务数 | {order_job_count} |",
        f"| 流水导出任务数 | {flow_job_count} |",
        "",
        "## 对账结果",
        "",
        "| 指标 | 数量 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {label} | {value} |" for label, value in counts)
    lines.extend([
        "",
        "## 文件校验",
        "",
        "| 检查项 | 结果 |",
        "| --- | --- |",
        f"| 综合校验 | {verification['Verification']} |",
        f"| 输出文件数 | {len(verification.get('files', []))} |",
        f"| 非空单元格均为文本 | {yn(verification.get('all_nonblank_cells_text'))} |",
        f"| 公式错误 | {verification.get('formula_errors', '')} |",
        f"| 外部链接 | {verification.get('external_links', '')} |",
        "",
        "## 权限与数据确认",
        "",
        "- 数据范围：当前已认证商户、指定币种及指定日期；未扩大原有数据权限。",
        "- 明细文件：仅保存在本次受控输出目录，由业务负责人按公司权限规则共享和归档。",
        "- 本记录：已去除完整订单号、联系信息、账户信息、访问凭证和临时下载链接，可用于效果留档。",
        "",
        "## 独立业务验证",
        "",
        "状态：待一名未参与制作、且与业务相关的验证人完成。作者自测或自动校验不能填写为独立验证。",
        "",
        "完成验证后，将验证记录与本文件一同归档。验证字段及要求见 `references/competition-evidence.md`。",
        "",
    ])

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
