from app.ai.risk.rules import RULE_SETS
from app.core.enums import RiskSignal


def assess_risk(drill: str, metrics: dict, ruleset: dict | None = None) -> dict:
    ruleset = ruleset or RULE_SETS[drill]; triggered = []; levels = []
    for metric, (moderate, high) in ruleset["rules"].items():
        item = metrics.get(metric)
        if not item or item.get("value") is None: continue
        value = abs(item["value"]); classification = "HIGH" if value >= high else ("MODERATE" if value >= moderate else "LOW")
        levels.append(classification); triggered.append({"metric": metric, "value": value, "classification": classification})
    if not levels: signal = RiskSignal.INSUFFICIENT_DATA
    elif "HIGH" in levels: signal = RiskSignal.HIGH
    elif "MODERATE" in levels: signal = RiskSignal.MODERATE
    else: signal = RiskSignal.LOW
    scores = {"LOW": .2, "MODERATE": .5, "HIGH": .85, "INSUFFICIENT_DATA": None}
    confidence_values = [m.get("confidence", 0) for m in metrics.values() if m.get("value") is not None]
    return {"rule_set_version": ruleset["version"], "risk_signal": signal, "risk_score": scores[signal], "triggered_rules": triggered, "confidence": sum(confidence_values) / len(confidence_values) if confidence_values else None}
