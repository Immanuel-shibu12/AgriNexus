import os
import time

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

import database as db

st.set_page_config(page_title="AgriNexus Admin", page_icon="🛠️", layout="wide")
db.init_db()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ---------------------------------------------------------------------
# Theme (dark, simple — this is an internal tool, not farmer-facing,
# so it intentionally does NOT share app.py's light/dark toggle system)
# ---------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: #0B0F0D; color: #E5E7EB; }
    .stApp p, .stApp span, .stApp label, .stApp li,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    [data-testid="stMarkdownContainer"] { color: #E5E7EB; }
    [data-testid="stCaptionContainer"] { color: #9aa0a6 !important; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #161B18 !important;
        border-radius: 14px !important;
        border: 1px solid #2A322D !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] * { color: #E5E7EB !important; }
    button[kind="primary"] {
        background-color: #22A559 !important;
        border-color: #22A559 !important;
        border-radius: 10px !important;
    }
    button[kind="secondary"] {
        background-color: #161B18 !important;
        color: #E5E7EB !important;
        border: 1px solid #2A322D !important;
        border-radius: 10px !important;
    }
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid #2A322D; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Password gate
# ---------------------------------------------------------------------
if "admin_authed" not in st.session_state:
    st.session_state.admin_authed = False

if not st.session_state.admin_authed:
    st.title("🛠️ AgriNexus Admin")

    if not ADMIN_PASSWORD:
        st.warning(
            "No `ADMIN_PASSWORD` is set in your `.env` file, so this page is "
            "currently **unprotected** — anyone with the URL can get in. "
            "Add `ADMIN_PASSWORD=yourpassword` to `.env` to lock it down. "
            "For anything beyond local/demo use, put this behind proper auth "
            "or a reverse proxy — this password box alone isn't production-grade security."
        )
        if st.button("Continue without a password (local/demo only)"):
            st.session_state.admin_authed = True
            st.rerun()
    else:
        pwd = st.text_input("Admin password", type="password")
        if st.button("Log in", type="primary"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_authed = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()


# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------
top_l, top_r = st.columns([4, 1])
with top_l:
    st.title("🛠️ AgriNexus Admin")
    st.caption("Internal tool — database view, crop schedule builder, backup/restore.")
with top_r:
    if st.button("Log out", use_container_width=True):
        st.session_state.admin_authed = False
        st.rerun()

st.markdown("---")


# ---------------------------------------------------------------------
# Helpers — raw table reads (no dedicated db.* helper exists for
# "all rows" on crop_stages/pest_reports, so we query directly)
# ---------------------------------------------------------------------
def fetch_all(table, order_by):
    conn = db.get_conn()
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()
    conn.close()
    return [dict(r) for r in rows]


tab_db, tab_schedules, tab_backup = st.tabs(["📋 Database view", "🌾 Crop schedule builder", "💾 Backup / restore"])


# ---------------------------------------------------------------------
# TAB: Live database view
# ---------------------------------------------------------------------
with tab_db:
    refresh_col, _ = st.columns([1, 5])
    with refresh_col:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    auto = st.checkbox("Auto-refresh every 5s", value=False)

    st.subheader(f"Farmers ({len(db.get_all_farmers())})")
    farmers = db.get_all_farmers()
    if farmers:
        st.dataframe(farmers, use_container_width=True, hide_index=True)
    else:
        st.info("No farmers registered yet.")

    st.subheader("Crop stages")
    stages = fetch_all("crop_stages", "crop, variety, day_offset")
    if stages:
        st.dataframe(stages, use_container_width=True, hide_index=True)
    else:
        st.info("No crop stages defined yet.")

    st.subheader("Pest reports")
    reports = fetch_all("pest_reports", "created_at DESC")
    if reports:
        st.dataframe(reports, use_container_width=True, hide_index=True)
    else:
        st.info("No pest reports logged yet.")

    if auto:
        time.sleep(5)
        st.rerun()


# ---------------------------------------------------------------------
# TAB: Crop schedule builder (moved here from the old admin nav page)
# ---------------------------------------------------------------------
with tab_schedules:
    st.caption(
        "Define the day-by-day operations for a crop, once — every farmer "
        "using that crop+variety inherits the schedule automatically."
    )

    with st.form("add_stage_form"):
        col1, col2 = st.columns(2)
        with col1:
            crop = st.text_input("Crop name", placeholder="e.g. Rice")
            variety = st.text_input("Variety", placeholder="e.g. Generic (Short Duration)")
            day_offset = st.number_input("Days after sowing/transplanting", min_value=0, step=1)
        with col2:
            stage_name = st.text_input("Stage name", placeholder="e.g. Transplanting")
            category = st.selectbox(
                "Category",
                ["sowing", "transplanting", "irrigation", "fertilizer", "pesticide", "weeding", "observation", "harvest"],
            )
            weather_sensitive = st.checkbox("Weather-sensitive (delay if rain/wind)?")
        instructions = st.text_area("Instructions shown to the farmer")

        if st.form_submit_button("Add stage to crop calendar", type="primary"):
            if crop and variety and stage_name and instructions:
                db.add_crop_stage(crop, variety, int(day_offset), stage_name, category, instructions, weather_sensitive)
                st.success(f"Added '{stage_name}' at day {day_offset} for {crop} / {variety}.")
                st.rerun()
            else:
                st.error("Please fill in all fields.")

    st.markdown("---")
    st.subheader("Existing crop calendars")
    crops = db.get_crops()
    crop_filter = st.selectbox("View crop", crops) if crops else None
    if crop_filter:
        for variety in db.get_varieties(crop_filter):
            st.markdown(f"**{crop_filter} — {variety}**")
            schedule = db.get_schedule(crop_filter, variety)
            for s in schedule:
                row_l, row_r = st.columns([6, 1])
                with row_l:
                    weather_tag = " ⛅" if s["weather_sensitive"] else ""
                    st.write(f"Day {s['day_offset']} — **{s['stage_name']}** ({s['category']}){weather_tag}")
                with row_r:
                    if st.button("Delete", key=f"del_{s['id']}", use_container_width=True):
                        db.delete_crop_stage(s["id"])
                        st.rerun()


# ---------------------------------------------------------------------
# TAB: Backup / restore (moved here from the farmer-facing app's sidebar)
# ---------------------------------------------------------------------
with tab_backup:
    if db.USE_POSTGRES:
        st.info("Connected to Postgres via `DATABASE_URL`. Use pgAdmin or `pg_dump`/`pg_restore` for backups instead of this panel.")
    else:
        st.caption("Download a copy of the current SQLite database, or restore from a previously downloaded `.db` file.")

        if os.path.exists(db.DB_PATH):
            with open(db.DB_PATH, "rb") as f:
                st.download_button(
                    "⬇️ Download current database",
                    data=f.read(),
                    file_name="agrischedule.db",
                    mime="application/octet-stream",
                )

        uploaded_db = st.file_uploader("Upload a .db file to restore", type=["db"], key="admin_db_upload")
        if uploaded_db is not None:
            st.warning("This will replace ALL current data (farmers, crop schedules, pest reports) for every user of the app.")
            if st.button("Confirm: replace database with this file", type="primary"):
                with open(db.DB_PATH, "wb") as f:
                    f.write(uploaded_db.getvalue())
                st.success("Database restored.")
                time.sleep(0.6)
                st.rerun()
