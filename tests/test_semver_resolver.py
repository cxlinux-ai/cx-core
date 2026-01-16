"""
Tests for Semantic Version Conflict Resolution

Issue: #154 - Semantic Version Conflict Resolution
"""

import pytest

from cortex.semver_resolver import (
    BreakingChangeRisk,
    ConstraintType,
    Dependency,
    ResolutionStrategy,
    SemVer,
    SemVerResolver,
    VersionConflict,
    VersionConstraint,
    run_semver_resolver,
)


class TestSemVer:
    """Tests for SemVer dataclass."""

    def test_basic_version(self):
        """Test basic version parsing."""
        v = SemVer(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

    def test_version_with_prerelease(self):
        """Test version with prerelease."""
        v = SemVer(major=1, minor=0, patch=0, prerelease="alpha.1")
        assert str(v) == "1.0.0-alpha.1"

    def test_version_with_build(self):
        """Test version with build metadata."""
        v = SemVer(major=1, minor=0, patch=0, build="20240114")
        assert str(v) == "1.0.0+20240114"

    def test_version_comparison_major(self):
        """Test major version comparison."""
        v1 = SemVer(1, 0, 0)
        v2 = SemVer(2, 0, 0)
        assert v1 < v2
        assert v2 > v1

    def test_version_comparison_minor(self):
        """Test minor version comparison."""
        v1 = SemVer(1, 1, 0)
        v2 = SemVer(1, 2, 0)
        assert v1 < v2

    def test_version_comparison_patch(self):
        """Test patch version comparison."""
        v1 = SemVer(1, 0, 1)
        v2 = SemVer(1, 0, 2)
        assert v1 < v2

    def test_version_comparison_prerelease(self):
        """Test prerelease comparison."""
        v1 = SemVer(1, 0, 0, prerelease="alpha")
        v2 = SemVer(1, 0, 0)
        assert v1 < v2  # Prerelease is lower

    def test_version_equality(self):
        """Test version equality."""
        v1 = SemVer(1, 2, 3)
        v2 = SemVer(1, 2, 3)
        assert v1 == v2

    def test_version_hash(self):
        """Test version hashing."""
        v1 = SemVer(1, 2, 3)
        v2 = SemVer(1, 2, 3)
        assert hash(v1) == hash(v2)

    def test_is_compatible_with(self):
        """Test compatibility check."""
        v1 = SemVer(1, 2, 3)
        v2 = SemVer(1, 5, 0)
        v3 = SemVer(2, 0, 0)
        assert v1.is_compatible_with(v2)
        assert not v1.is_compatible_with(v3)

    def test_breaking_change_from(self):
        """Test breaking change detection."""
        v1 = SemVer(1, 0, 0)
        v2 = SemVer(2, 0, 0)
        v3 = SemVer(1, 1, 0)
        v4 = SemVer(1, 0, 1)

        assert v2.breaking_change_from(v1) == BreakingChangeRisk.HIGH
        assert v3.breaking_change_from(v1) == BreakingChangeRisk.LOW
        assert v4.breaking_change_from(v1) == BreakingChangeRisk.NONE


class TestVersionConstraint:
    """Tests for VersionConstraint."""

    def test_exact_constraint(self):
        """Test exact version constraint."""
        c = VersionConstraint(
            raw="=1.2.3",
            constraint_type=ConstraintType.EXACT,
            version=SemVer(1, 2, 3),
        )
        assert c.satisfies(SemVer(1, 2, 3))
        assert not c.satisfies(SemVer(1, 2, 4))

    def test_caret_constraint(self):
        """Test caret constraint."""
        c = VersionConstraint(
            raw="^1.2.3",
            constraint_type=ConstraintType.CARET,
            version=SemVer(1, 2, 3),
        )
        assert c.satisfies(SemVer(1, 2, 3))
        assert c.satisfies(SemVer(1, 9, 0))
        assert not c.satisfies(SemVer(2, 0, 0))
        assert not c.satisfies(SemVer(1, 2, 2))

    def test_caret_constraint_zero_major(self):
        """Test caret constraint with 0.x version."""
        c = VersionConstraint(
            raw="^0.2.3",
            constraint_type=ConstraintType.CARET,
            version=SemVer(0, 2, 3),
        )
        assert c.satisfies(SemVer(0, 2, 5))
        assert not c.satisfies(SemVer(0, 3, 0))

    def test_tilde_constraint(self):
        """Test tilde constraint."""
        c = VersionConstraint(
            raw="~1.2.3",
            constraint_type=ConstraintType.TILDE,
            version=SemVer(1, 2, 3),
        )
        assert c.satisfies(SemVer(1, 2, 3))
        assert c.satisfies(SemVer(1, 2, 9))
        assert not c.satisfies(SemVer(1, 3, 0))

    def test_greater_constraint(self):
        """Test greater than constraint."""
        c = VersionConstraint(
            raw=">1.0.0",
            constraint_type=ConstraintType.GREATER,
            version=SemVer(1, 0, 0),
        )
        assert c.satisfies(SemVer(1, 0, 1))
        assert not c.satisfies(SemVer(1, 0, 0))

    def test_greater_eq_constraint(self):
        """Test greater than or equal constraint."""
        c = VersionConstraint(
            raw=">=1.0.0",
            constraint_type=ConstraintType.GREATER_EQ,
            version=SemVer(1, 0, 0),
        )
        assert c.satisfies(SemVer(1, 0, 0))
        assert c.satisfies(SemVer(2, 0, 0))
        assert not c.satisfies(SemVer(0, 9, 0))

    def test_less_constraint(self):
        """Test less than constraint."""
        c = VersionConstraint(
            raw="<2.0.0",
            constraint_type=ConstraintType.LESS,
            version=SemVer(2, 0, 0),
        )
        assert c.satisfies(SemVer(1, 9, 9))
        assert not c.satisfies(SemVer(2, 0, 0))

    def test_range_constraint(self):
        """Test range constraint."""
        c = VersionConstraint(
            raw=">=1.0.0 <2.0.0",
            constraint_type=ConstraintType.RANGE,
            version=SemVer(1, 0, 0),
            max_version=SemVer(2, 0, 0),
        )
        assert c.satisfies(SemVer(1, 0, 0))
        assert c.satisfies(SemVer(1, 9, 9))
        assert not c.satisfies(SemVer(2, 0, 0))
        assert not c.satisfies(SemVer(0, 9, 0))

    def test_any_constraint(self):
        """Test any version constraint."""
        c = VersionConstraint(
            raw="*",
            constraint_type=ConstraintType.ANY,
        )
        assert c.satisfies(SemVer(0, 0, 1))
        assert c.satisfies(SemVer(99, 99, 99))


class TestSemVerResolver:
    """Tests for SemVerResolver class."""

    @pytest.fixture
    def resolver(self):
        """Create a resolver instance."""
        return SemVerResolver()

    def test_parse_simple_version(self, resolver):
        """Test parsing simple version."""
        v = resolver.parse_version("1.2.3")
        assert v is not None
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_version_with_prerelease(self, resolver):
        """Test parsing version with prerelease."""
        v = resolver.parse_version("1.0.0-beta.1")
        assert v is not None
        assert v.prerelease == "beta.1"

    def test_parse_version_with_build(self, resolver):
        """Test parsing version with build metadata."""
        v = resolver.parse_version("1.0.0+build123")
        assert v is not None
        assert v.build == "build123"

    def test_parse_invalid_version(self, resolver):
        """Test parsing invalid version."""
        assert resolver.parse_version("not-a-version") is None
        assert resolver.parse_version("1.2") is None
        assert resolver.parse_version("") is None

    def test_parse_caret_constraint(self, resolver):
        """Test parsing caret constraint."""
        c = resolver.parse_constraint("^1.2.3")
        assert c is not None
        assert c.constraint_type == ConstraintType.CARET
        assert c.version == SemVer(1, 2, 3)

    def test_parse_tilde_constraint(self, resolver):
        """Test parsing tilde constraint."""
        c = resolver.parse_constraint("~1.2.3")
        assert c is not None
        assert c.constraint_type == ConstraintType.TILDE

    def test_parse_range_constraint(self, resolver):
        """Test parsing range constraint."""
        c = resolver.parse_constraint(">=1.0.0 <2.0.0")
        assert c is not None
        assert c.constraint_type == ConstraintType.RANGE
        assert c.version == SemVer(1, 0, 0)
        assert c.max_version == SemVer(2, 0, 0)

    def test_parse_any_constraint(self, resolver):
        """Test parsing any constraint."""
        c = resolver.parse_constraint("*")
        assert c is not None
        assert c.constraint_type == ConstraintType.ANY

    def test_parse_exact_constraint(self, resolver):
        """Test parsing exact constraint."""
        c = resolver.parse_constraint("=1.2.3")
        assert c is not None
        assert c.constraint_type == ConstraintType.EXACT

    def test_add_dependency(self, resolver):
        """Test adding dependency."""
        result = resolver.add_dependency("lib-x", "^1.2.3", "pkg-a")
        assert result is True
        assert "lib-x" in resolver.dependencies
        assert len(resolver.dependencies["lib-x"]) == 1

    def test_add_invalid_dependency(self, resolver):
        """Test adding invalid dependency."""
        result = resolver.add_dependency("lib-x", "invalid", "pkg-a")
        assert result is False


class TestVersionConflict:
    """Tests for VersionConflict detection."""

    def test_no_conflict_single_dep(self):
        """Test no conflict with single dependency."""
        conflict = VersionConflict(
            package="lib-x",
            dependencies=[
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^1.0.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(1, 0, 0),
                    ),
                    source="pkg-a",
                )
            ],
        )
        assert conflict.is_conflicting is False

    def test_conflict_different_majors(self):
        """Test conflict with different major versions."""
        conflict = VersionConflict(
            package="lib-x",
            dependencies=[
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^2.0.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(2, 0, 0),
                    ),
                    source="pkg-a",
                ),
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^1.0.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(1, 0, 0),
                    ),
                    source="pkg-b",
                ),
            ],
        )
        assert conflict.is_conflicting is True


class TestResolutionStrategies:
    """Tests for resolution strategy generation."""

    @pytest.fixture
    def resolver(self):
        return SemVerResolver()

    def test_suggest_resolutions(self, resolver):
        """Test resolution strategy generation."""
        conflict = VersionConflict(
            package="lib-x",
            dependencies=[
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^2.0.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(2, 0, 0),
                    ),
                    source="pkg-a",
                ),
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="~1.9.0",
                        constraint_type=ConstraintType.TILDE,
                        version=SemVer(1, 9, 0),
                    ),
                    source="pkg-b",
                ),
            ],
        )

        strategies = resolver.suggest_resolutions(conflict)

        assert len(strategies) > 0
        assert any(s.recommended for s in strategies)

    def test_compatible_constraints_strategy(self, resolver):
        """Test finding common version for compatible constraints."""
        conflict = VersionConflict(
            package="lib-x",
            dependencies=[
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^1.2.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(1, 2, 0),
                    ),
                    source="pkg-a",
                ),
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^1.5.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(1, 5, 0),
                    ),
                    source="pkg-b",
                ),
            ],
        )

        strategies = resolver.suggest_resolutions(conflict)

        # Should find a "use latest compatible" strategy
        assert any("compatible" in s.name.lower() for s in strategies)


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def resolver(self):
        return SemVerResolver()

    def test_display_conflicts_none(self, resolver, capsys):
        """Test displaying no conflicts."""
        resolver.display_conflicts()
        captured = capsys.readouterr()
        assert "no" in captured.out.lower()

    def test_display_conflicts(self, resolver, capsys):
        """Test displaying conflicts."""
        resolver.conflicts = [
            VersionConflict(
                package="lib-x",
                dependencies=[
                    Dependency(
                        name="lib-x",
                        constraint=VersionConstraint(
                            raw="^2.0.0",
                            constraint_type=ConstraintType.CARET,
                            version=SemVer(2, 0, 0),
                        ),
                        source="pkg-a",
                    ),
                    Dependency(
                        name="lib-x",
                        constraint=VersionConstraint(
                            raw="^1.0.0",
                            constraint_type=ConstraintType.CARET,
                            version=SemVer(1, 0, 0),
                        ),
                        source="pkg-b",
                    ),
                ],
            )
        ]

        resolver.display_conflicts()
        captured = capsys.readouterr()
        assert "lib-x" in captured.out

    def test_display_resolutions(self, resolver, capsys):
        """Test displaying resolutions."""
        conflict = VersionConflict(
            package="lib-x",
            dependencies=[
                Dependency(
                    name="lib-x",
                    constraint=VersionConstraint(
                        raw="^1.0.0",
                        constraint_type=ConstraintType.CARET,
                        version=SemVer(1, 0, 0),
                    ),
                    source="pkg-a",
                ),
            ],
        )

        resolver.display_resolutions(conflict)
        captured = capsys.readouterr()
        # Should show some output even for non-conflicting case
        assert len(captured.out) > 0


class TestRunSemverResolver:
    """Tests for run_semver_resolver entry point."""

    def test_run_no_packages(self, capsys):
        """Test running with no packages."""
        result = run_semver_resolver("analyze")
        assert result == 0
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower()

    def test_run_parse_version(self, capsys):
        """Test parsing a version."""
        result = run_semver_resolver("parse", packages=["1.2.3"])
        assert result == 0
        captured = capsys.readouterr()
        assert "version" in captured.out.lower()

    def test_run_parse_constraint(self, capsys):
        """Test parsing a constraint."""
        result = run_semver_resolver("parse", packages=["^1.2.3"])
        assert result == 0
        captured = capsys.readouterr()
        assert "constraint" in captured.out.lower()

    def test_run_check_satisfies(self, capsys):
        """Test checking constraint satisfaction."""
        result = run_semver_resolver("check", packages=["^1.0.0", "1.5.0"])
        assert result == 0
        captured = capsys.readouterr()
        assert "satisfies" in captured.out.lower()

    def test_run_check_not_satisfies(self, capsys):
        """Test checking constraint non-satisfaction."""
        result = run_semver_resolver("check", packages=["^2.0.0", "1.5.0"])
        assert result == 1
        captured = capsys.readouterr()
        assert "not" in captured.out.lower()

    def test_run_compare(self, capsys):
        """Test version comparison."""
        result = run_semver_resolver("compare", packages=["1.0.0", "2.0.0"])
        assert result == 0
        captured = capsys.readouterr()
        assert "<" in captured.out

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        result = run_semver_resolver("unknown")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()

    def test_run_analyze_with_conflict(self, capsys):
        """Test analyzing conflicting packages."""
        result = run_semver_resolver(
            "analyze",
            packages=["lib-x:^2.0.0:pkg-a", "lib-x:~1.9.0:pkg-b"],
        )
        # Returns 1 if conflicts found
        captured = capsys.readouterr()
        assert "lib-x" in captured.out

    def test_run_analyze_no_conflict(self, capsys):
        """Test analyzing non-conflicting packages."""
        result = run_semver_resolver(
            "analyze",
            packages=["lib-x:^1.2.0:pkg-a", "lib-x:^1.5.0:pkg-b"],
        )
        assert result == 0
