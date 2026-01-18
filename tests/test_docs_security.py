import pytest

from cortex.docs_generator import DocsGenerator


def test_path_traversal_validation():
    """Verify that path traversal attempts are blocked."""
    gen = DocsGenerator()

    malicious_names = [
        "../etc/passwd",
        "../../hidden_dir",
        "nested/../traversal",
        "invalid/name",
        "back\\slash",
        "",
        None,
    ]

    for name in malicious_names:
        with pytest.raises(ValueError) as excinfo:
            gen.generate_software_docs(name)
        assert "Invalid characters in software name" in str(excinfo.value)

        with pytest.raises(ValueError):
            gen.export_docs(name)

        with pytest.raises(ValueError):
            gen.view_guide(name, "installation")


def test_safe_software_name():
    """Verify that legitimate software names are accepted."""
    gen = DocsGenerator()
    # This shouldn't raise ValueError, but might raise other errors if package doesn't exist
    # which is fine for this security test.
    try:
        gen._validate_software_name("postgresql")
        gen._validate_software_name("nginx-common")
        gen._validate_software_name("python3.12")
    except ValueError:
        pytest.fail("Legitimate software name raised ValueError")
