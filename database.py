"""
Database layer for AgriSchedule.
Uses SQLite so the whole app runs with zero external services — good for
an academic MVP/demo, and easy to swap for Postgres later (same SQL mostly).
"""

import sqlite3
import os
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "agrischedule.db")

# Flip this (or wire it to an env var) if/when you migrate to Postgres.
# app.py checks this to decide whether to show the SQLite backup/restore
# panel, which doesn't apply once you're on a real Postgres server.
USE_POSTGRES = False


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)  # ensure "data" folder exists
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS crop_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop TEXT NOT NULL,
            variety TEXT NOT NULL,
            day_offset INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            category TEXT NOT NULL,        -- irrigation | fertilizer | pesticide | weeding | observation | harvest
            instructions TEXT NOT NULL,
            weather_sensitive INTEGER NOT NULL DEFAULT 0  -- 1 if rain/wind should delay this operation
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS farmers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            location TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            crop TEXT NOT NULL,
            variety TEXT NOT NULL,
            field_area REAL NOT NULL,
            sowing_date TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pest_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER,
            image_name TEXT,
            diagnosis TEXT,
            confidence REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (farmer_id) REFERENCES farmers (id)
        )
    """)

    conn.commit()

    # ---- migration: add `phone` to any farmers table created before this
    # column existed, so existing agrischedule.db files don't break. ----
    existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(farmers)").fetchall()}
    if "phone" not in existing_cols:
        cur.execute("ALTER TABLE farmers ADD COLUMN phone TEXT")
        conn.commit()

    # Seed default crop schedules only if table is empty
    cur.execute("SELECT COUNT(*) as c FROM crop_stages")
    if cur.fetchone()["c"] == 0:
        seed_default_schedules(conn)

    conn.close()


def seed_default_schedules(conn):
    """Seed a few realistic crop calendars so the app is usable out of the box."""
    rows = []

    # --- RICE (generic, applies to common transplanted varieties) ---
    rice_stages = [
        (0, "Nursery seed sowing", "sowing", "Soak seeds 24 hrs, sow in prepared nursery bed.", 0),
        (14, "Transplanting", "transplanting", "Transplant 25-30 day old... (use 14-21 day seedlings for short duration varieties).", 1),
        (21, "First weeding", "weeding", "Hand weed or apply pre-emergence herbicide as per local recommendation.", 1),
        (25, "First fertilizer top dressing (Urea)", "fertilizer", "Apply nitrogen top dressing at active tillering stage.", 1),
        (35, "First pest scouting", "observation", "Scout for stem borer and leaf folder; check for egg masses.", 0),
        (45, "Second weeding", "weeding", "Remove weeds before panicle initiation stage begins.", 1),
        (55, "Second fertilizer top dressing", "fertilizer", "Apply nitrogen at panicle initiation stage for grain filling.", 1),
        (60, "Pesticide spray if pest threshold crossed", "pesticide", "Spray recommended pesticide ONLY if pest scouting shows threshold levels.", 1),
        (75, "Flowering stage water management", "irrigation", "Maintain 5cm standing water; avoid moisture stress during flowering.", 1),
        (100, "Maturity check", "observation", "Check grain hardness and field yellowing (~80% grains golden).", 0),
        (110, "Harvest", "harvest", "Harvest when 80-85% of grains have turned golden yellow.", 1),
    ]
    for day, stage, cat, instr, ws in rice_stages:
        rows.append(("Rice", "Generic (Short Duration)", day, stage, cat, instr, ws))

    # --- WHEAT ---
    wheat_stages = [
        (0, "Sowing", "sowing", "Sow seeds at 4-5 cm depth in well-prepared field.", 0),
        (20, "First irrigation (Crown Root Initiation)", "irrigation", "Critical irrigation stage — do not delay even if soil looks moist.", 1),
        (25, "First weeding", "weeding", "Hand weed or apply post-emergence herbicide.", 1),
        (40, "First fertilizer top dressing", "fertilizer", "Apply nitrogen top dressing after first irrigation.", 1),
        (60, "Second irrigation (Tillering)", "irrigation", "Irrigate at tillering stage for better yield.", 1),
        (80, "Second fertilizer top dressing", "fertilizer", "Apply nitrogen at jointing stage.", 1),
        (90, "Third irrigation (Flowering)", "irrigation", "Critical stage; avoid moisture stress during flowering.", 1),
        (110, "Pest & disease scouting", "observation", "Check for rust and aphid infestation.", 0),
        (130, "Maturity check", "observation", "Grains should be hard, straw turning golden.", 0),
        (140, "Harvest", "harvest", "Harvest when moisture content is around 20-25%.", 1),
    ]
    for day, stage, cat, instr, ws in wheat_stages:
        rows.append(("Wheat", "Generic", day, stage, cat, instr, ws))

    # --- TOMATO ---
    tomato_stages = [
        (0, "Nursery sowing", "sowing", "Sow seeds in trays/nursery bed with fine, well-drained soil.", 0),
        (25, "Transplanting", "transplanting", "Transplant 25 day old seedlings to main field, 45x60 cm spacing.", 1),
        (35, "First fertilizer dose", "fertilizer", "Apply NPK dose after establishment.", 1),
        (40, "Staking", "observation", "Provide stakes/support as plants grow.", 0),
        (45, "Pest scouting (fruit borer, whitefly)", "observation", "Scout for fruit borer and whitefly-transmitted viral symptoms.", 0),
        (50, "Pesticide/IPM spray if needed", "pesticide", "Spray only if pest scouting crosses threshold; prefer IPM methods.", 1),
        (60, "Second fertilizer dose", "fertilizer", "Apply second dose at flowering stage.", 1),
        (65, "Flowering stage irrigation", "irrigation", "Maintain consistent soil moisture during flowering/fruit set.", 1),
        (80, "First harvest window begins", "harvest", "Begin harvesting fruits at breaker/turning stage.", 1),
    ]
    for day, stage, cat, instr, ws in tomato_stages:
        rows.append(("Tomato", "Generic", day, stage, cat, instr, ws))

    conn.executemany(
        """INSERT INTO crop_stages
           (crop, variety, day_offset, stage_name, category, instructions, weather_sensitive)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------
# Crop schedule helpers
# ---------------------------------------------------------------------

def get_crops():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT crop FROM crop_stages ORDER BY crop").fetchall()
    conn.close()
    return [r["crop"] for r in rows]


def get_varieties(crop):
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT variety FROM crop_stages WHERE crop = ? ORDER BY variety", (crop,)
    ).fetchall()
    conn.close()
    return [r["variety"] for r in rows]


def get_schedule(crop, variety):
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM crop_stages WHERE crop = ? AND variety = ?
           ORDER BY day_offset ASC""",
        (crop, variety),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_crop_stage(crop, variety, day_offset, stage_name, category, instructions, weather_sensitive):
    conn = get_conn()
    conn.execute(
        """INSERT INTO crop_stages
           (crop, variety, day_offset, stage_name, category, instructions, weather_sensitive)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (crop, variety, day_offset, stage_name, category, instructions, int(weather_sensitive)),
    )
    conn.commit()
    conn.close()


def delete_crop_stage(stage_id):
    conn = get_conn()
    conn.execute("DELETE FROM crop_stages WHERE id = ?", (stage_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# Farmer helpers
# ---------------------------------------------------------------------

def add_farmer(name, phone, location, latitude, longitude, crop, variety, field_area, sowing_date, language="en"):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO farmers
           (name, phone, location, latitude, longitude, crop, variety, field_area, sowing_date, language, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, phone, location, latitude, longitude, crop, variety, field_area,
         sowing_date, language, datetime.now().isoformat()),
    )
    conn.commit()
    farmer_id = cur.lastrowid
    conn.close()
    return farmer_id


def get_all_farmers():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM farmers ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_farmer(farmer_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM farmers WHERE id = ?", (farmer_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def log_pest_report(farmer_id, image_name, diagnosis, confidence):
    conn = get_conn()
    conn.execute(
        """INSERT INTO pest_reports (farmer_id, image_name, diagnosis, confidence, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (farmer_id, image_name, diagnosis, confidence, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()