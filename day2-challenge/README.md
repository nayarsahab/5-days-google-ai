# Day 2 Challenge: BigQuery Release Notes Explorer & Tweet Composer

A sleek, modern web application built using Python Flask, plain vanilla HTML5, CSS3, and JavaScript. The app fetches, parses, and structures the Google Cloud BigQuery Release Notes Atom XML feed, allows search and filtering by update types, and lets users compose and tweet specific updates directly.

## Features

1. **Live XML Parsing**: Retrieves release notes directly from [Google Cloud's Official BigQuery Release Notes Feed](https://docs.cloud.google.com/feeds/bigquery-release-notes.xml).
2. **Granular Update Breakdown**: Automatically parses complex HTML payloads inside each feed entry, splitting them by category (`Feature`, `Announcement`, `Change`, `Breaking`, `Issue`) into individual update cards.
3. **Robust Caching & Fast Loading**: Caches parsed results in memory to avoid hitting rate limits. Refresh trigger allows requesting fresh updates on-demand.
4. **Interactive UI**:
   - Modern dark/glassmorphic interface utilizing custom CSS variables.
   - Dynamic animations (fade-ins, smooth overlays, active tags, and hover card transformations).
   - Sidebar filters to narrow down updates by type.
   - Real-time client-side search across title, date, update text, and type.
   - Responsive design adapting gracefully to desktop and mobile screens.
5. **Interactive Tweet Composer**:
   - Opens a custom X/Twitter-style compose overlay.
   - Automatically drafts a structured tweet template: `BigQuery Update (Date) - [Type]: [Text] #BigQuery #GoogleCloud [Link]`.
   - Automatically truncates content to respect the 280-character limit.
   - Live visual character counter highlighting warnings (orange under 40) and limits (red/disabled button when exceeding 280 characters).
   - Links seamlessly to the Twitter Web Intent portal to complete the share.

## Directory Structure

```
day2-challenge/
│
├── app.py                # Python Flask Application (Routes & XML parser)
├── requirements.txt      # Python dependencies
├── README.md             # Project documentation
│
├── templates/
│   └── index.html        # Main HTML layout, filters, and modal overlay
│
└── static/
    ├── css/
    │   └── style.css     # CSS custom variables, typography, keyframes, and layout
    └── js/
        └── app.js        # Vanilla JS state management, UI rendering, search & filters
```

## Setup & Running the Application

### Prerequisites

- Python 3.8 or higher.
- `pip` (Python Package Installer).

### Installation

1. Navigate to the project directory:
   ```bash
   cd day2-challenge
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # OR on Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

1. Start the Flask server:
   ```bash
   python app.py
   ```

2. Open your web browser and navigate to:
   ```
   http://127.0.0.1:5000/
   ```
## UI/UX Enhancements

This project includes key UI/UX improvements suggested by the Antigravity CLI AI assistant, implemented to maximize visual clarity and device accessibility:
* **Category Icon Indicators**: Embedded visual icons directly into type badges (`fa-circle-check` for Feature, `fa-triangle-exclamation` for Breaking, `fa-circle-info` for Announcement, etc.) to aid speed-scanning and support color-blind users.
* **Grid Optimization**: Replaced the single-column list with a responsive grid (`.cards-grid`) that transitions into dual or triple columns on larger desktop screens (1400px+ and 1900px+), optimizing widescreen layout efficiency.
* **Smooth Color Scheme Transitions**: Applied CSS transitions to backgrounds, colors, borders, and text fields to prevent screen flashing when toggling light/dark themes.

## Development and Stack Details

- **Backend**: Python Flask 3.x, `requests` for fetching, `BeautifulSoup` (via `bs4`) for parsing XML & HTML node traversal.
- **Frontend**: Plain HTML5, CSS3, ES6 JavaScript. No framework overhead (no React, no TailwindCSS, etc.) for lightweight load speeds and maximum performance.
- **Icons**: FontAwesome 6.4.0 (CDN).
- **Typography**: `Outfit` font from Google Fonts.
