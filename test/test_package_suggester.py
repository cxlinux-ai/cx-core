from cortex.suggestions.package_suggester import suggest_alternatives


def test_suggests_apache_for_apache_server():
    results = suggest_alternatives("apache-server")
    names = [pkg["name"] for pkg in results]
    assert "apache2" in names


def test_suggest_returns_list():
    results = suggest_alternatives("randompkg")
    assert isinstance(results, list)


def test_suggest_with_exact_match():
    results = suggest_alternatives("apache2")
    assert results[0]["name"] == "apache2"
