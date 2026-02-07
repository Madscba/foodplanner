"""Neo4j database connection management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from foodplanner.config import get_settings
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


class GraphDatabase:
    """Neo4j database connection manager."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        settings = get_settings()
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Establish connection to Neo4j."""
        if self._driver is None:
            logger.info(f"Connecting to Neo4j at {self.uri}")
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info("Neo4j connection established")

    async def close(self) -> None:
        """Close the Neo4j connection."""
        if self._driver:
            logger.info("Closing Neo4j connection")
            await self._driver.close()
            self._driver = None

    @property
    def driver(self) -> AsyncDriver:
        """Get the Neo4j driver instance."""
        if self._driver is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._driver

    @asynccontextmanager
    async def session(self, database: str = "neo4j") -> AsyncIterator[AsyncSession]:
        """Get a database session as async context manager."""
        session = self.driver.session(database=database)
        try:
            yield session
        finally:
            await session.close()

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        Execute a Cypher query and return results.

        Args:
            query: Cypher query string.
            parameters: Query parameters.
            database: Database name.

        Returns:
            List of result records as dictionaries.
        """
        async with self.session(database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> dict[str, Any]:
        """
        Execute a write query and return summary.

        Args:
            query: Cypher query string.
            parameters: Query parameters.
            database: Database name.

        Returns:
            Query execution summary with counters.
        """
        async with self.session(database) as session:
            result = await session.run(query, parameters or {})
            summary = await result.consume()
            return {
                "nodes_created": summary.counters.nodes_created,
                "nodes_deleted": summary.counters.nodes_deleted,
                "relationships_created": summary.counters.relationships_created,
                "relationships_deleted": summary.counters.relationships_deleted,
                "properties_set": summary.counters.properties_set,
            }

    async def health_check(self) -> bool:
        """Check if Neo4j is reachable and responsive."""
        try:
            if self._driver is None:
                await self.connect()
            await self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
            return False

    async def setup_constraints(self) -> None:
        """Create database constraints and indexes for optimal performance."""
        constraints = [
            # Unique constraints
            "CREATE CONSTRAINT recipe_id IF NOT EXISTS FOR (r:Recipe) REQUIRE r.id IS UNIQUE",
            (
                "CREATE CONSTRAINT ingredient_name IF NOT EXISTS "
                "FOR (i:Ingredient) REQUIRE i.name IS UNIQUE"
            ),
            "CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE",
            (
                "CREATE CONSTRAINT category_name IF NOT EXISTS "
                "FOR (c:Category) REQUIRE c.name IS UNIQUE"
            ),
            "CREATE CONSTRAINT area_name IF NOT EXISTS FOR (a:Area) REQUIRE a.name IS UNIQUE",
            "CREATE CONSTRAINT store_id IF NOT EXISTS FOR (s:Store) REQUIRE s.id IS UNIQUE",
            # Indexes for common queries
            "CREATE INDEX recipe_name IF NOT EXISTS FOR (r:Recipe) ON (r.name)",
            (
                "CREATE INDEX ingredient_normalized IF NOT EXISTS "
                "FOR (i:Ingredient) ON (i.normalized_name)"
            ),
            "CREATE INDEX product_name IF NOT EXISTS FOR (p:Product) ON (p.name)",
        ]

        logger.info("Setting up Neo4j constraints and indexes")
        for constraint in constraints:
            try:
                await self.execute_write(constraint)
            except Exception as e:
                # Constraint might already exist
                logger.debug(f"Constraint setup note: {e}")

        logger.info("Neo4j constraints and indexes configured")

    async def __aenter__(self) -> "GraphDatabase":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


# Global instance for dependency injection
_graph_db: GraphDatabase | None = None


async def get_graph_db() -> GraphDatabase:
    """
    Get the global GraphDatabase instance.

    Creates and connects if not already initialized.
    """
    global _graph_db
    if _graph_db is None:
        _graph_db = GraphDatabase()
        await _graph_db.connect()
    return _graph_db


async def close_graph_db() -> None:
    """Close the global GraphDatabase instance."""
    global _graph_db
    if _graph_db is not None:
        await _graph_db.close()
        _graph_db = None
