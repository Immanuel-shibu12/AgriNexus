"""
AgriSchedule — Smart Crop Calendar & Advisory (MVP / Academic Demo)

Run with:  streamlit run app.py
"""

import calendar as pycalendar
import html
import json
import os
import time
from datetime import date

from dotenv import load_dotenv
load_dotenv()  # must run before mim_chatbot is imported, so it picks up GROK_API_KEY etc.

import streamlit as st
from PIL import Image
import streamlit.components.v1 as components

import database as db
import schedule_engine as se
import weather_utils as wx
import pest_guidance as pg
import mim_chatbot as mim
import reminders
try:
    from streamlit_mic_recorder import mic_recorder
except ImportError:
    mic_recorder = None
from schemes_data import SCHEMES, DISCLAIMER
from i18n import LANGUAGES, t

st.set_page_config(page_title="AgriSchedule", layout="wide")
db.init_db()

OFFLINE_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "offline_cache")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")
os.makedirs(OFFLINE_CACHE_DIR, exist_ok=True)

# Color-codes each crop-stage category consistently wherever it appears
# (currently: the month-grid calendar on the "My Crop Schedule" page).
CATEGORY_COLORS = {
    "sowing": "#22C55E",
    "transplanting": "#3B82F6",
    "weeding": "#F59E0B",
    "fertilizer": "#8B5CF6",
    "pesticide": "#EF4444",
    "irrigation": "#06B6D4",
    "observation": "#9CA3AF",
    "harvest": "#DC2626",
}

# ---------------------------------------------------------------------
# Global theme (card-style panels, rounded widgets — pairs with
# .streamlit/config.toml which sets the dark/green base palette)
# ---------------------------------------------------------------------
st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px !important;
        border-color: rgba(255,255,255,0.08) !important;
    }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 1rem 1.2rem;
    }
    button[kind="primary"] {
        border-radius: 10px !important;
        background-color: #3DA84F !important;
        border-color: #3DA84F !important;
    }
    button[kind="secondary"] {
        border-radius: 10px !important;
    }
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.08);
    }
    [data-testid="stChatMessage"] {
        border-radius: 14px;
        padding: 0.55rem 0.8rem;
        margin-bottom: 0.5rem;
        max-width: 92%;
    }
    /* Messages alternate user/assistant starting with user, so nth-of-type
       parity reliably tells them apart without needing a role attribute. */
    [data-testid="stChatMessage"]:nth-of-type(odd) {
        background: rgba(61, 168, 79, 0.14);
        flex-direction: row-reverse;
        margin-left: auto;
    }
    [data-testid="stChatMessage"]:nth-of-type(odd) [data-testid="stChatMessageContent"] {
        text-align: right;
    }
    [data-testid="stChatMessage"]:nth-of-type(even) {
        background: rgba(255,255,255,0.04);
        margin-right: auto;
    }
    div[data-testid="stExpander"] {
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------
if "farmer_id" not in st.session_state:
    st.session_state.farmer_id = None
if "lang_code" not in st.session_state:
    st.session_state.lang_code = "en"
if "booted" not in st.session_state:
    st.session_state.booted = False
if "mim_history" not in st.session_state:
    st.session_state.mim_history = []
if "mim_pending_speech" not in st.session_state:
    st.session_state.mim_pending_speech = None
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False
if "admin_name" not in st.session_state:
    st.session_state.admin_name = ""
if "admin_cal_offset" not in st.session_state:
    st.session_state.admin_cal_offset = 0
if "admin_selected_date" not in st.session_state:
    st.session_state.admin_selected_date = None


# ---------------------------------------------------------------------
# Splash / loading screen (shown once per browser session)
# ---------------------------------------------------------------------
def show_splash():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="stHeader"] {background: transparent;}
        .block-container {padding-top: 4rem;}
        @keyframes rise {
            0% { transform: scaleY(0.4); opacity: 0.5; }
            100% { transform: scaleY(1); opacity: 1; }
        }
        .splash-mark rect {
            transform-origin: bottom;
            animation: rise 1.1s ease-out;
        }
        .splash-mark rect:nth-child(2) { animation-delay: 0.12s; }
        .splash-mark rect:nth-child(3) { animation-delay: 0.24s; }
        .splash-wrap {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 52vh;
            text-align: center;
        }
        .splash-title {
            margin: 1rem 0 0 0;
            font-size: 2.1rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            color: #E8EDEB;
        }
        .splash-tagline {
            color: #9aa0a6;
            margin-top: 0.3rem;
            font-size: 0.95rem;
        }
        </style>
        <div class="splash-wrap">
            <svg class="splash-mark" width="44" height="44" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="3" y="14" width="5" height="11" rx="1.5" fill="#22A559"/>
                <rect x="11.5" y="8" width="5" height="17" rx="1.5" fill="#22A559"/>
                <rect x="20" y="3" width="5" height="22" rx="1.5" fill="#22A559"/>
            </svg>
            <h1 class="splash-title">AgriSchedule</h1>
            <p class="splash-tagline">Smart Crop Calendar &amp; Advisory</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    progress_col = st.columns([1, 2, 1])[1]
    with progress_col:
        progress_bar = st.progress(0)
        status = st.empty()

        steps = [
            (15, "Waking up the fields..."),
            (40, "Loading crop calendars..."),
            (65, "Checking weather services..."),
            (85, "Preparing your dashboard..."),
            (100, "Ready!"),
        ]
        for pct, msg in steps:
            status.caption(msg)
            progress_bar.progress(pct)
            time.sleep(0.35)

    st.session_state.booted = True
    st.rerun()


if not st.session_state.booted:
    show_splash()
    st.stop()


def cache_schedule_offline(farmer_id, calendar):
    """Save a JSON snapshot of the farmer's schedule so it can be viewed
    with no internet connection (offline access requirement)."""
    path = os.path.join(OFFLINE_CACHE_DIR, f"farmer_{farmer_id}.json")
    serializable = [
        {**e, "due_date": e["due_date"].isoformat()} for e in calendar
    ]
    with open(path, "w") as f:
        json.dump(serializable, f)


def load_cached_schedule(farmer_id):
    path = os.path.join(OFFLINE_CACHE_DIR, f"farmer_{farmer_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def run_pest_prediction(img):
    """Swap-in point for a trained pest/disease model.

    Drop a trained model file into ./model/ (e.g. model/pest_model.*)
    and load + run it here. Until then, this falls back to the
    built-in heuristic in pest_guidance.py so the app stays fully
    functional. Keeping this wrapper in app.py means pest_guidance.py
    doesn't need to change when the real model is ready.
    """
    has_trained_model = os.path.isdir(MODEL_DIR) and any(
        f.endswith((".pt", ".h5", ".onnx", ".pkl", ".joblib")) for f in os.listdir(MODEL_DIR)
    )

    if has_trained_model:
        # TODO: load the trained model from MODEL_DIR and run real inference
        # once training data/model files are provided.
        pass

    return pg.analyze_image(img)


def farmer_context_for_mim():
    """Build a short context string for Mim: preferred language always,
    plus the active farmer's details when one is selected."""
    parts = []
    lang_label = st.session_state.get("lang_label")
    if lang_label and lang_label != "English":
        parts.append(f"Preferred app language: {lang_label}.")

    if st.session_state.farmer_id:
        farmer = db.get_farmer(st.session_state.farmer_id)
        if farmer:
            parts.append(
                f"Name: {farmer['name']}, Crop: {farmer['crop']} ({farmer['variety']}), "
                f"Location: {farmer['location']}, Sowing date: {farmer['sowing_date']}, "
                f"Field area: {farmer['field_area']} acres."
            )

    return " ".join(parts) if parts else None


# ---------------------------------------------------------------------
# Sidebar: language + navigation
# ---------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
        .brand-row {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 1.1rem;
        }
        .brand-row .brand-mark { display: flex; align-items: center; }
        .brand-row .brand-name {
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            color: #eef1f4;
        }
        .nav-eyebrow {
            font-size: 0.68rem;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #6b7280;
            margin: 0.2rem 0 0.4rem 0.1rem;
        }
        section[data-testid="stSidebar"] div[data-testid="stRadio"] > label { display: none; }
        section[data-testid="stSidebar"] div[data-baseweb="radio"] > div:first-child { display: none; }
        section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 0.15rem; }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label {
            display: flex;
            align-items: center;
            width: 100%;
            padding: 0.5rem 0.7rem;
            border-radius: 9px;
            cursor: pointer;
            color: #c3c9d1;
            font-size: 0.92rem;
            transition: background-color .12s ease, color .12s ease;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
            background-color: rgba(255,255,255,0.05);
            color: #f0f2f4;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
            background-color: rgba(61, 168, 89, 0.16);
            color: #ffffff;
            font-weight: 600;
            box-shadow: inset 3px 0 0 0 #3DA859;
        }
        </style>
        <div class="brand-row">
            <span class="brand-mark">
                <svg width="22" height="22" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="3" y="14" width="5" height="11" rx="1.5" fill="#3DA859"/>
                    <rect x="11.5" y="8" width="5" height="17" rx="1.5" fill="#3DA859"/>
                    <rect x="20" y="3" width="5" height="22" rx="1.5" fill="#3DA859"/>
                </svg>
            </span>
            <span class="brand-name">AgriSchedule</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    lang_label = st.selectbox("Language / ഭാഷ / भाषा", list(LANGUAGES.keys()))
    st.session_state.lang_code = LANGUAGES[lang_label]
    st.session_state.lang_label = lang_label
    lc = st.session_state.lang_code

    nav_options = [
        t("nav_register", lc),
        t("nav_schedule", lc),
        t("nav_weather", lc),
        t("nav_pest", lc),
        t("nav_harvest", lc),
        t("nav_schemes", lc),
        "Admin",
    ]

    st.markdown('<div class="nav-eyebrow">Navigate</div>', unsafe_allow_html=True)
    page = st.radio(
        "Navigate",
        nav_options,
        label_visibility="collapsed",
    )

    st.divider()
    farmers = db.get_all_farmers()
    if farmers:
        options = {f"{f['name']} ({f['crop']}, {f['location']})": f["id"] for f in farmers}
        chosen = st.selectbox("Active farmer profile", ["— none —"] + list(options.keys()))
        if chosen != "— none —":
            st.session_state.farmer_id = options[chosen]
    st.caption("Demo data is stored locally in SQLite (data/agrischedule.db).")

    st.divider()
    if not db.USE_POSTGRES:
        with st.expander("Database backup / restore"):
            st.caption("Download a copy of the current database, or restore from a previously downloaded `.db` file.")

            if os.path.exists(db.DB_PATH):
                with open(db.DB_PATH, "rb") as f:
                    st.download_button(
                        "Download current database",
                        data=f.read(),
                        file_name="agrischedule.db",
                        mime="application/octet-stream",
                        width="stretch",
                    )

            uploaded_db = st.file_uploader("Upload a .db file to restore", type=["db"], key="db_upload")
            if uploaded_db is not None:
                st.warning("This will replace all current data (farmers, crop schedules, pest reports).")
                if st.button("Confirm: replace database with this file", width="stretch"):
                    with open(db.DB_PATH, "wb") as f:
                        f.write(uploaded_db.getvalue())
                    st.success("Database restored. Reloading...")
                    st.session_state.farmer_id = None
                    time.sleep(0.6)
                    st.rerun()
    else:
        st.caption("Connected to Postgres via `DATABASE_URL`. Use pgAdmin or `pg_dump` for backups.")


# ---------------------------------------------------------------------
# Main layout: content on the left, Mim assistant pinned on the right
# ---------------------------------------------------------------------
if "mim_open" not in st.session_state:
    st.session_state.mim_open = False

main_col, chat_col = st.columns([3, 1], gap="large")

with chat_col:
    mim_card = st.container(border=True)
    with mim_card:
        status_color = "#16A34A" if mim.is_configured() else "#9CA3AF"
        status_text = "Online" if mim.is_configured() else "Offline"
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:0.1rem;">
                <span style="font-weight:700; font-size:1.15rem;">Mim</span>
                <span style="display:inline-flex; align-items:center; gap:5px; font-size:0.72rem; color:#6b7280;">
                    <span style="width:7px; height:7px; border-radius:50%; background:{status_color}; display:inline-block;"></span>{status_text}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Your AgriSchedule assistant")

        if not st.session_state.mim_open:
            if st.button("Open chat", width="stretch", type="primary"):
                st.session_state.mim_open = True
                st.rerun()
        else:
            if st.button("Close chat", width="stretch"):
                st.session_state.mim_open = False
                st.rerun()

            if not mim.is_configured():
                st.caption("Not connected — set `GROK_API_KEY` in your `.env` file to enable full responses.")

            speak_replies = st.checkbox("Speak replies aloud", value=False, key="mim_speak")

            chat_box = st.container(height=420, border=True)
            with chat_box:
                for msg in st.session_state.mim_history:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])

            def _handle_turn(text):
                st.session_state.mim_history.append({"role": "user", "content": text})
                reply = mim.ask_mim(
                    text,
                    history=st.session_state.mim_history[-6:],
                    context=farmer_context_for_mim(),
                )
                st.session_state.mim_history.append({"role": "assistant", "content": reply})
                if speak_replies:
                    st.session_state.mim_pending_speech = reply
                st.rerun()

            audio = None
            if mic_recorder is not None:
                st.caption("Tap to speak, or type below")
                audio = mic_recorder(start_prompt="Speak", stop_prompt="Stop", just_once=True, key="mim_mic", use_container_width=True)
            else:
                st.caption("Voice input needs `pip install streamlit-mic-recorder`.")
            user_msg = st.chat_input("Ask Mim...")

            if audio and audio.get("bytes"):
                transcript, err = mim.transcribe_audio(audio["bytes"], filename="voice_note.wav")
                if transcript:
                    _handle_turn(transcript)
                elif err:
                    st.caption(err)

            if user_msg:
                _handle_turn(user_msg)

            # Speak the most recent reply aloud via the browser's built-in
            # text-to-speech, then clear it so it doesn't repeat on rerun.
            if st.session_state.get("mim_pending_speech"):
                safe_text = (
                    st.session_state.mim_pending_speech.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
                )
                # Maps this app's language codes (from i18n.LANGUAGES) to BCP-47
                # tags so the browser picks a matching voice/accent when available.
                # If your i18n.py uses different codes than these, update the keys
                # below to match — the value just needs to be a valid BCP-47 tag.
                SPEECH_LANG_TAGS = {
                    "en": "en-US", "hi": "hi-IN", "ml": "ml-IN", "bn": "bn-IN",
                    "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN", "mr": "mr-IN",
                    "gu": "gu-IN", "pa": "pa-IN", "or": "or-IN", "as": "as-IN",
                }
                speech_lang = SPEECH_LANG_TAGS.get(lc, "en-US")
                components.html(
                    f"""<script>
                        const u = new SpeechSynthesisUtterance("{safe_text}");
                        u.lang = "{speech_lang}";
                        window.speechSynthesis.cancel();
                        window.speechSynthesis.speak(u);
                    </script>""",
                    height=0,
                )
                st.session_state.mim_pending_speech = None

with main_col:
    st.title(t("app_title", lc))

    # -------------------------------------------------------------
    # PAGE: Farmer Registration
    # -------------------------------------------------------------
    if page == t("nav_register", lc):
        st.header(t("nav_register", lc))
        crops = db.get_crops()

        # -----------------------------------------------------------
        # Hero / insights strip, styled after the Zenze-style landing
        # page reference: eyebrow tag, bold headline, then a row of
        # quick stats pulled from the live farmer data.
        # -----------------------------------------------------------
        _hero_farmers = db.get_all_farmers()
        _hero_total = len(_hero_farmers)
        _hero_acres = round(sum(f["field_area"] or 0 for f in _hero_farmers), 1)
        _hero_crops = len({f["crop"] for f in _hero_farmers if f["crop"]})
        _hero_locations = len({f["location"] for f in _hero_farmers if f["location"]})

        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg, rgba(34,165,89,0.18), rgba(255,255,255,0.02));
                border: 1px solid rgba(61,168,89,0.35);
                border-radius: 18px;
                padding: 1.5rem 1.7rem;
                margin-bottom: 1.3rem;
            ">
                <div style="font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase;
                            color:#3DA859; font-weight:700; margin-bottom:0.35rem;">
                    Smart solutions for a better tomorrow
                </div>
                <div style="font-size:1.55rem; font-weight:700; color:#eef1f4; line-height:1.25; margin-bottom:0.25rem;">
                    Nurturing Fields.<br>Empowering Farmers.
                </div>
                <div style="color:#a9b0b8; font-size:0.9rem; margin-bottom:1.1rem; max-width:520px;">
                    Register a farmer profile to start tracking their crop calendar,
                    weather advisory and pest guidance in one place.
                </div>
                <div style="display:flex; gap:2rem; flex-wrap:wrap;">
                    <div>
                        <div style="font-size:1.35rem; font-weight:700; color:#ffffff;">{_hero_total}</div>
                        <div style="font-size:0.75rem; color:#8b939c;">Farmers registered</div>
                    </div>
                    <div>
                        <div style="font-size:1.35rem; font-weight:700; color:#ffffff;">{_hero_acres}</div>
                        <div style="font-size:0.75rem; color:#8b939c;">Acres managed</div>
                    </div>
                    <div>
                        <div style="font-size:1.35rem; font-weight:700; color:#ffffff;">{_hero_crops}</div>
                        <div style="font-size:0.75rem; color:#8b939c;">Crop types tracked</div>
                    </div>
                    <div>
                        <div style="font-size:1.35rem; font-weight:700; color:#ffffff;">{_hero_locations}</div>
                        <div style="font-size:0.75rem; color:#8b939c;">Locations covered</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("registration_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input(t("name", lc))
                phone = st.text_input("Phone number", placeholder="e.g. +91 98765 43210")
                location = st.text_input(t("location", lc), placeholder="e.g. Thrissur, Kerala")
                crop = st.selectbox(t("crop", lc), crops)
                variety = st.selectbox(t("variety", lc), db.get_varieties(crop) if crop else [])
            with col2:
                field_area = st.number_input(t("field_area", lc), min_value=0.1, value=1.0, step=0.1)
                sowing_date = st.date_input(t("sowing_date", lc), value=date.today())
                preferred_lang = lc

            st.caption("Phone number is used only to send schedule reminders by SMS or call.")
            submitted = st.form_submit_button(t("register_btn", lc))

            if submitted:
                if not name or not location:
                    st.error("Please fill in name and location.")
                else:
                    geo = wx.geocode_location(location)
                    lat = geo["latitude"] if geo else None
                    lon = geo["longitude"] if geo else None

                    farmer_id = db.add_farmer(
                        name, phone.strip() or None, location, lat, lon, crop, variety,
                        field_area, sowing_date.isoformat(), preferred_lang,
                    )
                    st.session_state.farmer_id = farmer_id
                    st.success(f"Registered! Welcome, {name}. Your farmer profile ID is {farmer_id}.")
                    if not geo:
                        st.warning(
                            "Couldn't resolve exact coordinates for this location right now "
                            "(needed for the weather advisory) — you can still use the app; "
                            "we'll retry geocoding when the connection is available."
                        )
                    st.rerun()

    # -------------------------------------------------------------
    # PAGE: My Crop Schedule (notifications feed)
    # -------------------------------------------------------------
    elif page == t("nav_schedule", lc):
        st.header(t("nav_schedule", lc))

        if not st.session_state.farmer_id:
            st.warning("Select or register a farmer profile from the sidebar first.")
        else:
            farmer = db.get_farmer(st.session_state.farmer_id)
            stages = db.get_schedule(farmer["crop"], farmer["variety"])
            calendar = se.build_calendar(farmer["sowing_date"], stages)

            weather_flag = {"rain_today": False, "high_wind_today": False, "available": False}
            if farmer["latitude"] and farmer["longitude"]:
                forecast = wx.get_forecast(farmer["latitude"], farmer["longitude"], days=3)
                weather_flag = wx.get_today_flags(forecast)
            calendar = se.apply_weather_override(calendar, weather_flag)

            cache_schedule_offline(farmer["id"], calendar)

            notifications = se.get_notifications(calendar)

            st.subheader(f"Upcoming reminders for {farmer['name']} — {farmer['crop']} ({farmer['variety']})")
            if not notifications:
                st.info("Nothing due in the next few days. Check back later.")
            status_colors = {"today": "#D97706", "overdue": "#DC2626", "upcoming": "#16A34A"}
            for idx, n in enumerate(notifications):
                dot_color = status_colors[n["status"]]
                with st.container(border=True):
                    st.markdown(
                        f'<span style="display:inline-block; width:8px; height:8px; border-radius:50%; '
                        f'background:{dot_color}; margin-right:8px;"></span>'
                        f"**{n['stage_name']}** — due {n['due_date'].strftime('%d %b %Y')} ({n['status']})",
                        unsafe_allow_html=True,
                    )
                    st.caption(n["instructions"])
                    if n.get("weather_warning"):
                        st.warning(n["weather_warning"])

                    if n["status"] == "overdue":
                        reminder_text = (
                            f"Reminder for {farmer['name']}: '{n['stage_name']}' for your "
                            f"{farmer['crop']} was due on {n['due_date'].strftime('%d %b %Y')}. "
                            f"{n['instructions']}"
                        )
                        rcol1, rcol2 = st.columns(2)
                        with rcol1:
                            if st.button("Send text reminder", key=f"sms_{idx}", width="stretch"):
                                ok, detail = reminders.send_sms(farmer.get("phone"), reminder_text)
                                (st.success if ok else st.error)(detail)
                        with rcol2:
                            if st.button("Call reminder", key=f"call_{idx}", width="stretch"):
                                ok, detail = reminders.make_call(farmer.get("phone"), reminder_text)
                                (st.success if ok else st.error)(detail)

            st.markdown("---")
            st.subheader("Full crop calendar")

            st.markdown(
                """
                <style>
                .cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:6px; margin-bottom:0.4rem; }
                .cal-head {
                    text-align:center; font-size:0.7rem; text-transform:uppercase;
                    letter-spacing:0.05em; color:#8b939c; padding-bottom:2px;
                }
                .cal-cell {
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 10px;
                    min-height: 90px;
                    padding: 6px;
                }
                .cal-cell.other-month { opacity: 0.32; }
                .cal-cell.is-today { border-color: #3DA859; box-shadow: inset 0 0 0 1px #3DA859; }
                .cal-daynum { font-size: 0.76rem; color: #c3c9d1; text-align:right; margin-bottom:4px; }
                .cal-cell.is-today .cal-daynum { color: #3DA859; font-weight:700; }
                .cal-chip {
                    font-size: 0.66rem; line-height:1.25; padding: 2px 5px 2px 6px;
                    border-radius: 5px; margin-bottom: 3px; white-space: nowrap;
                    overflow: hidden; text-overflow: ellipsis;
                }
                .cal-legend-dot {
                    display:inline-block; width:8px; height:8px; border-radius:50%;
                    margin-right:5px;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            # Reset the visible month whenever the active farmer changes.
            if st.session_state.get("sched_cal_farmer") != farmer["id"]:
                st.session_state.sched_cal_offset = 0
                st.session_state.sched_cal_farmer = farmer["id"]
            if "sched_cal_offset" not in st.session_state:
                st.session_state.sched_cal_offset = 0

            anchor = date.fromisoformat(farmer["sowing_date"])
            month_index = (anchor.month - 1) + st.session_state.sched_cal_offset
            view_year = anchor.year + month_index // 12
            view_month = month_index % 12 + 1

            nav_prev, nav_label, nav_next = st.columns([1, 4, 1])
            with nav_prev:
                if st.button("‹", key="sched_cal_prev", width="stretch"):
                    st.session_state.sched_cal_offset -= 1
                    st.rerun()
            with nav_label:
                st.markdown(
                    f'<div style="text-align:center; font-weight:700; padding-top:0.3rem;">'
                    f'{date(view_year, view_month, 1).strftime("%B %Y")}</div>',
                    unsafe_allow_html=True,
                )
            with nav_next:
                if st.button("›", key="sched_cal_next", width="stretch"):
                    st.session_state.sched_cal_offset += 1
                    st.rerun()

            events_by_date = {}
            for e in calendar:
                events_by_date.setdefault(e["due_date"], []).append(e)

            today_marker = date.today()
            weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            cells_html = "".join(f'<div class="cal-head">{wl}</div>' for wl in weekday_labels)

            cal_gen = pycalendar.Calendar(firstweekday=0)
            for week in cal_gen.monthdatescalendar(view_year, view_month):
                for day in week:
                    classes = ["cal-cell"]
                    if day.month != view_month:
                        classes.append("other-month")
                    if day == today_marker:
                        classes.append("is-today")

                    chips = ""
                    for ev in events_by_date.get(day, []):
                        chip_color = CATEGORY_COLORS.get(ev["category"], "#9CA3AF")
                        chips += (
                            f'<div class="cal-chip" style="background:{chip_color}26; '
                            f'color:{chip_color}; border-left:3px solid {chip_color};" '
                            f'title="{html.escape(ev["stage_name"])}">'
                            f'{html.escape(ev["stage_name"])}</div>'
                        )

                    cells_html += (
                        f'<div class="{" ".join(classes)}">'
                        f'<div class="cal-daynum">{day.day}</div>{chips}</div>'
                    )

            st.markdown(f'<div class="cal-grid">{cells_html}</div>', unsafe_allow_html=True)

            legend_bits = "".join(
                f'<span style="margin-right:14px; font-size:0.75rem; color:#c3c9d1;">'
                f'<span class="cal-legend-dot" style="background:{color};"></span>{cat.capitalize()}</span>'
                for cat, color in CATEGORY_COLORS.items()
            )
            st.markdown(f'<div style="margin:0.6rem 0 1rem 0;">{legend_bits}</div>', unsafe_allow_html=True)

            with st.expander("View as a simple table"):
                st.dataframe(
                    [
                        {
                            "Day": e["day_offset"],
                            "Date": e["due_date"].strftime("%d %b %Y"),
                            "Stage": e["stage_name"],
                            "Category": e["category"],
                            "Status": e["status"],
                        }
                        for e in calendar
                    ],
                    width="stretch", hide_index=True,
                )

            st.caption(
                "This calendar's data stays available **offline** — it's cached to "
                "`data/offline_cache/` on registration/first load, so a farmer with previously "
                "downloaded schedules can still check tasks without a live connection."
            )

    # -------------------------------------------------------------
    # PAGE: Weather Advisory
    # -------------------------------------------------------------
    elif page == t("nav_weather", lc):
        st.header(t("nav_weather", lc))

        if not st.session_state.farmer_id:
            st.warning("Select or register a farmer profile from the sidebar first.")
        else:
            farmer = db.get_farmer(st.session_state.farmer_id)
            if not farmer["latitude"] or not farmer["longitude"]:
                st.error("No coordinates saved for this farmer's location yet. Try re-registering, or check your connection.")
            else:
                forecast = wx.get_forecast(farmer["latitude"], farmer["longitude"], days=7)
                if not forecast:
                    st.error("Couldn't reach the weather service right now. Showing last known advisory logic only.")
                else:
                    flags = wx.get_today_flags(forecast)
                    st.subheader(f"Next 7 days — {farmer['location']}")

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Rain today?", "Yes" if flags["rain_today"] else "No",
                               f"{flags.get('precip_mm', 0)} mm")
                    c2.metric("High wind today?", "Yes" if flags["high_wind_today"] else "No",
                               f"{flags.get('wind_kmh', 0)} km/h")
                    c3.metric("Max temp today", f"{forecast['temperature_2m_max'][0]} °C")

                    st.markdown("### Advisory")
                    if flags["rain_today"]:
                        st.warning("Rain expected/occurring today: **skip irrigation** and **delay pesticide spraying** (wash-off risk).")
                    if flags["high_wind_today"]:
                        st.warning("Strong winds today: **delay spraying** — drift risk and poor coverage.")
                    if not flags["rain_today"] and not flags["high_wind_today"]:
                        st.success("Conditions look normal today — scheduled operations can proceed as planned.")

                    st.markdown("### 7-day outlook")
                    st.dataframe(
                        {
                            "Date": forecast["time"],
                            "Rain (mm)": forecast["precipitation_sum"],
                            "Wind (km/h)": forecast["windspeed_10m_max"],
                            "Max °C": forecast["temperature_2m_max"],
                            "Min °C": forecast["temperature_2m_min"],
                        },
                        width="stretch", hide_index=True,
                    )

    # -------------------------------------------------------------
    # PAGE: Pest & Disease Guidance
    # -------------------------------------------------------------
    elif page == t("nav_pest", lc):
        st.header(t("nav_pest", lc))
        st.caption(
            "Upload a photo, or use your camera, of the affected leaf/plant. This demo "
            "uses a lightweight offline colour-heuristic when no trained model is present "
            "(works with no internet) — drop a trained model into `model/` once it's ready "
            "and `run_pest_prediction()` in app.py will pick it up automatically."
        )

        source = st.radio("Image source", ["Upload a photo", "Use camera"], horizontal=True)
        uploaded = None
        if source == "Upload a photo":
            uploaded = st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png"])
        else:
            uploaded = st.camera_input("Take a photo of the affected leaf/plant")

        if uploaded:
            img = Image.open(uploaded)
            col1, col2 = st.columns([1, 1.3])
            with col1:
                st.image(img, caption="Photo", width="stretch")
            with col2:
                result = run_pest_prediction(img)
                st.subheader(result["label"])
                st.progress(result["confidence"])
                st.caption(f"Confidence: {int(result['confidence']*100)}% (heuristic estimate, not a lab diagnosis)")
                st.markdown(result["guidance"])

                if st.session_state.farmer_id:
                    image_name = getattr(uploaded, "name", "camera_capture.jpg")
                    db.log_pest_report(st.session_state.farmer_id, image_name, result["label"], result["confidence"])
                    st.success("Saved to this farmer's pest report history.")

        st.markdown("---")
        st.subheader("Quick reference: common issues")
        for key, entry in pg.KNOWLEDGE_BASE.items():
            with st.expander(entry["label"]):
                st.write(entry["guidance"])

    # -------------------------------------------------------------
    # PAGE: Harvest Countdown
    # -------------------------------------------------------------
    elif page == t("nav_harvest", lc):
        st.header(t("nav_harvest", lc))

        if not st.session_state.farmer_id:
            st.warning("Select or register a farmer profile from the sidebar first.")
        else:
            farmer = db.get_farmer(st.session_state.farmer_id)
            stages = db.get_schedule(farmer["crop"], farmer["variety"])
            calendar = se.build_calendar(farmer["sowing_date"], stages)
            harvest_info = se.get_harvest_info(calendar)

            if not harvest_info:
                st.info("No harvest stage defined for this crop/variety yet.")
            else:
                days_left = harvest_info["days_left"]
                st.metric(
                    "Estimated harvest date",
                    harvest_info["harvest_date"].strftime("%d %b %Y"),
                    f"{days_left} days left" if days_left >= 0 else f"{abs(days_left)} days overdue",
                )
                if days_left > 0:
                    st.progress(max(0.0, min(1.0, 1 - days_left / max(stages[-1]["day_offset"], 1))))
                st.caption(f"Final stage tracked: {harvest_info['stage_name']}")

    # -------------------------------------------------------------
    # PAGE: Government Schemes
    # -------------------------------------------------------------
    elif page == t("nav_schemes", lc):
        st.header(t("nav_schemes", lc))
        st.info(DISCLAIMER)
        for s in SCHEMES:
            with st.container(border=True):
                st.subheader(s["name"])
                st.write(s["summary"])
                st.caption(f"Who it's for: {s['who']}")
                st.markdown(f"[Official portal]({s['link']})")

    # -------------------------------------------------------------
    # PAGE: Admin (internal — registered farmers dataset view)
    # -------------------------------------------------------------
    elif page == "Admin":
        # -----------------------------------------------------------
        # Light theme for the whole Admin section (login screen and
        # dashboard alike) — scoped to this branch only, since the CSS
        # is only injected while this page is being rendered, so it
        # never leaks onto the other (dark-themed) pages of the app.
        # -----------------------------------------------------------
        st.markdown(
            """
            <style>
            [data-testid="stAppViewContainer"] .main .block-container {
                background: #F3F4F6;
                border-radius: 20px;
                padding: 1.4rem 1.7rem 2rem 1.7rem;
            }
            [data-testid="stAppViewContainer"] .main h1,
            [data-testid="stAppViewContainer"] .main h2,
            [data-testid="stAppViewContainer"] .main h3,
            [data-testid="stAppViewContainer"] .main p,
            [data-testid="stAppViewContainer"] .main label,
            [data-testid="stAppViewContainer"] .main span {
                color: #111827;
            }
            [data-testid="stAppViewContainer"] .main div[data-testid="stVerticalBlockBorderWrapper"] {
                background: #ffffff !important;
                border-color: rgba(17,24,39,0.08) !important;
            }
            .admin-card {
                background: #ffffff;
                border-radius: 18px;
                padding: 1.1rem 1.3rem;
                box-shadow: 0 2px 10px rgba(17,24,39,0.06);
                border: 1px solid rgba(17,24,39,0.06);
                margin-bottom: 1rem;
            }
            .admin-card, .admin-card * { color: #111827 !important; }
            .admin-muted { color: #6b7280 !important; font-size: 0.78rem; }
            .admin-stat-value { font-size: 1.5rem; font-weight: 700; color: #111827 !important; }
            .admin-greet-bar {
                background: #111827;
                border-radius: 18px;
                padding: 1.1rem 1.4rem;
                margin-bottom: 1rem;
            }
            .admin-greet-bar, .admin-greet-bar * { color: #ffffff !important; }
            .admin-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
            .admin-table th {
                text-align: left; color: #6b7280 !important; font-size: 0.7rem;
                text-transform: uppercase; letter-spacing: 0.05em;
                padding: 0.5rem 0.5rem; border-bottom: 1px solid #E5E7EB;
            }
            .admin-table td {
                padding: 0.55rem 0.5rem; color: #111827 !important;
                border-bottom: 1px solid #F0F1F3;
            }
            .admin-login-card {
                max-width: 380px;
                margin: 2.5rem auto 0 auto;
                background: #ffffff;
                border-radius: 20px;
                padding: 2rem 2rem 0.5rem 2rem;
                box-shadow: 0 10px 30px rgba(0,0,0,0.35);
                text-align: center;
            }
            .admin-login-card h2 { color: #111827 !important; margin-bottom: 0.2rem; }
            .admin-login-card p { color: #6b7280 !important; font-size: 0.85rem; margin-bottom: 0.4rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # -----------------------------------------------------------
        # Gate: name + fixed demo passcode ("0000"). This is a demo
        # separator for the internal view only, not real authentication.
        # -----------------------------------------------------------
        if not st.session_state.admin_authenticated:
            st.markdown(
                """
                <div class="admin-login-card">
                    <h2>Admin sign in</h2>
                    <p>Internal view — enter your name and the admin passcode.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            _, login_col, _ = st.columns([1, 1.2, 1])
            with login_col:
                login_card = st.container(border=True)
                with login_card:
                    with st.form("admin_login_form"):
                        admin_name_input = st.text_input("Name")
                        admin_password_input = st.text_input("Password", type="password", placeholder="••••")
                        login_submitted = st.form_submit_button(
                            "Sign in", width="stretch", type="primary"
                        )
                        if login_submitted:
                            if not admin_name_input.strip():
                                st.error("Please enter your name.")
                            elif admin_password_input != "0000":
                                st.error("Incorrect password.")
                            else:
                                st.session_state.admin_authenticated = True
                                st.session_state.admin_name = admin_name_input.strip()
                                st.rerun()

        # -----------------------------------------------------------
        # Dashboard — light theme styled after the reference dashboard:
        # greeting bar, stat cards, farmer table on the left; a sowing
        # calendar on the right. All CSS/markup here is only injected
        # while this branch runs, so it never leaks onto the other
        # (dark-themed) pages of the app.
        # -----------------------------------------------------------
        else:
            top_l, top_r = st.columns([4, 1])
            with top_l:
                st.markdown(
                    f"""
                    <div class="admin-greet-bar">
                        <div style="font-size:1.2rem; font-weight:700;">Hello, {html.escape(st.session_state.admin_name)}! 👋</div>
                        <div style="font-size:0.85rem; opacity:0.75;">Here's what's happening across your farmer network.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with top_r:
                st.write("")
                if st.button("Log out", width="stretch"):
                    st.session_state.admin_authenticated = False
                    st.rerun()

            all_farmers = farmers or []
            search_term = st.text_input("🔍 Search farmers by name, crop or location", key="admin_search")
            search_term = (search_term or "").strip().lower()
            if search_term:
                filtered_farmers = [
                    f for f in all_farmers
                    if search_term in (f["name"] or "").lower()
                    or search_term in (f["crop"] or "").lower()
                    or search_term in (f["location"] or "").lower()
                ]
            else:
                filtered_farmers = all_farmers

            total_farmers = len(all_farmers)
            total_acres = round(sum(f["field_area"] or 0 for f in all_farmers), 1)
            crop_types = len({f["crop"] for f in all_farmers if f["crop"]})
            locations = len({f["location"] for f in all_farmers if f["location"]})

            dash_col, cal_col = st.columns([2, 1], gap="large")

            # ---------------- left: stats + farmer records ----------------
            with dash_col:
                st.markdown('<div class="admin-muted">OVERVIEW</div>', unsafe_allow_html=True)
                s1, s2, s3, s4 = st.columns(4)
                for cell, label, value in (
                    (s1, "Farmers", total_farmers),
                    (s2, "Acres managed", total_acres),
                    (s3, "Crop types", crop_types),
                    (s4, "Locations", locations),
                ):
                    with cell:
                        st.markdown(
                            f"""<div class="admin-card" style="text-align:center; margin-bottom:0.8rem;">
                                    <div class="admin-stat-value">{value}</div>
                                    <div class="admin-muted">{label}</div>
                                </div>""",
                            unsafe_allow_html=True,
                        )

                st.markdown('<div class="admin-muted" style="margin:0.6rem 0 0.4rem 0;">FARMER RECORDS</div>', unsafe_allow_html=True)
                if filtered_farmers:
                    rows_html = "".join(
                        "<tr>"
                        f"<td>{f['id']}</td>"
                        f"<td>{html.escape(f['name'] or '')}</td>"
                        f"<td>{html.escape(f.get('phone') or '—')}</td>"
                        f"<td>{html.escape(f['location'] or '')}</td>"
                        f"<td>{html.escape(f['crop'] or '')}</td>"
                        f"<td>{html.escape(f['variety'] or '')}</td>"
                        f"<td>{f['field_area']}</td>"
                        f"<td>{f['sowing_date']}</td>"
                        "</tr>"
                        for f in filtered_farmers
                    )
                    st.markdown(
                        f"""
                        <div class="admin-card" style="padding:0.5rem 0.7rem; overflow-x:auto;">
                        <table class="admin-table">
                            <thead>
                                <tr>
                                    <th>ID</th><th>Name</th><th>Phone</th><th>Location</th>
                                    <th>Crop</th><th>Variety</th><th>Area (ac)</th><th>Sowing date</th>
                                </tr>
                            </thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown('<div class="admin-card">No matching farmer records.</div>', unsafe_allow_html=True)

            # ---------------- right: sowing calendar panel ----------------
            with cal_col:
                st.markdown('<div class="admin-card">', unsafe_allow_html=True)
                st.markdown(
                    '<div style="font-weight:700; font-size:1.05rem; margin-bottom:0.15rem;">Sowing calendar</div>'
                    '<div class="admin-muted" style="margin-bottom:0.6rem;">Pick a date to see who sowed that day</div>',
                    unsafe_allow_html=True,
                )

                today = date.today()
                month_index = (today.month - 1) + st.session_state.admin_cal_offset
                view_year = today.year + month_index // 12
                view_month = month_index % 12 + 1

                nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
                with nav_prev:
                    if st.button("‹", key="admin_cal_prev", width="stretch"):
                        st.session_state.admin_cal_offset -= 1
                        st.rerun()
                with nav_label:
                    st.markdown(
                        f'<div style="text-align:center; font-weight:600; padding-top:0.4rem;">'
                        f'{date(view_year, view_month, 1).strftime("%B %Y")}</div>',
                        unsafe_allow_html=True,
                    )
                with nav_next:
                    if st.button("›", key="admin_cal_next", width="stretch"):
                        st.session_state.admin_cal_offset += 1
                        st.rerun()

                sow_dates = set()
                for f in all_farmers:
                    try:
                        sow_dates.add(date.fromisoformat(f["sowing_date"]))
                    except (TypeError, ValueError):
                        pass

                weekday_cols = st.columns(7)
                for wc, wlabel in zip(weekday_cols, ["S", "M", "T", "W", "T", "F", "S"]):
                    wc.markdown(f'<div class="admin-muted" style="text-align:center;">{wlabel}</div>', unsafe_allow_html=True)

                cal = pycalendar.Calendar(firstweekday=6)
                for week in cal.monthdatescalendar(view_year, view_month):
                    week_cols = st.columns(7)
                    for wc, day in zip(week_cols, week):
                        in_month = day.month == view_month
                        has_sowing = day in sow_dates and in_month
                        is_selected = st.session_state.admin_selected_date == day
                        with wc:
                            if st.button(
                                str(day.day),
                                key=f"admin_cal_{day.isoformat()}",
                                width="stretch",
                                type="primary" if is_selected else "secondary",
                                disabled=not in_month,
                            ):
                                st.session_state.admin_selected_date = day
                                st.rerun()
                            if has_sowing:
                                st.markdown(
                                    '<div style="text-align:center; margin-top:-0.55rem;">'
                                    '<span style="display:inline-block; width:5px; height:5px; '
                                    'border-radius:50%; background:#22C55E;"></span></div>',
                                    unsafe_allow_html=True,
                                )

                st.markdown(
                    '<div class="admin-muted" style="margin-top:0.5rem;">'
                    '<span style="color:#22C55E;">●</span> has sowing activity</div>',
                    unsafe_allow_html=True,
                )

                if st.session_state.admin_selected_date:
                    sel = st.session_state.admin_selected_date
                    st.markdown(
                        f'<div style="margin-top:0.9rem; font-weight:600;">Sowed on {sel.strftime("%d %b %Y")}</div>',
                        unsafe_allow_html=True,
                    )
                    matches = [f for f in all_farmers if f["sowing_date"] == sel.isoformat()]
                    if matches:
                        for m in matches:
                            st.markdown(
                                f'<div class="admin-muted">🌱 {html.escape(m["name"])} — '
                                f'{html.escape(m["crop"] or "")} ({html.escape(m["location"] or "")})</div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown('<div class="admin-muted">No farmers sowed on this date.</div>', unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)