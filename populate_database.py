"""
Walmart Task 4 — Populate the SQLite shipment database from three CSV files.

Expected project layout:
    project/
        populate_database.py
        shipment_database.db
        data/
            shipping_data_0.csv
            shipping_data_1.csv
            shipping_data_2.csv

Uses only Python's standard library. Run from any working directory:
    python populate_database.py

Database schema expected by this task:
    product(id, name)
    shipment(id, product_id, quantity, origin, destination)

The script replaces existing shipment rows on each run so rerunning it
does not duplicate shipments. Existing product records are reused by name.
"""

import csv
import sqlite3
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "shipment_database.db"
DATA_DIR = BASE_DIR / "data"


def read_csv(path):
    """Yield CSV rows as dictionaries, handling a UTF-8 BOM if present."""
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        yield from csv.DictReader(csv_file)


def insert_product(cursor, product_name):
    """Create a product if needed and return its database ID."""
    cursor.execute(
        "INSERT OR IGNORE INTO product (name) VALUES (?)",
        (product_name.strip(),),
    )
    cursor.execute(
        "SELECT id FROM product WHERE name = ?",
        (product_name.strip(),),
    )
    result = cursor.fetchone()
    if result is None:
        raise RuntimeError(f"Could not find or create product: {product_name!r}")
    return result[0]


def load_routes(path):
    """Map each shipment identifier to its origin and destination."""
    routes = {}
    for row in read_csv(path):
        shipment_id = row["shipment_identifier"].strip()
        routes[shipment_id] = {
            "origin": row["origin_warehouse"].strip(),
            "destination": row["destination_store"].strip(),
        }
    return routes


def load_grouped_items(path):
    """Count each product per shipment from the one-product-per-row CSV."""
    items = defaultdict(lambda: defaultdict(int))
    for row in read_csv(path):
        shipment_id = row["shipment_identifier"].strip()
        product_name = row["product"].strip()
        items[shipment_id][product_name] += 1
    return items


def populate_database():
    csv0_path = DATA_DIR / "shipping_data_0.csv"
    csv1_path = DATA_DIR / "shipping_data_1.csv"
    csv2_path = DATA_DIR / "shipping_data_2.csv"

    for path in (csv0_path, csv1_path, csv2_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required CSV file not found: {path}\n"
                "Place all three CSV files in the project's data/ folder."
            )

    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"SQLite database not found: {DATABASE_PATH}\n"
            "Clone/download the provided repository so its database file "
            "is beside this script."
        )

    routes = load_routes(csv2_path)
    grouped_items = load_grouped_items(csv1_path)

    # Validate that every shipment in CSV 1 has routing information in CSV 2.
    missing_routes = sorted(set(grouped_items) - set(routes))
    if missing_routes:
        sample = ", ".join(missing_routes[:10])
        raise ValueError(
            f"{len(missing_routes)} shipment ID(s) have no route in "
            f"shipping_data_2.csv. Examples: {sample}"
        )

    inserted_from_0 = 0
    inserted_from_1_2 = 0

    with sqlite3.connect(DATABASE_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Keep the load atomic: any error rolls back the database changes.
        with connection:
            # Make repeated runs safe: rebuild shipment rows from source CSVs.
            cursor.execute("DELETE FROM shipment")

            # CSV 0 is self-contained: one row already contains product,
            # quantity, origin and destination.
            for row in read_csv(csv0_path):
                product_name = row["product"].strip()
                origin = row["origin_warehouse"].strip()
                destination = row["destination_store"].strip()
                quantity = int(row["product_quantity"])

                product_id = insert_product(cursor, product_name)
                cursor.execute(
                    """
                    INSERT INTO shipment
                        (product_id, quantity, origin, destination)
                    VALUES (?, ?, ?, ?)
                    """,
                    (product_id, quantity, origin, destination),
                )
                inserted_from_0 += 1

            # CSV 1 has one product per row; CSV 2 supplies route details.
            # Aggregate duplicate products within a shipment before inserting.
            for shipment_id, product_counts in grouped_items.items():
                route = routes[shipment_id]
                for product_name, quantity in product_counts.items():
                    product_id = insert_product(cursor, product_name)
                    cursor.execute(
                        """
                        INSERT INTO shipment
                            (product_id, quantity, origin, destination)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            product_id,
                            quantity,
                            route["origin"],
                            route["destination"],
                        ),
                    )
                    inserted_from_1_2 += 1

        # Counts are useful as a simple completion check.
        cursor.execute("SELECT COUNT(*) FROM product")
        product_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM shipment")
        shipment_count = cursor.fetchone()[0]

    print("Database population completed successfully.")
    print(f"Shipment rows from shipping_data_0.csv: {inserted_from_0}")
    print(f"Shipment rows from shipping_data_1.csv + shipping_data_2.csv: "
          f"{inserted_from_1_2}")
    print(f"Total products in database: {product_count}")
    print(f"Total shipment rows in database: {shipment_count}")
    print(f"Database: {DATABASE_PATH}")


if __name__ == "__main__":
    populate_database()
