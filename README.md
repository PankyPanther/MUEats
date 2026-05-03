# MUEats — Miami University Meal Planner

Flask + MongoDB + Selenium web scraper for Miami University dining.

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

---

## Making the Scraper Work (Required for Live Data)

The scraper drives a real browser to pull today's menu from
`dineoncampus.com/MiamiUniversity`. It needs either Firefox or Chrome installed.

### Option A — Firefox (recommended)

```bash
# macOS
brew install firefox

# Ubuntu/Debian
sudo apt install firefox

# Windows — download from https://www.mozilla.org/firefox/
```

geckodriver is downloaded automatically by `webdriver-manager`.

### Option B — Chrome / Chromium

```bash
# macOS
brew install --cask google-chrome

# Ubuntu
sudo apt install chromium-browser

# Windows — download from https://www.google.com/chrome/
```

chromedriver is downloaded automatically by `webdriver-manager`.

### Running the scraper

**Automatic** — the app checks on startup if today's data is loaded.
If not, it scrapes automatically in the background. It also re-scrapes every
night at midnight so data is always current.

**Manual from dashboard** — go to the Scraper page in the sidebar → pick
today's date → click Run Scraper Now.

**Manual from command line:**
```bash
# Scrape today (default)
python scraper_main.py

# Scrape a specific date
python scraper_main.py 2026-04-30

# Run headless (no browser window)
python scraper_main.py --headless

# Via the API
curl -X POST http://localhost:5000/api/scraper/run \
     -H "Content-Type: application/json" \
     -d '{"date":"2026-04-30"}'
```

---

## MongoDB Setup

Runs without MongoDB by default (in-memory storage).
To enable MongoDB persistence:

1. Copy `.env.example` to `.env` and set:
   ```
   USE_MONGO=true
   MONGO_URI=mongodb://localhost:27017/
   ```
2. All MongoDB queries are pre-written in `app.py` as comments — just uncomment.

### Collections

| Collection  | Holds                                            |
|-------------|--------------------------------------------------|
| `users`     | Email, name, hashed password, macro goals        |
| `meals`     | Dining hall items + macros + scraped date        |
| `meal_log`  | Per-user daily meal selections                   |

---

## API Reference

| Method | Endpoint                  | Description                           |
|--------|---------------------------|---------------------------------------|
| GET    | `/`                       | Login page                            |
| GET    | `/dashboard`              | Dashboard UI                          |
| POST   | `/api/auth/login`         | Login (Miami email only)              |
| POST   | `/api/auth/signup`        | Create account (Miami email only)     |
| POST   | `/api/auth/logout`        | Log out                               |
| GET    | `/api/user`               | Current user + goals + consumed today |
| PATCH  | `/api/goals`              | Update macro goals                    |
| PATCH  | `/api/body`               | Update body info (height/weight/age)  |
| GET    | `/api/recommendations`    | BMR/TDEE-based macro recommendations  |
| GET    | `/api/meals`              | All meals, scored + filtered          |
| GET    | `/api/restaurants`        | List of dining hall names             |
| GET    | `/api/periods`            | List of meal periods                  |
| GET    | `/api/suggestions`        | Top green-tier matches for user       |
| GET    | `/api/meal_log`           | Today's logged meals                  |
| POST   | `/api/meal_log`           | Log a meal                            |
| DELETE | `/api/meal_log/<id>`      | Remove a logged meal                  |
| POST   | `/api/scraper/run`        | Trigger scraper for a date            |
| GET    | `/api/scraper/status`     | Scraper data status + item counts     |
| GET    | `/api/stats`              | Live progress stats                   |

---

## Tier Scoring

Each meal is scored 0–100 against 1/3 of the user's daily goals:

| Macro    | Weight |
|----------|--------|
| Protein  | 40%    |
| Calories | 30%    |
| Carbs    | 20%    |
| Fat      | 10%    |

- **Green ≥ 80%** — Best Match
- **Yellow 50–79%** — Moderate  
- **Red < 50%** — Low Match
