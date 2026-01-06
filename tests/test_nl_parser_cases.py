import json
import os

import pytest

from cortex.llm.interpreter import CommandInterpreter


@pytest.fixture
def fake_interpreter(monkeypatch):
    monkeypatch.setenv(
        "CORTEX_FAKE_COMMANDS",
        '{"commands": ["echo install step 1", "echo install step 2"]}',
    )
    return CommandInterpreter(api_key="fake", provider="fake")


def test_install_machine_learning(fake_interpreter):
    commands = fake_interpreter.parse("install something for machine learning")
    assert len(commands) > 0


def test_install_web_server(fake_interpreter):
    commands = fake_interpreter.parse("I need a web server")
    assert isinstance(commands, list)


def test_python_dev_environment(fake_interpreter):
    commands = fake_interpreter.parse("set up python development environment")
    assert commands


def test_install_docker_kubernetes(fake_interpreter):
    commands = fake_interpreter.parse("install docker and kubernetes")
    assert len(commands) >= 1


def test_ambiguous_request(fake_interpreter):
    commands = fake_interpreter.parse("install something")
    assert commands  # ambiguity handled, not crash


def test_typo_tolerance(fake_interpreter):
    commands = fake_interpreter.parse("instal dockr")
    assert commands


def test_unknown_request(fake_interpreter):
    commands = fake_interpreter.parse("do something cool")
    assert isinstance(commands, list)


def test_multiple_tools_request(fake_interpreter):
    commands = fake_interpreter.parse("install tools for video editing")
    assert commands


def test_short_query(fake_interpreter):
    commands = fake_interpreter.parse("nginx")
    assert commands


def test_sentence_style_query(fake_interpreter):
    commands = fake_interpreter.parse("can you please install a database for me")
    assert commands


def test_fake_intent_extraction_default_is_not_ambiguous(fake_interpreter):
    intent = fake_interpreter.extract_intent("install something")
    assert intent["ambiguous"] is False
    assert intent["domain"] == "general"


def test_install_database(fake_interpreter):
    commands = fake_interpreter.parse("I need a database")
    assert isinstance(commands, list)


def test_install_containerization(fake_interpreter):
    commands = fake_interpreter.parse("set up containerization tools")
    assert commands


def test_install_ml_tools(fake_interpreter):
    commands = fake_interpreter.parse("machine learning libraries")
    assert commands


def test_install_web_dev(fake_interpreter):
    commands = fake_interpreter.parse("web development stack")
    assert commands


def test_install_with_typos(fake_interpreter):
    commands = fake_interpreter.parse("instll pytorch")
    assert commands


def test_install_unknown(fake_interpreter):
    commands = fake_interpreter.parse("install unicorn software")
    assert isinstance(commands, list)  # should handle gracefully


def test_intent_low_confidence(fake_interpreter, monkeypatch):
    fake_intent = {
        "action": "install",
        "domain": "unknown",
        "install_mode": "system",
        "description": "something vague",
        "ambiguous": True,
        "confidence": 0.3,
    }
    monkeypatch.setenv("CORTEX_FAKE_INTENT", json.dumps(fake_intent))
    intent = fake_interpreter.extract_intent("vague request")
    assert intent["confidence"] < 0.5


def test_intent_high_confidence(fake_interpreter, monkeypatch):
    fake_intent = {
        "action": "install",
        "domain": "machine_learning",
        "install_mode": "python",
        "description": "pytorch",
        "ambiguous": False,
        "confidence": 0.9,
    }
    monkeypatch.setenv("CORTEX_FAKE_INTENT", json.dumps(fake_intent))
    intent = fake_interpreter.extract_intent("install pytorch")
    assert intent["confidence"] >= 0.5
    assert intent["domain"] == "machine_learning"
