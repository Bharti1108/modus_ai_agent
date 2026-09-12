"""
Pure computation: role-fit %, skill gaps, competency averages.
No LLM calls here -- keep this fast and deterministic.
"""
from role_profiles import ROLE_PROFILES, MAX_SCORE


def competency_averages(qas: list) -> dict:
    """qas: list of dicts with 'competency' and 'score' (1-5, may be None)."""
    buckets = {}
    for qa in qas:
        if qa.get("score") is None:
            continue
        buckets.setdefault(qa["competency"], []).append(qa["score"])
    return {c: round(sum(v) / len(v), 2) for c, v in buckets.items()}


def compute_role_fit(target_role: str, comp_avgs: dict) -> float:
    profile = ROLE_PROFILES.get(target_role)
    if not profile:
        return 0.0

    total_weight = 0.0
    achieved = 0.0
    for competency, required_level in profile.items():
        candidate_level = comp_avgs.get(competency, 0.0)
        total_weight += required_level
        achieved += min(candidate_level, required_level)  # no over-credit beyond requirement... 
        # NOTE: switched to ratio-based scoring below for fairness (over-performance rewarded)
    # Ratio-based version: reward exceeding the bar too, capped at MAX_SCORE
    total_required = sum(profile.values())
    total_actual_weighted = sum(
        min(comp_avgs.get(c, 0.0), MAX_SCORE) * (req / total_required)
        for c, req in profile.items()
    )
    pct = (total_actual_weighted / (total_required / len(profile))) * 100 if profile else 0
    # simpler, more intuitive formula: average(candidate/required) capped at 100 per competency
    ratios = []
    for competency, required_level in profile.items():
        candidate_level = comp_avgs.get(competency, 0.0)
        ratios.append(min(candidate_level / required_level, 1.0) if required_level else 1.0)
    return round((sum(ratios) / len(ratios)) * 100, 1) if ratios else 0.0


def compute_skill_gaps(target_role: str, comp_avgs: dict) -> list:
    profile = ROLE_PROFILES.get(target_role, {})
    gaps = []
    for competency, required_level in profile.items():
        candidate_level = comp_avgs.get(competency, 0.0)
        if candidate_level < required_level:
            gaps.append({
                "competency": competency,
                "required": required_level,
                "current": candidate_level,
                "gap": round(required_level - candidate_level, 2),
            })
    gaps.sort(key=lambda g: g["gap"], reverse=True)
    return gaps


def pick_next_competency(target_role: str, qas: list, max_questions: int = 3) -> tuple:
    """
    Adaptive logic: pick the competency that is either (a) unexplored, or
    (b) has the lowest average score so far. Difficulty ramps based on
    performance so far in that competency.
    Returns (competency, difficulty) or (None, None) if session should end.
    """
    profile = ROLE_PROFILES.get(target_role, {})
    competencies = list(profile.keys())

    if len(qas) >= max_questions:
        return None, None

    avgs = competency_averages(qas)
    asked_counts = {}
    for qa in qas:
        asked_counts[qa["competency"]] = asked_counts.get(qa["competency"], 0) + 1

    # Prioritize competencies never asked yet
    unexplored = [c for c in competencies if asked_counts.get(c, 0) == 0]
    if unexplored:
        # weight by role importance (higher required level first)
        unexplored.sort(key=lambda c: profile[c], reverse=True)
        return unexplored[0], "medium"

    # Otherwise target the weakest-scoring competency for a follow-up
    weakest = min(competencies, key=lambda c: avgs.get(c, 5.0))
    weakest_avg = avgs.get(weakest, 3.0)
    if weakest_avg >= 4:
        difficulty = "hard"
    elif weakest_avg >= 2.5:
        difficulty = "medium"
    else:
        difficulty = "easy"
    return weakest, difficulty
