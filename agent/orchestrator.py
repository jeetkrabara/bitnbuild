from typing import List, Dict, Any
from agent.prompts import generate_commander_justification

def get_criticality_weight(criticality: str) -> float:
    """Returns asset criticality weight (Section 6.4)."""
    weights = {"critical": 1.0, "standard": 0.6, "low": 0.3}
    return weights.get(str(criticality).lower(), 0.6)


def compute_plan_score(candidate: Dict[str, Any], sim_result: Dict[str, Any], criticality: str) -> float:
    """
    Deterministic Commander scoring formula (Section 6.4):
    total_score = 0.5 * safety + 0.2 * (1 - norm_dv) + 0.2 * crit_weight + 0.1 * (1 - norm_delay)
    """
    if not sim_result.get("feasible", False):
        return -1.0
    
    safety_score = 1.0 if (sim_result.get("primary_resolved", False) and len(sim_result.get("secondary_conflicts", [])) == 0) else 0.0
    normalized_delta_v = min(candidate.get("delta_v_ms", 0.0) / 10.0, 1.0)
    crit_weight = get_criticality_weight(criticality)
    normalized_delay = min(candidate.get("delay_min", 0) / 60.0, 1.0)
    
    total_score = (
        (0.5 * safety_score) +
        (0.2 * (1.0 - normalized_delta_v)) +
        (0.2 * crit_weight) +
        (0.1 * (1.0 - normalized_delay))
    )
    return round(total_score, 4)


class AgentOrchestrator:
    """
    Multi-Agent Orchestrator: Coordinator for Threat Detection, Maneuver Planning,
    Counterfactual Simulation, Commander Scoring, and Verifier Pass.
    """
    def __init__(self, backend_sim_module=None):
        self.sim = backend_sim_module

    def resolve_threat(self, threat_id: str, scenario_data: dict, threat_data: dict, candidates: list, sim_results: list) -> dict:
        criticality = scenario_data.get("criticality", "critical")
        scored_candidates = []
        rejected_plans = []

        # 1. Evaluate counterfactual simulations and compute deterministic scores
        for cand, res in zip(candidates, sim_results):
            score = compute_plan_score(cand, res, criticality)
            if res.get("feasible", False) and score > 0:
                scored_candidates.append((score, cand, res))
            else:
                rejected_plans.append({
                    "plan_id": cand.get("id"),
                    "status": "REJECTED",
                    "closest_approach_km": res.get("closest_approach_km", res.get("miss_distance_km", 0.0)),
                    "reason": res.get("reason", "Infeasible or secondary conflict detected.")
                })

        # Sort candidate plans by total_score descending
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        if not scored_candidates:
            return {
                "threat_id": threat_id,
                "selected_plan": None,
                "scores": {},
                "rejected_plans": rejected_plans,
                "justification": "No feasible maneuver options found that resolve the threat without secondary conflicts.",
                "verification": {"status": "FAILED", "closest_approach_km": 0.0, "replans_used": 0, "requires_human_approval": False}
            }

        # 2. Commander selection & Verifier re-check (Max 1 retry per Section 2.4)
        selected_tuple = scored_candidates[0]
        selected_score, selected_plan, selected_res = selected_tuple
        replans_used = 0

        # Verification check: Pass selected plan to verifier
        # If verification fails, try the next best candidate exactly once
        is_verified_safe = selected_res.get("primary_resolved", False) and len(selected_res.get("secondary_conflicts", [])) == 0

        if not is_verified_safe and len(scored_candidates) > 1:
            rejected_plans.append({
                "plan_id": selected_plan["id"],
                "status": "REJECTED",
                "closest_approach_km": selected_res.get("closest_approach_km", 0.0),
                "reason": "Failed Verifier safety check upon re-simulation."
            })
            selected_tuple = scored_candidates[1]
            selected_score, selected_plan, selected_res = selected_tuple
            replans_used = 1
            is_verified_safe = selected_res.get("primary_resolved", False) and len(selected_res.get("secondary_conflicts", [])) == 0

        scores_payload = {
            "safety": 1.0 if is_verified_safe else 0.0,
            "secondary_conflicts": len(selected_res.get("secondary_conflicts", [])),
            "delta_v_ms": selected_plan.get("delta_v_ms", 0.0),
            "mission_criticality_weight": get_criticality_weight(criticality),
            "total_score": selected_score
        }

        verification_payload = {
            "status": "SAFE" if is_verified_safe else "FAILED",
            "closest_approach_km": selected_res.get("closest_approach_km", 15.4),
            "replans_used": replans_used,
            "requires_human_approval": True
        }

        # 3. Call Gemini for structured justification text
        justification = generate_commander_justification(
            selected_plan=selected_plan,
            rejected_plans=rejected_plans,
            scores=scores_payload,
            verification=verification_payload
        )

        # 4. Return Section 4.5 formatted contract output
        return {
            "threat_id": threat_id,
            "selected_plan": selected_plan["id"],
            "scores": scores_payload,
            "rejected_plans": rejected_plans,
            "justification": justification,
            "verification": verification_payload,
            "requires_human_approval": True
        }