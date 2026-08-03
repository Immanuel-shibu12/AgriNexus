# What's in this zip

Everything **I** built or fixed with you in this conversation:

- `app.py` — the farmer-facing app (AgriNexus). Registration, crop
  calendar with month-view + toast alerts, weather advisory, pest
  guidance (upload + live camera), harvest countdown, schemes, Mim
  chat panel, light/dark theme toggle. Database backup/restore has
  been REMOVED from here — it's admin-only now.
- `admin_app.py` — NEW. A separate app, meant to run on its own port,
  for you only. Live database view (farmers / crop stages / pest
  reports, with manual + optional auto-refresh), the crop schedule
  builder (add/delete stages), and database backup/restore.
- `database.py` — shared by both apps. Includes the `USE_POSTGRES`
  flag admin_app.py and app.py both check.
- `custom_mic.py` + `mic_widget/index.html` — the voice-recording
  component (records audio, doesn't transcribe it yet — see note below).
- `.env.example` — every environment variable either app reads.

## ⚠️ What's NOT in this zip — you MUST add these back yourself

I have never received these files from you at any point in this
conversation, so I cannot include them. `app.py` will NOT run without
them — you'll get `ModuleNotFoundError` on startup:

- `schedule_engine.py`
- `weather_utils.py`
- `pest_guidance.py`
- `schemes_data.py`
- `i18n.py`
- `mim_chatbot.py`
- `requirements.txt`

Copy your existing versions of these into the same folder as `app.py`
before running it. If any of them get lost, or you want me to rebuild
one from scratch, paste it to me (or tell me to rebuild it) and I will.

## How to run

Two separate apps, two separate terminals/ports:

```powershell
# Terminal 1 — the app farmers use
streamlit run app.py

# Terminal 2 — your admin console
streamlit run admin_app.py --server.port 8502
```

Set `ADMIN_PASSWORD` in `.env` before running `admin_app.py` for real
use — without it, the admin app will warn you and let you continue
unprotected (fine for local testing, not fine for anything public).

## Still open / things I flagged earlier and haven't done yet

- **Voice-to-text for the mic recording**: `custom_mic.py` returns raw
  audio bytes, but nothing transcribes them yet. You asked which STT
  API to use — I haven't answered that yet (got derailed fixing the
  crash). Ask me again and I'll research current options properly.
- **Two unrelated projects in one folder**: your AGRI folder also had
  `app_user.py`, `admin_dashboard.py`, `model_integration.py`, and
  `reminders.py` from a different project ("AuxGlobal AI"). Those
  aren't part of this zip and I'd strongly recommend moving them to
  their own folder so the two projects stop overwriting each other's
  `database.py`/`custom_mic.py`.
- **Corrupted data**: earlier you hit a crash from a farmer record
  with `sowing_date = 'en'` (leftover bad test data). That row still
  needs fixing/deleting in your actual `.db` file — this zip doesn't
  touch your existing database.
