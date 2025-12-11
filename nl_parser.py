import difflib
import re
from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple

# Vocabulary for typo correction
VOCAB = {
    "python", "pip", "venv", "virtualenv", "conda", "anaconda",
    "docker", "kubernetes", "k8s", "kubectl",
    "nginx", "apache", "httpd", "web", "server",
    "flask", "django", "tensorflow", "pytorch", "torch",
    "install", "setup", "development", "env", "environment",
}

# Canonical examples for lightweight semantic matching
INTENT_EXAMPLES = {
    "install_ml": [
        "install something for machine learning",
        "install pytorch",
        "install tensorflow",
        "i want to run pytorch",
    ],
    "install_web_server": [
        "i need a web server",
        "install nginx",
        "install apache",
        "set up a web server",
    ],
    "setup_python_env": [
        "set up python development environment",
        "install python 3.10",
        "create python venv",
        "setup dev env",
    ],
    "install_docker": [
        "install docker",
        "add docker",
        "deploy containers - docker",
    ],
    "install_docker_k8s": [
        "install docker and kubernetes",
        "docker and k8s",
        "k8s and docker on my mac",
    ],
}


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9.\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return text.split()


def spell_correct_token(token: str) -> Tuple[str, bool]:
    """Return corrected_token, was_corrected"""
    if token in VOCAB:
        return token, False
    close = difflib.get_close_matches(token, VOCAB, n=1, cutoff=0.75)
    if close:
        return close[0], True
    return token, False


def apply_spell_correction(tokens: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    corrections = []
    new_tokens = []
    for t in tokens:
        new, fixed = spell_correct_token(t)
        if fixed:
            corrections.append((t, new))
        new_tokens.append(new)
    return new_tokens, corrections


def fuzzy_phrase_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def semantic_intent_score(text: str) -> Tuple[str, float]:
    """Compare text with intent examples."""
    best_intent = "unknown"
    best_score = 0.0

    for intent, examples in INTENT_EXAMPLES.items():
        for ex in examples:
            score = fuzzy_phrase_score(text, ex)
            if score > best_score:
                best_score = score
                best_intent = intent

    return best_intent, best_score


def rule_intent(text: str) -> Tuple[str, float]:
    """Simple keyword/rule-based detection."""
    t = text

    if "docker" in t:
        if "kubernetes" in t or "k8s" in t or "kubectl" in t:
            return "install_docker_k8s", 0.95
        return "install_docker", 0.9

    if "kubernetes" in t or "k8s" in t or "kubectl" in t:
        return "install_docker_k8s", 0.9

    if "nginx" in t or "apache" in t or "httpd" in t or "web server" in t:
        return "install_web_server", 0.9

    if "python" in t or "venv" in t or "conda" in t or "anaconda" in t:
        return "setup_python_env", 0.9

    if any(word in t for word in ("tensorflow", "pytorch", "torch", "machine learning", "ml")):
        return "install_ml", 0.9

    return "unknown", 0.0


VERSION_RE = re.compile(r"python\s*([0-9]+(?:\.[0-9]+)?)")
PLATFORM_RE = re.compile(r"\b(mac|macos|windows|linux|ubuntu|debian)\b")
PACKAGE_RE = re.compile(r"\b(nginx|apache|docker|kubernetes|k8s|kubectl|python|pip|venv|conda|tensorflow|pytorch)\b")


def extract_slots(text: str) -> Dict[str, Any]:
    slots = {}

    v = VERSION_RE.search(text)
    if v:
        slots["python_version"] = v.group(1)

    p = PLATFORM_RE.search(text)
    if p:
        slots["platform"] = p.group(1)

    pkgs = PACKAGE_RE.findall(text)
    if pkgs:
        slots["packages"] = list(dict.fromkeys(pkgs))  # unique preserve order

    return slots


def aggregate_confidence(c_rule, c_sem, num_corrections, c_classifier=0.0):
    penalty = 1 - (num_corrections * 0.1)
    penalty = max(0.0, penalty)

    final = (
        0.4 * c_rule +
        0.4 * c_sem +
        0.2 * c_classifier
    ) * penalty

    return round(max(0.0, min(1.0, final)), 2)


def decide_clarifications(intent, confidence):
    if intent == "unknown" or confidence < 0.6:
        return [
            "Install Docker and Kubernetes",
            "Set up Python development environment",
            "Install a web server (nginx/apache)",
            "Install ML libraries (tensorflow/pytorch)",
        ]
    if intent == "setup_python_env" and confidence < 0.75:
        return ["Use venv", "Use conda", "Install a specific Python version"]
    return []


def parse_request(text: str) -> Dict[str, Any]:
    """Main function used by tests and demo."""
    norm = normalize(text)
    tokens = tokenize(norm)

    tokens_corr, corrections = apply_spell_correction(tokens)
    corrected_text = " ".join(tokens_corr)

    rule_int, c_rule = rule_intent(corrected_text)
    sem_int, c_sem = semantic_intent_score(corrected_text)

    if rule_int != "unknown" and rule_int == sem_int:
        chosen_intent = rule_int
        c_classifier = 0.95
    elif rule_int != "unknown":
        chosen_intent = rule_int
        c_classifier = 0.0
    elif c_sem > 0.6:
        chosen_intent = sem_int
        c_classifier = 0.0
    else:
        chosen_intent = "unknown"
        c_classifier = 0.0

    slots = extract_slots(corrected_text)

    confidence = aggregate_confidence(
        c_rule, c_sem, len(corrections), c_classifier
    )

    clarifications = decide_clarifications(chosen_intent, confidence)

    explanation = []
    if corrections:
        explanation.append(
            "corrected: " + ", ".join(f"{a}->{b}" for a, b in corrections)
        )
    explanation.append(f"rule_intent={rule_int} ({c_rule:.2f})")
    explanation.append(f"semantic_match={sem_int} ({c_sem:.2f})")

    return {
        "intent": chosen_intent,
        "confidence": confidence,
        "explanation": "; ".join(explanation),
        "slots": slots,
        "corrections": corrections,
        "clarifications": clarifications,
    }


