import os
import sys
import warnings
warnings.filterwarnings("ignore")  # Suppresses SDK deprecation/notice warnings

from google import genai
from google.genai import types
from pydantic import BaseModel


class SuppressStderr:
    def __enter__(self):
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self._original_stderr

class CommanderJustification(BaseModel):
    justification: str

def generate_commander_justification(selected_plan: dict, rejected_plans: list, scores: dict, verification: dict) -> str:
    """
    Calls Google Gemini to generate a 2-3 sentence human-readable justification.
    Strictly uses Gemini ONLY for text reasoning over deterministic inputs (Section 2.3).
    """
    # Pre-calculated fallback string for demo safety (Section 9.3)
    plan_id = selected_plan.get("id", "PLAN-3")
    dv = scores.get("delta_v_ms", 2.8)
    fallback = (
        f"{plan_id} resolves the primary conjunction with zero secondary conflicts "
        f"at an acceptable delta-v cost ({dv} m/s). Alternative plans were rejected due "
        "to secondary conflict risks or insufficient safety margins."
    )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Agent Warning] GEMINI_API_KEY environment variable not found. Using fallback justification.")
        return fallback

    try:
        client = genai.Client(api_key=api_key)

        system_instruction = (
            "You are the Commander agent in OrbitGuard, a satellite conjunction response system. "
            "You are given pre-computed structured physics and simulation results. "
            "Never invent, modify, or override any physical numbers or safety statuses. "
            "Write a concise 2-3 sentence plain-English justification explaining why the selected plan was chosen over the rejected options."
        )

        user_prompt = f"""
        Selected Plan: {selected_plan}
        Scores: {scores}
        Rejected Plans: {rejected_plans}
        Verification Result: {verification}
        """
        with SuppressStderr():
           response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=CommanderJustification,
                temperature=0.2,
            ),
        )

        result = CommanderJustification.model_validate_json(response.text)
        return result.justification

    except Exception as e:
        print(f"[Agent Warning] Gemini API call failed or timed out: {e}. Using fallback justification.")
        return fallback