"""
MarketAnalyzer: Uses Claude API to estimate true probabilities for Polymarket event markets.
Compares LLM-estimated probabilities against market prices to find trading edges.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    condition_id: str
    question: str
    probability_yes: float
    probability_no: float
    confidence: float
    reasoning: str
    key_factors: list[str]
    market_yes_price: float
    edge_yes: float
    edge_no: float
    recommended_side: str  # "YES", "NO", or "NONE"
    timestamp: float = field(default_factory=lambda: time.time())


class MarketAnalyzer:
    """Analyzes Polymarket event markets using Claude to estimate true probabilities."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        self.api_key = api_key
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

        # Rate limiting: max 10 requests per minute
        self._request_timestamps: list[float] = []
        self._rate_limit = 10
        self._rate_window = 60.0  # seconds

        # Cache: condition_id -> (AnalysisResult, expiry_timestamp)
        self._cache: dict[str, tuple[AnalysisResult, float]] = {}
        self._cache_ttl = 30 * 60  # 30 minutes

    async def analyze_market(
        self,
        question: str,
        description: str,
        current_yes_price: float,
        outcomes: list[str],
        tags: list[str],
        condition_id: str = "",
    ) -> AnalysisResult | None:
        """
        Analyze a market question using Claude and return probability estimates.

        Returns None if the market should be filtered out (too close to 50/50 or
        too close to resolved).
        """
        # Check cache first
        if condition_id and condition_id in self._cache:
            cached_result, expiry = self._cache[condition_id]
            if time.time() < expiry:
                logger.debug("Cache hit for condition_id=%s", condition_id)
                return cached_result
            else:
                del self._cache[condition_id]

        # Pre-filter: skip markets too close to resolved (>0.95 on either side)
        if current_yes_price > 0.95 or current_yes_price < 0.05:
            logger.debug(
                "Skipping nearly-resolved market: '%s' (yes_price=%.2f)",
                question[:60],
                current_yes_price,
            )
            return None

        # Rate limiting
        await self._enforce_rate_limit()

        # Build the prompt
        prompt = self._build_prompt(
            question, description, current_yes_price, outcomes, tags
        )

        # Call Claude API
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            logger.error("Claude API error for '%s': %s", question[:50], e)
            return None

        # Parse the response
        result = self._parse_response(
            response, question, current_yes_price, condition_id
        )
        if result is None:
            return None

        # Post-filter: skip low-confidence results too close to 50/50
        if result.confidence < 0.5 and abs(result.probability_yes - 0.5) < 0.05:
            logger.debug(
                "Skipping low-confidence 50/50 market: '%s' (prob=%.2f, conf=%.2f)",
                question[:60],
                result.probability_yes,
                result.confidence,
            )
            return None

        # Cache the result
        if condition_id:
            self._cache[condition_id] = (result, time.time() + self._cache_ttl)

        return result

    def _build_prompt(
        self,
        question: str,
        description: str,
        current_yes_price: float,
        outcomes: list[str],
        tags: list[str],
    ) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        outcomes_str = ", ".join(outcomes) if outcomes else "Yes, No"
        tags_str = ", ".join(tags) if tags else "none"

        return f"""You are an expert prediction market analyst. Analyze the following market and estimate the true probability.

MARKET QUESTION: {question}

DESCRIPTION: {description}

OUTCOMES: {outcomes_str}
TAGS: {tags_str}
CURRENT MARKET PRICE (YES): {current_yes_price:.2%}
TODAY'S DATE: {today}

Instructions:
1. Consider all known facts, historical base rates, and current context as of {today}.
2. Estimate the TRUE probability that the first outcome (YES) occurs.
3. Rate your confidence in this estimate from 0 to 1 (1 = very confident, 0 = pure guess).
4. Provide brief reasoning and key factors.

You MUST respond with ONLY a valid JSON object in this exact format (no markdown, no extra text):
{{"probability_yes": 0.XX, "confidence": 0.XX, "reasoning": "brief explanation", "key_factors": ["factor1", "factor2", "factor3"]}}"""

    def _parse_response(
        self,
        response: anthropic.types.Message,
        question: str,
        current_yes_price: float,
        condition_id: str,
    ) -> AnalysisResult | None:
        """Parse the Claude API response into an AnalysisResult."""
        try:
            raw_text = response.content[0].text.strip()

            # Handle potential markdown code fences
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                # Remove first and last lines (fences)
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw_text = "\n".join(lines).strip()

            data = json.loads(raw_text)

            probability_yes = float(data["probability_yes"])
            probability_no = 1.0 - probability_yes
            confidence = float(data["confidence"])
            reasoning = str(data.get("reasoning", ""))
            key_factors = list(data.get("key_factors", []))

            # Clamp values to valid ranges
            probability_yes = max(0.0, min(1.0, probability_yes))
            probability_no = 1.0 - probability_yes
            confidence = max(0.0, min(1.0, confidence))

            # Calculate edges
            edge_yes = probability_yes - current_yes_price
            edge_no = probability_no - (1.0 - current_yes_price)

            # Determine recommended side
            if abs(edge_yes) > abs(edge_no) and edge_yes > 0:
                recommended_side = "YES"
            elif abs(edge_no) > abs(edge_yes) and edge_no > 0:
                recommended_side = "NO"
            elif edge_yes > 0:
                recommended_side = "YES"
            elif edge_no > 0:
                recommended_side = "NO"
            else:
                recommended_side = "NONE"

            return AnalysisResult(
                condition_id=condition_id,
                question=question,
                probability_yes=probability_yes,
                probability_no=probability_no,
                confidence=confidence,
                reasoning=reasoning,
                key_factors=key_factors,
                market_yes_price=current_yes_price,
                edge_yes=edge_yes,
                edge_no=edge_no,
                recommended_side=recommended_side,
            )

        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
            logger.error(
                "Failed to parse Claude response for '%s': %s | raw: %s",
                question[:50],
                e,
                response.content[0].text[:200] if response.content else "empty",
            )
            return None

    async def _enforce_rate_limit(self) -> None:
        """Enforce max 10 requests per 60 seconds via sliding window."""
        import asyncio

        now = time.time()
        # Purge timestamps older than the window
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < self._rate_window
        ]

        if len(self._request_timestamps) >= self._rate_limit:
            # Wait until the oldest request in the window expires
            oldest = self._request_timestamps[0]
            sleep_time = self._rate_window - (now - oldest) + 0.1
            if sleep_time > 0:
                logger.info("Rate limit reached, sleeping %.1fs", sleep_time)
                await asyncio.sleep(sleep_time)

        self._request_timestamps.append(time.time())

    def clear_cache(self) -> None:
        """Clear the entire analysis cache."""
        self._cache.clear()

    def evict_expired_cache(self) -> int:
        """Remove expired cache entries. Returns number of entries evicted."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in expired:
            del self._cache[k]
        return len(expired)
