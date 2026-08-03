# AgriNexus

A smart crop planning and advisory platform for farmers, built with Streamlit. It helps users manage crop schedules, monitor weather risks, access scheme information, get pest guidance, and interact with an AI assistant for agricultural support.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/Status-Open%20Project-4CAF50?style=for-the-badge)

## Overview

AgriNexus brings together:

- Farmer registration and crop tracking
- Seasonal crop calendar and reminders
- Weather-based advisory support
- Pest and disease guidance
- Government scheme discovery
- AI-powered assistant with multilingual support
- Admin dashboard for operational oversight

## Key Features

### Farmer Experience
- Personalized crop scheduling
- Alerts for upcoming field activities
- Weather and advisory summaries
- Harvest countdown and reminders
- Scheme recommendations and eligibility info
- Chat-style agricultural assistant

### Admin Experience
- Monitor farmer records
- Review crop stages and pest reports
- Manage database operations
- Configure schedule logic and operational data

## Project Structure

```text
AgriNexus/
├── app.py                  # Main farmer-facing app
├── admin_app.py           # Admin console
├── database.py            # Shared database layer
├── schedule_engine.py     # Crop-stage logic and scheduling
├── weather_utils.py       # Weather fetch and helpers
├── pest_guidance.py       # Pest and disease guidance
├── mim_chatbot.py         # AI chat integration
├── reminders.py           # Notification/reminder logic
├── schemes_data.py        # Government scheme definitions
├── i18n.py                # Localization support
├── requirements.txt       # Python dependencies
├── config.toml            # Streamlit theme config
├── data/                  # Local database and cached data
├── README.md              # Project documentation
├── .gitignore             # Git hygiene rules
└── .env.example           # Sample environment variables
```

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Immanuel-shibu12/AgriNexus.git
cd AgriNexus
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file using the required variables:

```env
GROK_API_KEY=your_api_key_here
ADMIN_PASSWORD=your_admin_password
```

### 5. Run the apps

Launch the farmer-facing app:

```bash
streamlit run app.py
```

Launch the admin dashboard on a separate port:

```bash
streamlit run admin_app.py --server.port 8502
```

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `GROK_API_KEY` | Yes for AI chat features | Enables chat and voice-related responses |
| `ADMIN_PASSWORD` | Recommended for admin access | Locks down the admin dashboard |

## Notes

- The app expects a local SQLite database and can use offline cached schedule data when needed.
- The admin experience is intentionally separated for controlled access and operational management.
- For production use, keep secrets in a secure environment and avoid committing `.env` files.

## Recommended Next Improvements

- Add automated tests for schedule logic and database workflows
- Harden admin authentication and role-based access control
- Expand multilingual support and scheme filters
- Introduce real pestclassification model integration
- Add deployment support for Docker or cloud hosting

## License

This project is intended for local use and demonstration purposes unless a separate project license is added.

## Contact

For upgrades, bug fixes, or feature discussions, use the project repository issues or discussion section.
