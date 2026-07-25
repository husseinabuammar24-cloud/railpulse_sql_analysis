import csv
import logging
import shutil
import sqlite3
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import TypeAlias


DB_PATH = Path(__file__).resolve().parent / "railpulse.db"
DATA_DIR = Path(__file__).resolve().parent / "data"
PROGRESS_EVERY_ROWS = 10_000
IMPORT_BATCH_SIZE = 1_000
LOGGER = logging.getLogger(__name__)


class MenuChoice(StrEnum):
    """Menu options for the interactive CLI."""

    CREATE_TABLES = "1"
    IMPORT_DATA = "2"
    CREATE_AND_IMPORT = "3"
    EXIT = "4"


# Groupings used to decide which menu selections trigger table creation
# and/or data import in the main loop.
CREATE_TABLE_CHOICES = {MenuChoice.CREATE_TABLES, MenuChoice.CREATE_AND_IMPORT}
IMPORT_DATA_CHOICES = {MenuChoice.IMPORT_DATA, MenuChoice.CREATE_AND_IMPORT}
MENU_LABELS = {
    MenuChoice.CREATE_TABLES: "Create database tables",
    MenuChoice.IMPORT_DATA: "Insert data from GTFS files",
    MenuChoice.CREATE_AND_IMPORT: "Create tables and insert data",
    MenuChoice.EXIT: "Exit",
}
ImportResult: TypeAlias = tuple[int, int]

# Names of all indexes created on the GTFS tables. Kept as a single source
# of truth so they can be dropped before a bulk import and recreated after.
INDEX_NAMES = (
    "idx_routes_agency_id",
    "idx_calendar_dates_service_id",
    "idx_trips_route_id",
    "idx_trips_service_id",
    "idx_stop_times_trip_id",
    "idx_stop_times_stop_id",
    "idx_stops_parent_station",
    "idx_transfers_from_stop_id",
    "idx_transfers_to_stop_id",
    "idx_transfers_from_trip_id",
    "idx_transfers_to_trip_id",
    "idx_translations_dedupe",
)

# Maps each GTFS table name to the CSV file that feeds it.
FILE_MAP = {
    "agency": DATA_DIR / "agency.txt",
    "routes": DATA_DIR / "routes.txt",
    "calendar": DATA_DIR / "calendar.txt",
    "calendar_dates": DATA_DIR / "calendar_dates.txt",
    "trips": DATA_DIR / "trips.txt",
    "stops": DATA_DIR / "stops.txt",
    "stop_times": DATA_DIR / "stop_times.txt",
    "transfers": DATA_DIR / "transfers.txt",
    "feed_info": DATA_DIR / "feed_info.txt",
    "translations": DATA_DIR / "translations.txt",
}

# Columns that must be present in a CSV file before we attempt to import it.
REQUIRED_COLUMNS = {
    "agency": {"agency_id"},
    "routes": {"route_id"},
    "trips": {"trip_id"},
    "stops": {"stop_id"},
    "stop_times": {"trip_id", "stop_sequence"},
}

# Import order matters: parent tables (e.g. agency, routes) must be loaded
# before child tables that reference them via foreign keys.
IMPORT_ORDER = [
    "agency",
    "routes",
    "calendar",
    "calendar_dates",
    "trips",
    "stops",
    "stop_times",
    "transfers",
    "feed_info",
    "translations",
]

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agency (
    agency_id TEXT PRIMARY KEY,
    agency_name TEXT,
    agency_url TEXT,
    agency_timezone TEXT,
    agency_lang TEXT,
    agency_phone TEXT,
    agency_fare_url TEXT
);

CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    agency_id TEXT,
    route_short_name TEXT,
    route_long_name TEXT,
    route_desc TEXT,
    route_type INTEGER,
    route_url TEXT,
    route_color TEXT,
    route_text_color TEXT,
    FOREIGN KEY (agency_id) REFERENCES agency(agency_id)
);

CREATE TABLE IF NOT EXISTS calendar (
    service_id TEXT PRIMARY KEY,
    monday INTEGER,
    tuesday INTEGER,
    wednesday INTEGER,
    thursday INTEGER,
    friday INTEGER,
    saturday INTEGER,
    sunday INTEGER,
    start_date TEXT,
    end_date TEXT
);

CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id TEXT NOT NULL,
    date TEXT NOT NULL,
    exception_type INTEGER,
    PRIMARY KEY (service_id, date),
    FOREIGN KEY (service_id) REFERENCES calendar(service_id)
);

CREATE TABLE IF NOT EXISTS trips (
    trip_id TEXT PRIMARY KEY,
    route_id TEXT,
    service_id TEXT,
    trip_headsign TEXT,
    trip_short_name TEXT,
    direction_id INTEGER,
    block_id TEXT,
    shape_id TEXT,
    wheelchair_accessible INTEGER,
    bikes_allowed INTEGER,
    FOREIGN KEY (route_id) REFERENCES routes(route_id),
    FOREIGN KEY (service_id) REFERENCES calendar(service_id)
);

CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_code TEXT,
    stop_name TEXT,
    stop_desc TEXT,
    stop_lat REAL,
    stop_lon REAL,
    zone_id TEXT,
    stop_url TEXT,
    location_type INTEGER,
    parent_station TEXT,
    wheelchair_boarding TEXT,
    platform_code TEXT
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    stop_id TEXT,
    arrival_time TEXT,
    departure_time TEXT,
    stop_headsign TEXT,
    pickup_type INTEGER,
    drop_off_type INTEGER,
    shape_dist_traveled REAL,
    PRIMARY KEY (trip_id, stop_sequence),
    FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
    FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
);

CREATE TABLE IF NOT EXISTS transfers (
    from_stop_id TEXT NOT NULL,
    to_stop_id TEXT NOT NULL,
    from_trip_id TEXT,
    to_trip_id TEXT,
    transfer_type INTEGER,
    min_transfer_time INTEGER,
    PRIMARY KEY (from_stop_id, to_stop_id, from_trip_id, to_trip_id),
    FOREIGN KEY (from_stop_id) REFERENCES stops(stop_id),
    FOREIGN KEY (to_stop_id) REFERENCES stops(stop_id),
    FOREIGN KEY (from_trip_id) REFERENCES trips(trip_id),
    FOREIGN KEY (to_trip_id) REFERENCES trips(trip_id)
);

CREATE TABLE IF NOT EXISTS feed_info (
    feed_id TEXT PRIMARY KEY,
    feed_publisher_name TEXT,
    feed_publisher_url TEXT,
    feed_lang TEXT,
    default_lang TEXT,
    feed_start_date TEXT,
    feed_end_date TEXT,
    feed_version TEXT,
    feed_contact_email TEXT,
    feed_contact_url TEXT
);

CREATE TABLE IF NOT EXISTS translations (
    table_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    record_id TEXT,
    record_sub_id TEXT,
    language TEXT NOT NULL,
    field_value TEXT,
    translation TEXT,
    PRIMARY KEY (table_name, field_name, field_value, language)
);
"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_routes_agency_id
    ON routes(agency_id);

CREATE INDEX IF NOT EXISTS idx_calendar_dates_service_id
    ON calendar_dates(service_id);

CREATE INDEX IF NOT EXISTS idx_trips_route_id
    ON trips(route_id);

CREATE INDEX IF NOT EXISTS idx_trips_service_id
    ON trips(service_id);

CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id
    ON stop_times(trip_id);

CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id
    ON stop_times(stop_id);

CREATE INDEX IF NOT EXISTS idx_stops_parent_station
    ON stops(parent_station);

CREATE INDEX IF NOT EXISTS idx_transfers_from_stop_id
    ON transfers(from_stop_id);

CREATE INDEX IF NOT EXISTS idx_transfers_to_stop_id
    ON transfers(to_stop_id);

CREATE INDEX IF NOT EXISTS idx_transfers_from_trip_id
    ON transfers(from_trip_id);

CREATE INDEX IF NOT EXISTS idx_transfers_to_trip_id
    ON transfers(to_trip_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_dedupe
    ON translations(
        table_name,
        field_name,
        ifnull(record_id, ''),
        ifnull(record_sub_id, ''),
        ifnull(field_value, ''),
        language,
        ifnull(translation, '')
    );
"""


def create_tables(connection: sqlite3.Connection) -> None:
    """Create GTFS tables if they do not already exist."""
    # Base schema creation, followed by any legacy-schema migrations needed
    # to bring an older database up to the current expected shape.
    connection.executescript(TABLES_SQL)
    ensure_transfers_nullable_trip_ids(connection)
    ensure_translations_nullable_ids(connection)
    ensure_translations_unique_index(connection)


def ensure_transfers_nullable_trip_ids(connection: sqlite3.Connection) -> None:
    """Migrate legacy transfers schema where trip IDs were incorrectly NOT NULL."""
    # PRAGMA table_info returns one row per column; index 0 is missing if the
    # table doesn't exist yet, so an empty result means there's nothing to migrate.
    columns_info = connection.execute("PRAGMA table_info(transfers)").fetchall()
    if not columns_info:
        return

    # Column index 1 is the column name, index 3 is the "notnull" flag (0/1).
    not_null_by_column = {row[1]: row[3] for row in columns_info}
    if not_null_by_column.get("from_trip_id", 0) == 0 and not_null_by_column.get("to_trip_id", 0) == 0:
        # Already on the desired schema (both columns nullable); nothing to do.
        return

    LOGGER.info("Migrating transfers schema to allow NULL trip IDs...")
    # SQLite can't ALTER a column's NOT NULL constraint directly, so rebuild
    # the table with the correct schema and copy the existing rows over.
    connection.executescript(
        """
        CREATE TABLE transfers_new (
            from_stop_id TEXT NOT NULL,
            to_stop_id TEXT NOT NULL,
            from_trip_id TEXT,
            to_trip_id TEXT,
            transfer_type INTEGER,
            min_transfer_time INTEGER,
            PRIMARY KEY (from_stop_id, to_stop_id, from_trip_id, to_trip_id),
            FOREIGN KEY (from_stop_id) REFERENCES stops(stop_id),
            FOREIGN KEY (to_stop_id) REFERENCES stops(stop_id),
            FOREIGN KEY (from_trip_id) REFERENCES trips(trip_id),
            FOREIGN KEY (to_trip_id) REFERENCES trips(trip_id)
        );

        INSERT OR IGNORE INTO transfers_new (
            from_stop_id,
            to_stop_id,
            from_trip_id,
            to_trip_id,
            transfer_type,
            min_transfer_time
        )
        SELECT
            from_stop_id,
            to_stop_id,
            from_trip_id,
            to_trip_id,
            transfer_type,
            min_transfer_time
        FROM transfers;

        DROP TABLE transfers;
        ALTER TABLE transfers_new RENAME TO transfers;
        """
    )


def ensure_translations_nullable_ids(connection: sqlite3.Connection) -> None:
    """Migrate translations schema to keep nullable IDs and PK(table_name, field_name, field_value, language)."""
    columns_info = connection.execute("PRAGMA table_info(translations)").fetchall()
    if not columns_info:
        # Table doesn't exist yet; nothing to migrate.
        return

    # Column index 3 is the "notnull" flag; index 5 is the column's position
    # within the primary key (0 means "not part of the PK").
    not_null_by_column = {row[1]: row[3] for row in columns_info}
    pk_columns = [
        row[1]
        for row in sorted(columns_info, key=lambda row: row[5])
        if row[5] > 0
    ]
    desired_pk_columns = ["table_name", "field_name", "field_value", "language"]

    if (
        not_null_by_column.get("record_id", 0) == 0
        and not_null_by_column.get("record_sub_id", 0) == 0
        and pk_columns == desired_pk_columns
    ):
        # Schema already matches what we want; nothing to migrate.
        return

    LOGGER.info("Migrating translations schema to keep nullable IDs and PK(table_name, field_name, field_value, language)...")
    # As with transfers, SQLite requires a rebuild-and-copy to change the
    # primary key definition or nullability of existing columns.
    connection.executescript(
        """
        CREATE TABLE translations_new (
            table_name TEXT NOT NULL,
            field_name TEXT NOT NULL,
            record_id TEXT,
            record_sub_id TEXT,
            language TEXT NOT NULL,
            field_value TEXT,
            translation TEXT,
            PRIMARY KEY (table_name, field_name, field_value, language)
        );

        INSERT OR IGNORE INTO translations_new (
            table_name,
            field_name,
            record_id,
            record_sub_id,
            language,
            field_value,
            translation
        )
        SELECT
            table_name,
            field_name,
            record_id,
            record_sub_id,
            language,
            field_value,
            translation
        FROM translations;

        DROP TABLE translations;
        ALTER TABLE translations_new RENAME TO translations;
        """
    )


def ensure_translations_unique_index(connection: sqlite3.Connection) -> None:
    """Ensure idempotent import for translations even when record IDs are NULL."""
    # ifnull(...) coalesces NULLs to empty string so the UNIQUE constraint
    # still applies consistently across rows with missing optional IDs.
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_dedupe
        ON translations(
            table_name,
            field_name,
            ifnull(record_id, ''),
            ifnull(record_sub_id, ''),
            ifnull(field_value, ''),
            language,
            ifnull(translation, '')
        )
        """
    )


def create_indexes(connection: sqlite3.Connection) -> None:
    """Create GTFS indexes if they do not already exist."""
    connection.executescript(INDEXES_SQL)


def analyze_database(connection: sqlite3.Connection) -> None:
    """Update SQLite planner statistics after data import and index creation."""
    connection.execute("ANALYZE")


def drop_indexes(connection: sqlite3.Connection) -> None:
    """Drop GTFS indexes before bulk import to speed up inserts."""
    # Dropping indexes before a large import avoids the overhead of updating
    # them on every row insert; they're recreated afterward in one pass.
    for index_name in INDEX_NAMES:
        connection.execute(f'DROP INDEX IF EXISTS "{index_name}"')


def import_csv_to_table(
    connection: sqlite3.Connection,
    table_name: str,
    csv_file: Path,
    progress_every_rows: int = PROGRESS_EVERY_ROWS,
) -> ImportResult:
    """Import one GTFS CSV file into a table and return total and inserted counts."""
    with csv_file.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        if not columns:
            # Empty file (no header row); nothing to import.
            return 0, 0

        # Fail fast if the CSV is missing any column the schema depends on.
        required = REQUIRED_COLUMNS.get(table_name, set())
        missing = required - set(columns)
        if missing:
            missing_columns = ", ".join(sorted(missing))
            raise ValueError(f"{table_name} missing columns: {missing_columns}")

        placeholders = ", ".join(["?"] * len(columns))
        column_sql = ", ".join([f'"{column}"' for column in columns])
        # ON CONFLICT DO NOTHING makes repeated imports idempotent: rows that
        # already exist (matching a primary key) are silently skipped rather
        # than raising an error.
        insert_sql = (
            f'INSERT INTO "{table_name}" ({column_sql}) VALUES ({placeholders}) '
            f'ON CONFLICT DO NOTHING'
        )

        total_rows = 0
        changes_before = connection.total_changes
        batch: list[tuple[str | None, ...]] = []

        LOGGER.info("Importing %s...", csv_file.name)

        for row in reader:
            total_rows += 1
            # Treat empty strings from the CSV as NULL rather than as
            # literal empty text, which matches GTFS conventions.
            values = tuple(
                None if (value := row.get(column, "")) == "" else value
                for column in columns
            )
            batch.append(values)

            if progress_every_rows > 0 and total_rows % progress_every_rows == 0:
                LOGGER.info("%s rows...", total_rows)

            # Flush in batches rather than row-by-row for import performance.
            if len(batch) >= IMPORT_BATCH_SIZE:
                connection.executemany(insert_sql, batch)
                batch.clear()

        # Flush any remaining rows that didn't fill a full batch.
        if batch:
            connection.executemany(insert_sql, batch)

    # total_changes is cumulative on the connection, so the delta since we
    # started tells us how many rows were actually inserted (vs. skipped).
    inserted_rows = connection.total_changes - changes_before
    return total_rows, inserted_rows


def load_data(connection: sqlite3.Connection) -> None:
    """Import all supported GTFS files from data directory into the database."""
    # IMPORT_ORDER ensures parent tables are populated before dependents
    # that reference them via foreign keys.
    for table_name in IMPORT_ORDER:
        csv_file = FILE_MAP[table_name]
        if csv_file.is_file():
            start_time = perf_counter()
            total_rows, inserted_rows = import_csv_to_table(
                connection,
                table_name,
                csv_file,
            )
            elapsed_seconds = perf_counter() - start_time
            skipped_rows = total_rows - inserted_rows
            LOGGER.info(
                "✓ %s\n    Total    : %s\n    Imported : %s\n    Skipped  : %s\n    Elapsed  : %.1f s",
                csv_file.name,
                total_rows,
                inserted_rows,
                skipped_rows,
                elapsed_seconds,
            )
        else:
            # Optional GTFS files (e.g. transfers, translations) may not be
            # present in every feed; skip them without failing the run.
            LOGGER.warning("Skipped %s: file not found", csv_file.name)


def show_menu() -> None:
    """Display the command-line menu for available database actions."""
    LOGGER.info("\nRailPulse SQLite Tool")
    for choice in MenuChoice:
        LOGGER.info("%s. %s", choice.value, MENU_LABELS[choice])


def configure_connection(connection: sqlite3.Connection, importing: bool = False) -> None:
    """Configure SQLite PRAGMA settings and toggle foreign key checks by mode."""
    previous_isolation_level = connection.isolation_level

    # SQLite only applies PRAGMA foreign_keys changes when not in a transaction.
    connection.isolation_level = None
    try:
        # WAL mode + NORMAL synchronous trade a small durability window for
        # much faster writes, which matters for large bulk imports.
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA cache_size=-256000")
        connection.execute("PRAGMA busy_timeout=5000")
        # Foreign keys are disabled during import (rows may arrive out of
        # dependency order within a batch) and re-enabled afterward.
        connection.execute(f"PRAGMA foreign_keys={'OFF' if importing else 'ON'}")
    finally:
        connection.isolation_level = previous_isolation_level

    fk_status = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    LOGGER.info("FK status=%s", fk_status)


def open_connection() -> sqlite3.Connection:
    """Open the SQLite database with actionable diagnostics for common filesystem issues."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        return sqlite3.connect(DB_PATH)
    except sqlite3.OperationalError as error:
        # Give a more specific hint when the failure is due to a full disk,
        # since that's a common and easily-misdiagnosed cause.
        free_bytes = shutil.disk_usage(DB_PATH.parent).free
        if free_bytes == 0:
            raise sqlite3.OperationalError(
                f"Unable to open database at {DB_PATH}: no free disk space left on {DB_PATH.parent}"
            ) from error

        raise sqlite3.OperationalError(
            f"Unable to open database at {DB_PATH}: check folder permissions and available disk space"
        ) from error


def main() -> None:
    """Run the interactive CLI loop for schema creation and GTFS data import."""
    while True:
        show_menu()
        raw_choice = input("Choose an option (1-4): ").strip()

        try:
            choice = MenuChoice(raw_choice)
        except ValueError:
            # Not a recognized menu value; re-prompt instead of crashing.
            LOGGER.warning("Invalid choice. Please try again.")
            continue

        if choice == MenuChoice.EXIT:
            LOGGER.info("Goodbye!")
            break

        with open_connection() as connection:
            configure_connection(
                connection,
                importing=choice in IMPORT_DATA_CHOICES,
            )

            try:
                if choice == MenuChoice.CREATE_TABLES:
                    with connection:
                        create_tables(connection)
                        create_indexes(connection)
                    LOGGER.info("Tables and indexes created or verified.")
                    LOGGER.info("Database ready at %s", DB_PATH)

                if choice in IMPORT_DATA_CHOICES:
                    with connection:
                        create_tables(connection)

                    try:
                        # Drop indexes for faster bulk inserts, then reload
                        # all GTFS data in a single transaction.
                        drop_indexes(connection)
                        LOGGER.info("Indexes dropped before import.")

                        with connection:
                            load_data(connection)
                    finally:
                        # Re-enable FK checks outside of the import transaction.
                        configure_connection(connection, importing=False)

                    # With FKs back on, check for any orphaned references
                    # that slipped in while foreign key checks were off.
                    fk_violation = connection.execute(
                        'SELECT "table", rowid, parent, fkid FROM pragma_foreign_key_check LIMIT 1'
                    ).fetchone()
                    if fk_violation:
                        LOGGER.error(
                            "Foreign key check failed (table=%s, rowid=%s, parent=%s, fkid=%s)",
                            fk_violation[0],
                            fk_violation[1],
                            fk_violation[2],
                            fk_violation[3],
                        )
                    else:
                        LOGGER.info("Foreign key check passed.")

                    with connection:
                        create_indexes(connection)
                        analyze_database(connection)
                    LOGGER.info("Indexes recreated after import.")

                    LOGGER.info("Data import completed.")
                    LOGGER.info("Database updated at %s", DB_PATH)
            except (sqlite3.Error, ValueError) as error:
                LOGGER.error("Database error: %s", error)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
