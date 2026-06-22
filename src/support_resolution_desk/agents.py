from __future__ import annotations

from typing import Any

from .models import Decision


def has_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(term in low for term in terms)


class IntakeAgent:
    name = "intake"

    def run(self, ticket: dict[str, Any]) -> Decision:
        text = ticket["message"]
        condition = ticket["item_condition"]
        tracking = ticket["tracking_status"]
        if tracking == "not_delivered":
            category = "failed_delivery"
            reason = "Tracking indicates the order was not delivered."
        elif condition == "damaged" or has_any(text, ["cracked", "broken", "dented", "unsafe"]):
            category = "damaged_item"
            reason = "Customer describes damage or safety concern."
        elif condition == "hardware_failure" or has_any(text, ["stopped working", "powers off", "failure"]):
            category = "warranty_failure"
            reason = "Customer describes a post-delivery hardware failure."
        else:
            category = "buyer_remorse"
            reason = "Customer no longer wants the item or dislikes it."
        return Decision(self.name, "classification", category, 0.86, reason)


class PolicyAgent:
    name = "policy"

    def run(self, ticket: dict[str, Any], issue: str) -> Decision:
        days = int(ticket["days_since_purchase"])
        value = float(ticket["order_value"])
        tier = ticket["customer_tier"]
        condition = ticket["item_condition"]
        tracking = ticket["tracking_status"]

        eligible = False
        reason = "No refund or replacement rule matched."
        recommended = "deny"

        if issue == "failed_delivery" and tracking == "not_delivered":
            eligible = True
            recommended = "replace" if ticket["stock_available"] else "refund"
            reason = "Failed delivery qualifies for refund or replacement."
        elif issue == "damaged_item" and days <= 30:
            eligible = True
            recommended = "replace" if ticket["stock_available"] else "refund"
            reason = "Damaged item within 30 days qualifies for refund or replacement."
        elif issue == "buyer_remorse" and days <= 14 and condition == "unopened" and value < 200:
            eligible = True
            recommended = "refund"
            reason = "Unopened accessory under $200 is refundable within 14 days."
        elif issue == "warranty_failure" and days <= 180:
            eligible = True
            recommended = "replace" if ticket["stock_available"] else "escalate"
            reason = "Verified electronics failure is covered by warranty window."

        if eligible and value > 500 and tier != "vip":
            recommended = "escalate"
            reason += " Supervisor approval is needed for refunds over $500."

        return Decision(
            self.name,
            "eligibility",
            "eligible" if eligible else "not_eligible",
            0.78,
            reason,
            {"recommended_action": recommended},
        )


class RiskAgent:
    name = "risk"

    def run(self, ticket: dict[str, Any], policy_decision: Decision) -> Decision:
        text = ticket["message"].lower()
        value = float(ticket["order_value"])
        prior = int(ticket["prior_refunds_90d"])
        tier = ticket["customer_tier"]
        triggers = []
        if any(term in text for term in ["chargeback", "legal", "posting", "publicly", "unsafe"]):
            triggers.append("escalation_language")
        if prior >= 4 and value > 300:
            triggers.append("refund_abuse_risk")
        if tier == "vip" and policy_decision.call_value == "not_eligible":
            triggers.append("vip_ambiguity")

        if "refund_abuse_risk" in triggers or "escalation_language" in triggers:
            level = "high"
            confidence = 0.88
        elif triggers:
            level = "medium"
            confidence = 0.74
        else:
            level = "low"
            confidence = 0.82

        return Decision(self.name, "risk_level", level, confidence, f"Risk triggers: {', '.join(triggers) if triggers else 'none'}.", {"triggers": triggers})


class ResolutionAgent:
    name = "resolution"

    def run(self, ticket: dict[str, Any], policy_decision: Decision, risk_decision: Decision) -> Decision:
        recommended = str(policy_decision.metadata.get("recommended_action", "deny"))
        if risk_decision.call_value == "high":
            action = "escalate"
            reason = "High risk or escalation language requires supervisor review."
            confidence = 0.84
        else:
            action = recommended
            reason = f"Following policy recommendation: {recommended}."
            confidence = 0.8
        if ticket["customer_tier"] == "vip" and action == "replace":
            reason += " VIP customer receives expedited replacement."
            confidence = 0.88
        return Decision(self.name, "final_action", action, confidence, reason)


class QaAgent:
    name = "qa"

    def run(self, ticket: dict[str, Any], decisions: list[Decision]) -> Decision:
        expected = ticket["expected"]["final_action"]
        final = next(d.call_value for d in decisions if d.agent == "resolution")
        if final == expected:
            verdict = "approved"
            confidence = 0.9
            reason = "Final action matches the expected policy outcome."
        elif final == "escalate" and ticket["expected"]["requires_escalation"]:
            verdict = "approved"
            confidence = 0.82
            reason = "Escalation is acceptable because the case has a required escalation trigger."
        else:
            verdict = "rejected"
            confidence = 0.86
            reason = f"Final action {final} does not match expected action {expected}."
        return Decision(self.name, "qa_verdict", verdict, confidence, reason)

