from pydantic import BaseModel
from typing import List, Optional

class CandidatePlan(BaseModel):
    id: str
    type: str  # "raise_orbit" | "lower_orbit" | "phase_shift" | "wait"
    delta_v_ms: float
    delay_min: int

class SimResult(BaseModel):
    plan_id: str
    primary_resolved: bool
    secondary_conflicts: List[dict]
    closest_approach_km: float
    feasible: bool
    status: str  # "REJECTED" | "SELECTED"
    reason: str

class VerificationResult(BaseModel):
    status: str  # "SAFE" | "FAILED"
    closest_approach_km: float
    replans_used: int  # 0 or 1 per Section 2.4 rules

class DecisionOutput(BaseModel):
    threat_id: str
    selected_plan: str
    scores: dict
    rejected_plans: List[dict]
    justification: str
    verification: VerificationResult
    requires_human_approval: bool = True