"""Ingredient to product matching using fuzzy and semantic matching."""

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process

from foodplanner.graph.database import GraphDatabase
from foodplanner.graph.models import MatchesRelationship
from foodplanner.graph.repository import GraphRepository
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


# Common words to remove from ingredient names for better matching
STOP_WORDS = {
    "fresh",
    "dried",
    "chopped",
    "diced",
    "minced",
    "sliced",
    "grated",
    "crushed",
    "ground",
    "whole",
    "large",
    "medium",
    "small",
    "raw",
    "cooked",
    "frozen",
    "canned",
    "organic",
    "free-range",
    "boneless",
    "skinless",
    "peeled",
    "deseeded",
    "trimmed",
    "washed",
    "ripe",
    "unripe",
    "softened",
    "melted",
    "room temperature",
    "cold",
    "warm",
    "hot",
    "plain",
    "unsalted",
    "salted",
    "sweetened",
    "unsweetened",
    "low-fat",
    "full-fat",
    "skimmed",
    "semi-skimmed",
    "extra virgin",
    "virgin",
    "light",
    "dark",
    "white",
    "brown",
    "black",
    "red",
    "green",
    "yellow",
}

# Ingredient synonyms and translations (English -> common variations)
INGREDIENT_SYNONYMS = {
    # Vegetables
    "capsicum": ["bell pepper", "pepper", "paprika"],
    "bell pepper": ["capsicum", "pepper", "paprika"],
    "aubergine": ["eggplant"],
    "eggplant": ["aubergine"],
    "courgette": ["zucchini"],
    "zucchini": ["courgette"],
    "coriander": ["cilantro"],
    "cilantro": ["coriander"],
    "rocket": ["arugula"],
    "arugula": ["rocket"],
    "spring onion": ["scallion", "green onion"],
    "scallion": ["spring onion", "green onion"],
    "green onion": ["spring onion", "scallion"],
    # Proteins
    "minced beef": ["ground beef", "beef mince"],
    "ground beef": ["minced beef", "beef mince"],
    "chicken breast": ["chicken fillet"],
    "prawns": ["shrimp"],
    "shrimp": ["prawns"],
    # Dairy
    "double cream": ["heavy cream", "whipping cream"],
    "heavy cream": ["double cream", "whipping cream"],
    "single cream": ["light cream"],
    "caster sugar": ["superfine sugar", "fine sugar"],
    "icing sugar": ["powdered sugar", "confectioners sugar"],
    # Grains
    "plain flour": ["all-purpose flour", "flour"],
    "all-purpose flour": ["plain flour", "flour"],
    "self-raising flour": ["self-rising flour"],
    "bicarbonate of soda": ["baking soda"],
    "baking soda": ["bicarbonate of soda"],
    # Danish specific mappings (for Danish grocery products)
    "milk": ["mælk"],
    "cheese": ["ost"],
    "bread": ["brød"],
    "butter": ["smør"],
    "egg": ["æg"],
    "chicken": ["kylling"],
    "beef": ["oksekød"],
    "pork": ["svinekød"],
    "fish": ["fisk"],
    "potato": ["kartoffel", "kartofler"],
    "tomato": ["tomat", "tomater"],
    "onion": ["løg"],
    "garlic": ["hvidløg"],
    "carrot": ["gulerod", "gulerødder"],
    "apple": ["æble", "æbler"],
    "banana": ["banan", "bananer"],
    "orange": ["appelsin", "appelsiner"],
    "rice": ["ris"],
    "pasta": ["pasta"],
    "oil": ["olie"],
    "salt": ["salt"],
    "pepper": ["peber"],
    "sugar": ["sukker"],
    "flour": ["mel"],
    "cream": ["fløde"],
    "yogurt": ["yoghurt"],
}


@dataclass
class MatchResult:
    """Result of an ingredient-to-product match."""

    ingredient_name: str
    product_id: str
    product_name: str
    confidence_score: float
    match_type: str  # "exact", "fuzzy", "synonym", "semantic"
    matched_term: str  # The term that matched


class IngredientMatcher:
    """Service for matching ingredients to products."""

    # Confidence thresholds
    EXACT_MATCH_SCORE = 1.0
    SYNONYM_MATCH_SCORE = 0.95
    HIGH_FUZZY_THRESHOLD = 90
    MEDIUM_FUZZY_THRESHOLD = 75
    LOW_FUZZY_THRESHOLD = 60

    def __init__(self, db: GraphDatabase):
        self.db = db
        self.repo = GraphRepository(db)
        self._product_cache: dict[str, list[dict[str, Any]]] | None = None

    def normalize_ingredient(self, name: str) -> str:
        """
        Normalize an ingredient name for matching.

        Args:
            name: Raw ingredient name.

        Returns:
            Normalized ingredient name.
        """
        # Convert to lowercase
        normalized = name.lower().strip()

        # Remove measurements and quantities at the start
        # e.g., "2 cups flour" -> "flour", "1/2 tsp salt" -> "salt"
        # Handle: digits, unicode fractions (½¼¾), ASCII fractions (1/2), and combinations (1 1/2)
        normalized = re.sub(
            r"^[\d½¼¾⅓⅔⅛]+(?:/[\d]+)?\s*(?:[\d½¼¾⅓⅔⅛]+(?:/[\d]+)?)?\s*(cups?|tbsp|tsp|oz|g|kg|ml|l|lb)?\s*",
            "",
            normalized,
        )

        # Remove parenthetical notes
        # e.g., "butter (softened)" -> "butter"
        normalized = re.sub(r"\([^)]*\)", "", normalized)

        # Remove stop words
        words = normalized.split()
        words = [w for w in words if w not in STOP_WORDS]
        normalized = " ".join(words)

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        return normalized.strip()

    def get_synonyms(self, ingredient: str) -> list[str]:
        """
        Get synonyms for an ingredient.

        Args:
            ingredient: Normalized ingredient name.

        Returns:
            List of synonyms including the original.
        """
        synonyms = [ingredient]

        # Check direct synonyms
        if ingredient in INGREDIENT_SYNONYMS:
            synonyms.extend(INGREDIENT_SYNONYMS[ingredient])

        # Check reverse synonyms (ingredient might be a synonym of something else)
        for key, values in INGREDIENT_SYNONYMS.items():
            if ingredient in values and key not in synonyms:
                synonyms.append(key)
                synonyms.extend(v for v in values if v not in synonyms)

        return list(set(synonyms))

    async def _load_product_cache(self) -> dict[str, list[dict[str, Any]]]:
        """Load all products into a cache organized by normalized name."""
        if self._product_cache is not None:
            return self._product_cache

        query = """
        MATCH (p:Product)
        OPTIONAL MATCH (p)-[:IN_STORE]->(s:Store)
        RETURN p.id as id, p.name as name, p.price as price,
               p.discount_price as discount_price,
               p.has_active_discount as has_discount,
               s.id as store_id, s.name as store_name
        """
        results = await self.db.execute_query(query)

        self._product_cache = {}
        for r in results:
            name = r["name"].lower() if r["name"] else ""
            if name not in self._product_cache:
                self._product_cache[name] = []
            self._product_cache[name].append(r)

        logger.info(f"Loaded {len(results)} products into matching cache")
        return self._product_cache

    def invalidate_cache(self) -> None:
        """Invalidate the product cache."""
        self._product_cache = None

    async def find_matches(
        self,
        ingredient_name: str,
        top_k: int = 5,
        min_confidence: float = 0.5,
    ) -> list[MatchResult]:
        """
        Find matching products for an ingredient.

        Args:
            ingredient_name: Raw ingredient name.
            top_k: Maximum number of matches to return.
            min_confidence: Minimum confidence score to include.

        Returns:
            List of match results sorted by confidence.
        """
        normalized = self.normalize_ingredient(ingredient_name)
        if not normalized:
            return []

        synonyms = self.get_synonyms(normalized)
        product_cache = await self._load_product_cache()
        product_names = list(product_cache.keys())

        matches: list[MatchResult] = []
        seen_products: set[str] = set()

        # 1. Check for exact matches (including synonyms)
        for term in synonyms:
            if term in product_cache:
                for product in product_cache[term]:
                    if product["id"] not in seen_products:
                        score = (
                            self.EXACT_MATCH_SCORE
                            if term == normalized
                            else self.SYNONYM_MATCH_SCORE
                        )
                        matches.append(
                            MatchResult(
                                ingredient_name=ingredient_name,
                                product_id=product["id"],
                                product_name=product["name"],
                                confidence_score=score,
                                match_type="exact" if term == normalized else "synonym",
                                matched_term=term,
                            )
                        )
                        seen_products.add(product["id"])

        # 2. Fuzzy matching on normalized name
        if product_names:
            # Try each synonym
            for term in synonyms:
                fuzzy_matches = process.extract(
                    term,
                    product_names,
                    scorer=fuzz.token_sort_ratio,
                    limit=top_k * 2,
                )

                for matched_name, score, _ in fuzzy_matches:
                    if score >= self.LOW_FUZZY_THRESHOLD:
                        # Calculate confidence based on fuzzy score
                        if score >= self.HIGH_FUZZY_THRESHOLD:
                            confidence = 0.85 + (score - 90) * 0.01
                        elif score >= self.MEDIUM_FUZZY_THRESHOLD:
                            confidence = 0.70 + (score - 75) * 0.01
                        else:
                            confidence = 0.50 + (score - 60) * 0.013

                        for product in product_cache.get(matched_name, []):
                            if product["id"] not in seen_products:
                                matches.append(
                                    MatchResult(
                                        ingredient_name=ingredient_name,
                                        product_id=product["id"],
                                        product_name=product["name"],
                                        confidence_score=min(confidence, 0.95),
                                        match_type="fuzzy",
                                        matched_term=matched_name,
                                    )
                                )
                                seen_products.add(product["id"])

        # 3. Partial word matching for compound ingredients
        if len(matches) < top_k:
            words = normalized.split()
            if len(words) > 1:
                # Try matching the main word (usually last word)
                main_word = words[-1]
                for product_name in product_names:
                    if main_word in product_name and product_name not in [
                        m.matched_term for m in matches
                    ]:
                        for product in product_cache.get(product_name, []):
                            if product["id"] not in seen_products:
                                matches.append(
                                    MatchResult(
                                        ingredient_name=ingredient_name,
                                        product_id=product["id"],
                                        product_name=product["name"],
                                        confidence_score=0.55,
                                        match_type="fuzzy",
                                        matched_term=product_name,
                                    )
                                )
                                seen_products.add(product["id"])
                                if len(matches) >= top_k * 2:
                                    break
                    if len(matches) >= top_k * 2:
                        break

        # Filter by minimum confidence and sort
        matches = [m for m in matches if m.confidence_score >= min_confidence]
        matches.sort(key=lambda m: m.confidence_score, reverse=True)

        return matches[:top_k]

    async def match_and_store(
        self,
        ingredient_name: str,
        top_k: int = 3,
        min_confidence: float = 0.6,
    ) -> list[MatchResult]:
        """
        Find matches and store them in the graph database.

        Args:
            ingredient_name: Raw ingredient name.
            top_k: Maximum number of matches to store.
            min_confidence: Minimum confidence score to store.

        Returns:
            List of stored match results.
        """
        matches = await self.find_matches(
            ingredient_name,
            top_k=top_k,
            min_confidence=min_confidence,
        )

        stored_matches = []
        for match in matches:
            try:
                relationship = MatchesRelationship(
                    confidence_score=match.confidence_score,
                    match_type=match.match_type,
                )
                await self.repo.create_ingredient_product_match(
                    ingredient_name=match.ingredient_name,
                    product_id=match.product_id,
                    match=relationship,
                )
                stored_matches.append(match)
            except Exception as e:
                logger.warning(
                    f"Failed to store match for {ingredient_name} -> {match.product_name}: {e}"
                )

        return stored_matches

    async def compute_all_matches(
        self,
        min_confidence: float = 0.6,
        top_k: int = 3,
        batch_size: int = 50,
    ) -> dict[str, Any]:
        """
        Compute matches for all unmatched ingredients.

        Args:
            min_confidence: Minimum confidence to store.
            top_k: Maximum matches per ingredient.
            batch_size: Number of ingredients to process at once.

        Returns:
            Summary of matching operation.
        """
        # Preload product cache
        await self._load_product_cache()

        # Get unmatched ingredients
        unmatched = await self.repo.get_unmatched_ingredients(limit=10000)
        logger.info(f"Found {len(unmatched)} unmatched ingredients")

        results = {
            "total_ingredients": len(unmatched),
            "ingredients_matched": 0,
            "total_matches_created": 0,
            "ingredients_no_match": 0,
            "errors": 0,
        }

        for i in range(0, len(unmatched), batch_size):
            batch = unmatched[i : i + batch_size]

            for ingredient_name in batch:
                try:
                    matches = await self.match_and_store(
                        ingredient_name,
                        top_k=top_k,
                        min_confidence=min_confidence,
                    )
                    if matches:
                        results["ingredients_matched"] += 1
                        results["total_matches_created"] += len(matches)
                    else:
                        results["ingredients_no_match"] += 1
                except Exception as e:
                    logger.error(f"Error matching ingredient '{ingredient_name}': {e}")
                    results["errors"] += 1

            logger.info(
                f"Processed {min(i + batch_size, len(unmatched))}/{len(unmatched)} ingredients"
            )

        return results


async def run_ingredient_matching(
    min_confidence: float = 0.6,
    top_k: int = 3,
) -> dict[str, Any]:
    """
    Run the ingredient matching process.

    This is a convenience function for running matching outside of Celery.

    Args:
        min_confidence: Minimum confidence score.
        top_k: Maximum matches per ingredient.

    Returns:
        Matching results summary.
    """
    db = GraphDatabase()
    try:
        await db.connect()
        matcher = IngredientMatcher(db)
        return await matcher.compute_all_matches(
            min_confidence=min_confidence,
            top_k=top_k,
        )
    finally:
        await db.close()
