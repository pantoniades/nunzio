"""Exercise-name normalization, matching, and muscle-group guessing — pure, no I/O."""

import re

# Spelling variants folded to one token before comparing.
_SYNONYMS = {
    "pec": "chest",
    "pecs": "chest",
    "pectoral": "chest",
    "flye": "fly",
    "flyes": "fly",
    "flies": "fly",
    "db": "dumbbell",
    "dumbell": "dumbbell",
    "bb": "barbell",
}

# Tokens that make a different exercise: "dumbbell bench press" is not "bench press",
# "incline curl" is not "curl". A mismatch on any of these halves the score.
_VARIANT_TOKENS = {
    "dumbbell", "barbell", "machine", "cable", "band", "kettlebell", "smith", "ez",
    "incline", "decline",
}

_VARIANT_PENALTY = 0.5


def _singular(t: str) -> str:
    if len(t) <= 3:
        return t
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith(("sses", "shes", "ches", "xes")):
        return t[:-2]
    if t.endswith("s") and not t.endswith(("ss", "us")):
        return t[:-1]
    return t


def normalize_tokens(name: str) -> set[str]:
    """Lowercase, split on non-alphanumerics, fold synonyms and plurals."""
    s = (name or "").lower()
    s = re.sub(r"pull[\s-]+down", "pulldown", s)
    out = set()
    for t in re.findall(r"[a-z0-9]+", s):
        t = _SYNONYMS.get(t, t)
        t = _singular(t)
        out.add(_SYNONYMS.get(t, t))
    return out


def score_match(query: str, name: str) -> float:
    """Jaccard overlap of normalized tokens, penalized when equipment/angle differ."""
    q = normalize_tokens(query)
    n = normalize_tokens(name)
    if not q or not n:
        return 0.0
    score = len(q & n) / len(q | n)
    if (q ^ n) & _VARIANT_TOKENS:
        score *= _VARIANT_PENALTY
    return score


# Ordered (first match wins): specific phrases before generic words.
_GROUP_RULES: list[tuple[str, str]] = [
    (r"\b(run|running|jog|bike|biking|cycling|cycle|elliptical|treadmill|walk|walking"
     r"|swim|swimming|rowing machine|erg|stair|stepper|spin)\b", "cardio"),
    (r"\b(stretch|stretching|yoga|mobility|foam roll)", "flexibility"),
    (r"\bleg curl|\bhamstring curl", "legs"),
    (r"\b(face pull|rear delt|lateral raise|front raise|shoulder|overhead press|arnold"
     r"|military|pull[\s-]?apart|upright row|shrug)", "shoulders"),
    (r"\b(tricep|triceps|skull|pushdown|push-down|rope pulldown|dip|kickback)", "triceps"),
    (r"\b(row|pulldown|pull[\s-]?down|pull[\s-]?up|chin[\s-]?up|lat\b|deadlift"
     r"|back extension)", "back"),
    (r"\b(curl|bicep|biceps)", "biceps"),
    (r"\b(bench|chest|pec|pectoral|fly|flye|flyes|push[\s-]?up)", "chest"),
    (r"\b(squat|lunge|leg|calf|calves|glute|hip thrust|step[\s-]?up)", "legs"),
    (r"\b(plank|crunch|sit[\s-]?up|abs?|core|russian twist|hollow)\b", "core"),
]


def guess_muscle_group(name: str) -> str:
    """Best-effort muscle group from an exercise name; 'general' if nothing fits."""
    s = (name or "").lower()
    for pattern, group in _GROUP_RULES:
        if re.search(pattern, s):
            return group
    return "general"
