"""
AgriSchedule — Smart Crop Calendar & Advisory (MVP / Academic Demo)

Run with:  streamlit run app.py
"""

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
                "This full calendar view is what stays available **offline** — it's cached to "
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
        st.header("Admin")
        st.caption("Internal view of all registered farmer records.")
        if farmers:
            st.dataframe(
                [{k: f[k] for k in ("id", "name", "phone", "location", "crop", "variety", "field_area", "sowing_date")} for f in farmers],
                width="stretch", hide_index=True,
            )
        else:
            st.info("No farmers registered yet.")