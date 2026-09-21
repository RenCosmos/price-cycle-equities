from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

from .cycle import (
    PHASE_DIRECTIONS,
    PHASE_FAMILIES,
    PHASES,
    SOURCE_PHASE_FAMILIES,
)
from .models import (
    DataSet,
    FeatureRow,
    ObservedEvent,
    PhaseAssessment,
    json_value,
)
from .market_rules import RuleResolutionStatus, rules_at
from .parameters import ResearchParameters


SCHEMA_VERSION = "1.0.1"
ENGINE_VERSION = "0.1.1"
STRATEGY_SPEC_VERSION = "1.0.1-draft"


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _config_hash(parameters: ResearchParameters) -> str:
    payload = json.dumps(
        parameters.values(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _feature_value(value: float | None) -> float | None:
    return None if value is None else round(value, 8)


def _technical_snapshot(row: FeatureRow) -> dict[str, object]:
    return {
        "latest_bar_date": row.bar.session_date.isoformat(),
        "close": row.bar.close,
        "ema10": _feature_value(row.ema10),
        "ema20": _feature_value(row.ema20),
        "sma50": _feature_value(row.sma50),
        "sma200": _feature_value(row.sma200),
        "atr14": _feature_value(row.atr14),
        "volume_ratio": _feature_value(row.volume_ratio),
        "range_ratio": _feature_value(row.range_ratio),
        "distance_ema20_atr": _feature_value(row.distance_ema20_atr),
        "relative_strength_20": _feature_value(row.relative_strength_20),
        "relative_strength_60": _feature_value(row.relative_strength_60),
    }


def _evidence_json(items: tuple[object, ...]) -> list[object]:
    return [json_value(item) for item in items]


def _phase_json(assessment: PhaseAssessment) -> dict[str, object]:
    return {
        "phase": assessment.phase,
        "phase_family": PHASE_FAMILIES[assessment.phase],
        "directional_variant": PHASE_DIRECTIONS[assessment.phase],
        "score": round(assessment.score, 6),
        "confidence": assessment.confidence,
        "score_is_probability": False,
        "evidence_for": _evidence_json(assessment.evidence_for),
        "evidence_against": _evidence_json(assessment.evidence_against),
        "unknowns": _evidence_json(assessment.unknowns),
    }


def _canslim_unknowns(latest: FeatureRow) -> dict[str, dict[str, object]]:
    return {
        "C": {
            "status": "UNKNOWN",
            "reason": "No point-in-time quarterly EPS or sales data was supplied.",
        },
        "A": {
            "status": "UNKNOWN",
            "reason": "No point-in-time annual earnings history was supplied.",
        },
        "N": {
            "status": "UNKNOWN",
            "reason": "No dated catalyst evidence was supplied; price alone is insufficient.",
        },
        "S": {
            "status": "UNKNOWN",
            "reason": "OHLCV is available, but share supply and complete demand evidence are not.",
        },
        "L": {
            "status": "UNKNOWN",
            "reason": (
                "Relative performance is observed but no industry-universe leadership rank exists."
                if latest.relative_strength_20 is not None
                else "No benchmark-aligned relative performance was available."
            ),
            "observed_relative_strength_20": _feature_value(
                latest.relative_strength_20
            ),
        },
        "I": {
            "status": "UNKNOWN",
            "reason": "No point-in-time institutional sponsorship data was supplied.",
        },
        "M": {
            "status": "UNKNOWN",
            "reason": "No independently assessed market-cycle evidence was supplied.",
        },
    }


def build_report(
    *,
    dataset: DataSet,
    diagnostics: dict[str, object],
    features: tuple[FeatureRow, ...],
    assessments: tuple[PhaseAssessment, ...],
    events: tuple[ObservedEvent, ...],
    parameters: ResearchParameters,
    input_filename: str,
    input_sha256: str,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    if not features:
        raise ValueError("Cannot build a report without features")
    generated = generated_at or datetime.now(timezone.utc)
    if generated.tzinfo is None:
        raise ValueError("generated_at must include a timezone")

    latest = features[-1]
    market_rules = rules_at(
        market=dataset.market,
        as_of=dataset.as_of,
        venue=dataset.venue,
        segment=dataset.segment,
        security_type=dataset.security_type,
    )
    calendar_days_stale = (dataset.as_of - latest.bar.session_date).days
    warnings: list[str] = []
    if diagnostics.get("input_reordered"):
        warnings.append("INPUT_ROWS_REORDERED")
    if diagnostics.get("instrument_id_is_fallback"):
        warnings.append("FALLBACK_INSTRUMENT_ID")
    if diagnostics.get("excluded_after_as_of"):
        warnings.append("ROWS_AFTER_AS_OF_EXCLUDED")
    if diagnostics.get("excluded_not_yet_known"):
        warnings.append("ROWS_NOT_YET_KNOWN_EXCLUDED")
    if calendar_days_stale > 0:
        warnings.append("LATEST_BAR_PRECEDES_AS_OF")
    if len(dataset.bars) < parameters.sma_long_period:
        warnings.append("SMA200_WARMUP_INCOMPLETE")
    if not dataset.benchmark_bars:
        warnings.append("BENCHMARK_NOT_SUPPLIED")
    if dataset.price_basis.value != "raw":
        warnings.append("ADJUSTED_PRICE_POINT_IN_TIME_RISK")
    if market_rules.status is RuleResolutionStatus.PARTIAL:
        warnings.append("MARKET_RULES_PARTIAL")
    elif market_rules.status is RuleResolutionStatus.UNKNOWN:
        warnings.append("MARKET_RULES_UNKNOWN")

    data_quality_status = "OK" if not warnings else "PARTIAL"
    supported_assessments = tuple(
        assessment
        for assessment in assessments
        if assessment.confidence in {"LOW", "MEDIUM", "HIGH"}
        and assessment.score > 0
    )
    top = (
        max(supported_assessments, key=lambda assessment: assessment.score)
        if supported_assessments
        else None
    )
    signal_time = events[-1].session_date.isoformat() if events else None
    config_hash = _config_hash(parameters)
    missing_capabilities = [
        "point_in_time_fundamentals",
        "institutional_sponsorship",
        "broker_execution_rules",
        "live_instrument_trading_state",
    ]
    if market_rules.status is not RuleResolutionStatus.RESOLVED:
        missing_capabilities.append("fully_resolved_dated_market_rule_snapshot")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated.astimezone(timezone.utc).isoformat(),
        "as_of": dataset.as_of.isoformat(),
        "instrument": {
            "instrument_id": dataset.instrument_id,
            "symbol": dataset.symbol,
            "market": dataset.market.value,
            "venue": dataset.venue,
            "segment": dataset.segment,
            "security_type": dataset.security_type,
            "price_basis": dataset.price_basis.value,
            "source": dataset.source,
            "input_filename": input_filename,
            "input_sha256": input_sha256,
        },
        "market_context": {
            "benchmark_symbol": dataset.benchmark_symbol,
            "technical_snapshot": _technical_snapshot(latest),
            "market_rules_status": market_rules.status.value,
            "market_rules": json_value(market_rules),
            "execution_ready": market_rules.execution_ready,
        },
        "data_quality": {
            "status": data_quality_status,
            "rows_read": diagnostics.get("input_rows"),
            "rows_used": len(dataset.bars),
            "first_bar_date": dataset.bars[0].session_date.isoformat(),
            "latest_bar_date": latest.bar.session_date.isoformat(),
            "future_rows_ignored": diagnostics.get("excluded_after_as_of", 0),
            "not_yet_known_rows_ignored": diagnostics.get(
                "excluded_not_yet_known", 0
            ),
            "calendar_days_stale": calendar_days_stale,
            "warnings": warnings,
            "missing_capabilities": missing_capabilities,
        },
        "phase_taxonomy": {
            "model": "six_source_families_eight_directional_candidates",
            "source_families": list(SOURCE_PHASE_FAMILIES),
            "source_family_count": len(SOURCE_PHASE_FAMILIES),
            "directional_candidate_count": len(PHASES),
            "provenance": "author_interpretation",
        },
        "candidate_phases": [_phase_json(item) for item in assessments],
        "observed_events": [json_value(event) for event in events],
        "canslim": _canslim_unknowns(latest),
        "trade_plan": {
            "status": "conditional",
            "plan_type": "conditional_research_plan",
            "is_order": False,
            "entry_condition": [
                "Require manual confirmation of the structural pivot and current market rules."
            ],
            "invalidation_condition": [
                "UNKNOWN: no validated structural invalidation price was derived."
            ],
            "risk_notes": [
                "No position size is calculated without account risk and a validated invalidation price.",
                "Execution constraints and fill availability are UNKNOWN.",
            ],
            "position_size": "UNKNOWN",
            "signal_time": signal_time,
            "decision_time": None,
            "order_time": None,
            "eligible_time": None,
            "fill_time": None,
        },
        "provenance": [
            {
                "item": "cycle_evidence_engine",
                "provenance": "author_interpretation",
                "note": "Experimental evidence classifier; phase score is not a probability.",
            },
            *parameters.manifest(),
        ],
        "versions": {
            "skill_version": ENGINE_VERSION,
            "strategy_spec_version": STRATEGY_SPEC_VERSION,
            "engine_version": ENGINE_VERSION,
            "data_schema_version": SCHEMA_VERSION,
            "rulebook_version": market_rules.rule_version,
            "execution_model_version": "none",
            "config_hash": config_hash,
            "data_snapshot_id": input_sha256,
        },
        "_summary": {
            "status": "SUPPORTED_CANDIDATE" if top else "NO_SUPPORTED_PHASE",
            "top_phase": top.phase if top else "UNKNOWN",
            "top_confidence": top.confidence if top else "UNKNOWN",
            "top_score": round(top.score, 6) if top else None,
        },
    }


def _fmt(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _evidence_line(item: dict[str, object]) -> str:
    rule_id = item.get("rule_id", "UNKNOWN")
    status = item.get("status", "UNKNOWN")
    message = item.get("message", "")
    provenance = item.get("provenance", "UNKNOWN")
    return f"`{rule_id}` [{status}; {provenance}] {message}"


def render_markdown(report: dict[str, object]) -> str:
    instrument = report["instrument"]
    quality = report["data_quality"]
    context = report["market_context"]
    summary = report["_summary"]
    phases = report["candidate_phases"]
    canslim = report["canslim"]
    plan = report["trade_plan"]
    if summary["status"] == "SUPPORTED_CANDIDATE":
        conclusion = (
            f"当前证据最支持 **{summary['top_phase']}**，"
            f"置信度为 **{summary['top_confidence']}**，"
            f"证据分数 {_fmt(summary['top_score'])}。"
            "该分数不是上涨概率，CAN SLIM 与执行信息仍不完整。"
        )
    else:
        conclusion = (
            "当前无可确认阶段：八个方向化候选均未获得正证据支持，"
            "因此结论保持 **UNKNOWN**。这不等于没有行情，只表示现有输入不足以支持阶段判断。"
        )

    lines = [
        f"# {instrument['symbol']} 价格循环研究报告",
        "",
        "## 1. 范围与免责声明",
        "",
        f"- 市场：{instrument['market']}",
        f"- 截止日期：{report['as_of']} 收盘后",
        f"- 数据来源：{instrument['source']}",
        f"- 价格口径：{instrument['price_basis']}",
        "- 本报告用于研究，不是交易订单，也不承诺收益。",
        "",
        "## 2. 一句话结论",
        "",
        conclusion,
        "",
        "## 3. 候选阶段",
        "",
        (
            "以下八行是从六个来源阶段家族展开的方向化候选；"
            "方向展开属于本项目的工程解释。"
        ),
        "",
        "| 候选阶段 | 来源阶段家族 | 方向 | 证据分数 | 置信度 | 支持 | 反证 | 未知 |",
        "|---|---|---|---:|---|---:|---:|---:|",
    ]
    for phase in phases:
        lines.append(
            "| {phase} | {family} | {direction} | {score:.3f} | {confidence} | {supports} | {against} | {unknowns} |".format(
                phase=phase["phase"],
                family=phase["phase_family"],
                direction=phase["directional_variant"],
                score=phase["score"],
                confidence=phase["confidence"],
                supports=len(phase["evidence_for"]),
                against=len(phase["evidence_against"]),
                unknowns=len(phase["unknowns"]),
            )
        )

    lines.extend(["", "### 候选阶段证据明细", ""])
    for phase in phases:
        lines.append(
            f"#### {phase['phase']}（{phase['confidence']}，{phase['score']:.3f}）"
        )
        evidence_groups = (
            ("支持", phase["evidence_for"]),
            ("反证", phase["evidence_against"]),
            ("未知", phase["unknowns"]),
        )
        for label, items in evidence_groups:
            if items:
                lines.append(f"- {label}：" + "；".join(_evidence_line(item) for item in items))
            else:
                lines.append(f"- {label}：无")
        lines.append("")

    lines.extend(
        [
            "",
            "## 4. CAN SLIM",
            "",
            "| 因素 | 状态 | 原因 |",
            "|---|---|---|",
        ]
    )
    for factor in ("C", "A", "N", "S", "L", "I", "M"):
        item = canslim[factor]
        lines.append(f"| {factor} | {item['status']} | {item['reason']} |")

    snapshot = context["technical_snapshot"]
    rule_resolution = context["market_rules"]
    rule_snapshot = rule_resolution["snapshot"]
    lines.extend(
        [
            "",
            "## 5. 市场环境",
            "",
            f"- 基准：{_fmt(context['benchmark_symbol'])}",
            f"- RS20：{_fmt(snapshot['relative_strength_20'])}",
            f"- RS60：{_fmt(snapshot['relative_strength_60'])}",
            f"- 市场规则状态：{context['market_rules_status']}",
            f"- 交易场所：{_fmt(instrument['venue'])}",
            f"- 板块：{_fmt(instrument['segment'])}",
            f"- 规则版本：{_fmt(rule_snapshot['rule_version'] if rule_snapshot else None)}",
            (
                "- 规则未知项："
                + (
                    ", ".join(rule_resolution["unknowns"])
                    if rule_resolution["unknowns"]
                    else "无"
                )
            ),
            "- 执行就绪：否",
            "",
            "## 6. 条件式计划",
            "",
            f"- 状态：{plan['status']}",
            f"- 计划类型：{plan['plan_type']}",
            "- 是否为订单：否",
            f"- 仓位：{plan['position_size']}",
        ]
    )
    for note in plan["risk_notes"]:
        lines.append(f"- 风险：{note}")

    lines.extend(
        [
            "",
            "## 7. 数据质量",
            "",
            f"- 状态：{quality['status']}",
            f"- 使用行数：{quality['rows_used']}",
            f"- 最新数据日：{quality['latest_bar_date']}",
            f"- 距截止日：{quality['calendar_days_stale']} 个自然日",
            f"- 警告：{', '.join(quality['warnings']) if quality['warnings'] else '无'}",
            "",
            "## 8. 来源与参数",
            "",
            "- 价格行为阶段来自策略事实规范；检测阈值均作为 research_parameter 输出。",
            f"- 配置哈希：{report['versions']['config_hash']}",
            f"- 数据快照：{report['versions']['data_snapshot_id']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "instrument"


def write_report_files(
    report: dict[str, object],
    *,
    output_dir: str | Path,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    instrument = report["instrument"]
    target_dir = (
        Path(output_dir)
        / str(instrument["market"]).lower()
        / _safe_component(str(instrument["symbol"]))
        / str(report["as_of"])
    )
    json_path = target_dir / "report.json"
    markdown_path = target_dir / "report.md"
    if not overwrite and (json_path.exists() or markdown_path.exists()):
        raise FileExistsError(
            f"Report already exists at {target_dir}; pass --overwrite to replace it"
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(
        {key: value for key, value in report.items() if key != "_summary"},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    markdown_text = render_markdown(report)

    temporary_paths: list[Path] = []
    try:
        for content, suffix in ((json_text, ".json"), (markdown_text, ".md")):
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=target_dir,
                suffix=suffix,
            ) as handle:
                handle.write(content)
                temporary_paths.append(Path(handle.name))
        os.replace(temporary_paths[0], json_path)
        os.replace(temporary_paths[1], markdown_path)
    finally:
        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()
    return json_path, markdown_path
