"""Script to scrape REMA 1000 products and store in the PostgreSQL database.

This stores products in the PostgreSQL database for querying.

Run with: uv run python scripts/scrape_to_db.py
Query with: uv run python scripts/scrape_to_db.py --query

Requires PostgreSQL to be running (via Docker or locally).
"""

import argparse
import asyncio

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from foodplanner.config import settings
from foodplanner.database import Base
from foodplanner.ingest.batch_ingest import _upsert_scraped_products
from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper
from foodplanner.models import Product, Store


def get_engine():
    """Create database engine using settings."""
    # Convert async URL to sync URL for this script
    database_url = settings.database_url.replace("+asyncpg", "")
    return create_engine(database_url, echo=False)


def init_db(engine):
    """Initialize database tables."""
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Create REMA 1000 store if it doesn't exist
        existing = session.execute(select(Store).where(Store.id == "rema1000")).scalar_one_or_none()

        if not existing:
            store = Store(
                id="rema1000",
                name="REMA 1000",
                brand="rema1000",
                is_active=True,
            )
            session.add(store)
            session.commit()
            print("Created REMA 1000 store record")


async def scrape_and_store(limit: int = 50, category: str | None = None):
    """Scrape products and store in database."""
    engine = get_engine()
    init_db(engine)

    print(f"\n{'='*60}")
    print("Scraping products from REMA 1000")
    print(f"  Limit: {limit}")
    print(f"  Category: {category or 'All'}")
    print(f"{'='*60}\n")

    async with Rema1000Scraper() as scraper:
        products = await scraper.scrape_products(category=category, limit=limit)

    print(f"Scraped {len(products)} products\n")

    # Store in database
    with Session(engine) as session:
        inserted = _upsert_scraped_products(
            session=session,
            store_id="rema1000",
            products=products,
        )
        print(f"Stored {inserted} products in database\n")

    print(f"Database: {settings.database_url}")
    print("\nRun with --query to see stored products")


def query_db():
    """Query and display stored products."""
    engine = get_engine()

    with Session(engine) as session:
        # Get total count
        total = session.execute(select(func.count(Product.id))).scalar() or 0

        print(f"\n{'='*60}")
        print(f"Database: {settings.database_url}")
        print(f"Total products: {total}")
        print(f"{'='*60}\n")

        if total == 0:
            print("No products found. Run without --query first to scrape products.")
            return

        # Show products by category
        categories = session.execute(
            select(Product.category, func.count(Product.id))
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
        ).all()

        print("Products by category:")
        for cat, count in categories:
            print(f"  {cat or 'Uncategorized'}: {count}")

        # Show sample products
        print(f"\n{'='*60}")
        print("Sample products (first 20):")
        print(f"{'='*60}\n")

        products = session.execute(select(Product).order_by(Product.name).limit(20)).scalars().all()

        for p in products:
            print(f"ID: {p.id}")
            print(f"  Name: {p.name}")
            print(f"  Price: {p.price:.2f} kr")
            print(f"  Unit: {p.unit}")
            print(f"  Category: {p.category or 'N/A'}")
            print(f"  Origin: {p.origin or 'N/A'}")
            print(f"  Last Updated: {p.last_updated}")
            print()


def interactive_query():
    """Interactive SQL query mode."""
    engine = get_engine()

    print(f"\n{'='*60}")
    print("Interactive SQL Query Mode")
    print(f"Database: {settings.database_url}")
    print("Type SQL queries or 'exit' to quit")
    print(f"{'='*60}\n")

    print("Available tables: stores, products, discounts")
    print("Example: SELECT name, price FROM products WHERE price < 10 LIMIT 5")
    print()

    with engine.connect() as conn:
        while True:
            try:
                query = input("SQL> ").strip()

                if query.lower() in ("exit", "quit", "q"):
                    break

                if not query:
                    continue

                result = conn.execute(text(query))
                rows = result.fetchall()

                if rows:
                    # Print column headers
                    columns = result.keys()
                    print("\n" + " | ".join(str(c) for c in columns))
                    print("-" * 60)

                    # Print rows
                    for row in rows:
                        print(" | ".join(str(v)[:30] for v in row))

                    print(f"\n({len(rows)} rows)\n")
                else:
                    print("(0 rows)\n")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="Scrape REMA 1000 products to PostgreSQL database")
    parser.add_argument("--query", "-q", action="store_true", help="Query existing database")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive SQL mode")
    parser.add_argument("--limit", "-l", type=int, default=50, help="Number of products to scrape")
    parser.add_argument("--category", "-c", type=str, help="Category slug (e.g., frugt-gront)")

    args = parser.parse_args()

    if args.interactive:
        interactive_query()
    elif args.query:
        query_db()
    else:
        asyncio.run(scrape_and_store(limit=args.limit, category=args.category))


if __name__ == "__main__":
    main()
