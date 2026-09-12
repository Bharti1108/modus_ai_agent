"""
Hardcoded role -> competency requirement matrix.
Scores are on a 1-5 scale. This is your "consulting competency model".
Add roles/competencies here without touching any other code.
"""

COMPETENCIES = [
    "Problem Solving",
    "Business Acumen",
    "Communication",
    "Leadership",
    "Data & Quant Reasoning",
]

ROLE_PROFILES = {
    "Management Consultant (Associate)": {
        "Problem Solving": 4.5,
        "Business Acumen": 4.0,
        "Communication": 4.0,
        "Leadership": 3.0,
        "Data & Quant Reasoning": 4.0,
    },
    "Strategy Analyst": {
        "Problem Solving": 4.0,
        "Business Acumen": 3.5,
        "Communication": 3.5,
        "Leadership": 2.5,
        "Data & Quant Reasoning": 4.5,
    },
    "Engagement Manager": {
        "Problem Solving": 4.0,
        "Business Acumen": 4.5,
        "Communication": 4.5,
        "Leadership": 4.5,
        "Data & Quant Reasoning": 3.5,
    },
}

# Personality/Values self-report items (Likert 1-5, "Strongly Disagree" -> "Strongly Agree")
PERSONALITY_ITEMS = [
    {"id": "p1", "text": "I enjoy breaking ambiguous problems into structured parts.", "trait": "Structured Thinking"},
    {"id": "p2", "text": "I actively seek feedback and change my approach quickly.", "trait": "Adaptability"},
    {"id": "p3", "text": "I'm comfortable pushing back on senior stakeholders with data.", "trait": "Assertiveness"},
    {"id": "p4", "text": "I prioritize client/stakeholder value over being 'technically right'.", "trait": "Client Orientation"},
    {"id": "p5", "text": "I stay calm and organized under tight deadlines.", "trait": "Resilience"},
    {"id": "p6", "text": "I prefer collaborative decision-making over working solo.", "trait": "Collaboration"},
    {"id": "p7", "text": "I proactively flag risks before being asked.", "trait": "Ownership"},
    {"id": "p8", "text": "I enjoy mentoring or unblocking teammates.", "trait": "Leadership"},
    {"id": "p9", "text": "I'm energized by quantitative/data-heavy problems.", "trait": "Quant Orientation"},
    {"id": "p10", "text": "I adapt my communication style to different audiences.", "trait": "Communication"},
]

MAX_SCORE = 5.0
