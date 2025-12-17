"""Unit tests for semantic cache functionality."""

import os
import sqlite3
import tempfile
import unittest

from cortex.semantic_cache import SemanticCache


class TestSemanticCache(unittest.TestCase):
    """Test suite for SemanticCache."""

    def setUp(self):
        """Create temporary database for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_cache.db")
        self.cache = SemanticCache(db_path=self.db_path, max_entries=10, similarity_threshold=0.85)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_cache_initialization(self):
        """Test that cache database is created properly."""
        self.assertTrue(os.path.exists(self.db_path))
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        conn.close()

        self.assertIn("llm_cache_entries", tables)
        self.assertIn("llm_cache_stats", tables)

    def test_cache_stats_initial(self):
        """Test initial cache stats are zero."""
        stats = self.cache.stats()
        self.assertEqual(stats.hits, 0)
        self.assertEqual(stats.misses, 0)
        self.assertEqual(stats.total, 0)
        self.assertEqual(stats.hit_rate, 0.0)

    def test_put_and_get_exact_match(self):
        """Test storing and retrieving with exact prompt match."""
        prompt = "install nginx"
        commands = ["sudo apt update", "sudo apt install -y nginx"]

        # Store in cache
        self.cache.put_commands(
            prompt=prompt,
            provider="openai",
            model="gpt-4",
            system_prompt="test system prompt",
            commands=commands,
        )

        # Retrieve from cache
        retrieved = self.cache.get_commands(
            prompt=prompt, provider="openai", model="gpt-4", system_prompt="test system prompt"
        )

        self.assertEqual(retrieved, commands)

        # Check stats
        stats = self.cache.stats()
        self.assertEqual(stats.hits, 1)
        self.assertEqual(stats.misses, 0)

    def test_cache_miss(self):
        """Test cache miss with non-existent prompt."""
        result = self.cache.get_commands(
            prompt="install something that was never cached",
            provider="openai",
            model="gpt-4",
            system_prompt="test system prompt",
        )

        self.assertIsNone(result)

        stats = self.cache.stats()
        self.assertEqual(stats.hits, 0)
        self.assertEqual(stats.misses, 1)

    def test_semantic_similarity_match(self):
        """Test semantic similarity matching for similar prompts."""
        # Store original
        self.cache.put_commands(
            prompt="install nginx web server",
            provider="openai",
            model="gpt-4",
            system_prompt="test system prompt",
            commands=["sudo apt install nginx"],
        )

        # Try very similar wording
        result = self.cache.get_commands(
            prompt="install nginx web server",
            provider="openai",
            model="gpt-4",
            system_prompt="test system prompt",
        )

        # Should find the exact match
        self.assertIsNotNone(result)
        self.assertEqual(result, ["sudo apt install nginx"])

    def test_provider_isolation(self):
        """Test that different providers don't share cache entries."""
        prompt = "install docker"
        commands_openai = ["apt install docker"]
        commands_claude = ["apt install docker-ce"]

        # Store with OpenAI
        self.cache.put_commands(
            prompt=prompt,
            provider="openai",
            model="gpt-4",
            system_prompt="test",
            commands=commands_openai,
        )

        # Store with Claude
        self.cache.put_commands(
            prompt=prompt,
            provider="claude",
            model="claude-3",
            system_prompt="test",
            commands=commands_claude,
        )

        # Retrieve for OpenAI
        result_openai = self.cache.get_commands(
            prompt=prompt, provider="openai", model="gpt-4", system_prompt="test"
        )

        # Retrieve for Claude
        result_claude = self.cache.get_commands(
            prompt=prompt, provider="claude", model="claude-3", system_prompt="test"
        )

        self.assertEqual(result_openai, commands_openai)
        self.assertEqual(result_claude, commands_claude)

    def test_lru_eviction(self):
        """Test that LRU eviction works when max_entries is exceeded."""
        # Fill cache to max
        for i in range(10):
            self.cache.put_commands(
                prompt=f"install package{i}",
                provider="openai",
                model="gpt-4",
                system_prompt="test",
                commands=[f"apt install package{i}"],
            )

        # Add one more (should trigger eviction)
        self.cache.put_commands(
            prompt="install package10",
            provider="openai",
            model="gpt-4",
            system_prompt="test",
            commands=["apt install package10"],
        )

        # Verify cache size doesn't exceed max
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM llm_cache_entries")
        count = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count, 10)

    def test_embedding_generation(self):
        """Test that embeddings are generated correctly."""
        vec = SemanticCache._embed("test prompt")

        self.assertEqual(len(vec), 128)
        self.assertIsInstance(vec[0], float)

        # Check normalization (L2 norm should be ~1.0)
        norm = sum(v * v for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]

        # Identical vectors
        sim1 = SemanticCache._cosine(vec1, vec2)
        self.assertAlmostEqual(sim1, 1.0)

        # Orthogonal vectors
        sim2 = SemanticCache._cosine(vec1, vec3)
        self.assertAlmostEqual(sim2, 0.0)


if __name__ == "__main__":
    unittest.main()
