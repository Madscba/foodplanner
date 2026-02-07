"""Tests for ingredient-to-product matching."""

from unittest.mock import MagicMock

import pytest

from foodplanner.graph.matching import (
    INGREDIENT_SYNONYMS,
    STOP_WORDS,
    IngredientMatcher,
    MatchResult,
)


class TestIngredientNormalization:
    """Tests for ingredient name normalization."""

    @pytest.fixture
    def matcher(self):
        """Create a matcher with mocked database."""
        mock_db = MagicMock()
        return IngredientMatcher(mock_db)

    def test_basic_normalization(self, matcher):
        """Test basic string normalization."""
        assert matcher.normalize_ingredient("Chicken") == "chicken"
        assert matcher.normalize_ingredient("  GARLIC  ") == "garlic"

    def test_remove_stop_words(self, matcher):
        """Test removal of stop words."""
        assert matcher.normalize_ingredient("fresh garlic") == "garlic"
        assert matcher.normalize_ingredient("chopped onion") == "onion"
        assert matcher.normalize_ingredient("dried herbs") == "herbs"

    def test_remove_measurements(self, matcher):
        """Test removal of measurements at start."""
        assert matcher.normalize_ingredient("2 cups flour") == "flour"
        assert matcher.normalize_ingredient("1/2 tsp salt") == "salt"
        assert matcher.normalize_ingredient("500g chicken") == "chicken"

    def test_remove_parenthetical(self, matcher):
        """Test removal of parenthetical notes."""
        assert matcher.normalize_ingredient("butter (softened)") == "butter"
        assert matcher.normalize_ingredient("eggs (room temperature)") == "eggs"

    def test_complex_normalization(self, matcher):
        """Test complex ingredient strings."""
        assert matcher.normalize_ingredient("2 cups fresh chopped onion") == "onion"
        assert (
            matcher.normalize_ingredient("500g boneless skinless chicken breast")
            == "chicken breast"
        )

    def test_empty_after_normalization(self, matcher):
        """Test ingredients that become empty after normalization."""
        # If only stop words, should return empty
        assert matcher.normalize_ingredient("fresh") == ""
        assert matcher.normalize_ingredient("   ") == ""


class TestSynonymLookup:
    """Tests for ingredient synonym lookup."""

    @pytest.fixture
    def matcher(self):
        """Create a matcher with mocked database."""
        mock_db = MagicMock()
        return IngredientMatcher(mock_db)

    def test_direct_synonyms(self, matcher):
        """Test direct synonym lookup."""
        synonyms = matcher.get_synonyms("capsicum")
        assert "bell pepper" in synonyms
        assert "capsicum" in synonyms

    def test_reverse_synonyms(self, matcher):
        """Test reverse synonym lookup."""
        synonyms = matcher.get_synonyms("bell pepper")
        assert "capsicum" in synonyms

    def test_danish_synonyms(self, matcher):
        """Test Danish ingredient synonyms."""
        synonyms = matcher.get_synonyms("chicken")
        assert "kylling" in synonyms

        synonyms = matcher.get_synonyms("garlic")
        assert "hvidløg" in synonyms

    def test_no_synonyms(self, matcher):
        """Test ingredient with no synonyms."""
        synonyms = matcher.get_synonyms("quinoa")
        assert synonyms == ["quinoa"]

    def test_unique_synonyms(self, matcher):
        """Test that synonyms are unique."""
        synonyms = matcher.get_synonyms("eggplant")
        assert len(synonyms) == len(set(synonyms))


class TestMatchResult:
    """Tests for MatchResult data class."""

    def test_create_match_result(self):
        """Test creating a match result."""
        result = MatchResult(
            ingredient_name="chicken breast",
            product_id="p123",
            product_name="Chicken Breast 500g",
            confidence_score=0.95,
            match_type="exact",
            matched_term="chicken breast",
        )

        assert result.ingredient_name == "chicken breast"
        assert result.confidence_score == 0.95
        assert result.match_type == "exact"


class TestIngredientMatching:
    """Tests for the full matching process."""

    @pytest.fixture
    def matcher_with_products(self, sample_products):
        """Create a matcher with mocked product cache."""
        mock_db = MagicMock()
        matcher = IngredientMatcher(mock_db)

        # Build product cache
        cache = {}
        for p in sample_products:
            name = p["name"].lower()
            if name not in cache:
                cache[name] = []
            cache[name].append(p)

        matcher._product_cache = cache
        return matcher

    @pytest.mark.asyncio
    async def test_exact_match(self, matcher_with_products):
        """Test exact ingredient matching."""
        matches = await matcher_with_products.find_matches("soy sauce")

        assert len(matches) > 0
        assert matches[0].confidence_score == 1.0
        assert matches[0].match_type == "exact"
        assert matches[0].product_name == "soy sauce"

    @pytest.mark.asyncio
    async def test_fuzzy_match(self, matcher_with_products):
        """Test fuzzy ingredient matching."""
        matches = await matcher_with_products.find_matches("chicken")

        # Should find chicken breast
        assert len(matches) > 0
        assert any("chicken" in m.product_name.lower() for m in matches)

    @pytest.mark.asyncio
    async def test_synonym_match(self, matcher_with_products):
        """Test matching via synonyms."""
        # "garlic" should match "hvidløg" (Danish) via synonyms
        matches = await matcher_with_products.find_matches("garlic")

        # Should find fresh garlic and possibly hvidløg
        product_names = [m.product_name.lower() for m in matches]
        assert any("garlic" in name or "hvidløg" in name for name in product_names)

    @pytest.mark.asyncio
    async def test_no_match(self, matcher_with_products):
        """Test when no matches are found."""
        matches = await matcher_with_products.find_matches(
            "exotic fruit xyz",
            min_confidence=0.8,
        )

        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_top_k_limit(self, matcher_with_products):
        """Test that results are limited to top_k."""
        matches = await matcher_with_products.find_matches(
            "rice",
            top_k=2,
            min_confidence=0.1,
        )

        assert len(matches) <= 2

    @pytest.mark.asyncio
    async def test_min_confidence_filter(self, matcher_with_products):
        """Test that low confidence matches are filtered."""
        matches = await matcher_with_products.find_matches(
            "chicken",
            min_confidence=0.9,
        )

        for match in matches:
            assert match.confidence_score >= 0.9

    @pytest.mark.asyncio
    async def test_results_sorted_by_confidence(self, matcher_with_products):
        """Test that results are sorted by confidence."""
        matches = await matcher_with_products.find_matches(
            "onion",
            top_k=5,
            min_confidence=0.1,
        )

        if len(matches) > 1:
            for i in range(len(matches) - 1):
                assert matches[i].confidence_score >= matches[i + 1].confidence_score


class TestStopWords:
    """Tests for stop words configuration."""

    def test_stop_words_lowercase(self):
        """Test that all stop words are lowercase."""
        for word in STOP_WORDS:
            assert word == word.lower()

    def test_common_stop_words_present(self):
        """Test that common cooking terms are in stop words."""
        common_terms = ["fresh", "chopped", "minced", "diced", "frozen"]
        for term in common_terms:
            assert term in STOP_WORDS


class TestIngredientSynonyms:
    """Tests for ingredient synonyms configuration."""

    def test_synonym_consistency(self):
        """Test that synonyms are bidirectional where expected."""
        # capsicum <-> bell pepper
        assert "bell pepper" in INGREDIENT_SYNONYMS.get("capsicum", [])
        assert "capsicum" in INGREDIENT_SYNONYMS.get("bell pepper", [])

    def test_danish_translations_present(self):
        """Test that Danish translations are included."""
        assert "mælk" in INGREDIENT_SYNONYMS.get("milk", [])
        assert "kylling" in INGREDIENT_SYNONYMS.get("chicken", [])
        assert "hvidløg" in INGREDIENT_SYNONYMS.get("garlic", [])
