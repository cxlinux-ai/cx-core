import pytest
from nl_parser import parse_request

@pytest.mark.parametrize("text,expected", [
    ("install something for machine learning", "install_ml"),
    ("I need a web server", "install_web_server"),
    ("set up python development environment", "setup_python_env"),
    ("install docker and kubernets", "install_docker_k8s"),
    ("Can you provision a python env with pip, venv and flake8?", "setup_python_env"),
    ("need nginx or apache for a website", "install_web_server"),
    ("deploy containers - docker", "install_docker"),
    ("k8s and docker on my mac", "install_docker_k8s"),
    ("i want to run pytorch", "install_ml"),
    ("setup dev env", "ambiguous"),
    ("add docker", "install_docker"),
    ("pls install pyhton 3.10", "setup_python_env"),
])
def test_intent(text, expected):
    result = parse_request(text)
    intent = result["intent"]
    confidence = result["confidence"]

    if expected == "ambiguous":
        assert result["clarifications"], f"Expected clarifications for: {text}"
    else:
        assert intent == expected
        assert confidence >= 0.5

def test_corrections():
    r = parse_request("install docker and kubernets")
    assert r["intent"] == "install_docker_k8s"
    assert any(orig == "kubernets" for orig, _ in r["corrections"])

def test_slot_extraction():
    r = parse_request("pls install python 3.10 on mac")
    assert r["slots"].get("python_version") == "3.10"
    assert r["slots"].get("platform") in ("mac", "macos")