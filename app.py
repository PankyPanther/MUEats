"""
MUEats Flask Application — v3
==============================
Changes:
  1. Auto-scraper: on startup checks if today's menu is already loaded; if not,
     runs the scraper automatically in a background thread. Schedules a midnight
     re-run every day so data is always fresh without any manual action.
  2. Real progress tracking: /api/stats computes live streak, days-on-target,
     avg match score, and per-macro progress from actual logged meal data.
  3. /api/goals and /api/body persist to _user_store across requests.
"""

from flask import Flask, render_template, jsonify, request, session, redirect 
from datetime import datetime, date, timedelta
import json, os, re, math, threading, time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mueats-dev-secret-change-in-prod")

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
USE_MONGO = os.environ.get("USE_MONGO", "false").lower() == "true"
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DATA_FILE = os.path.join(os.path.dirname(__file__), "menu_data.json")

db = None
if USE_MONGO:
    from pymongo import MongoClient  # type: ignore
    client = MongoClient(MONGO_URI)
    db = client["mueats"]
    print("[+] MongoDB connected")

# ─────────────────────────────────────────────────────────────
#  IN-MEMORY STORES
# ─────────────────────────────────────────────────────────────
_user_store: dict[str, dict] = {}
_log_store:  dict[str, list] = {}   # email → list of log entries (today)
_log_date:   dict[str, str]  = {}   # email → date string of current log
# Weekly history: email → list of daily dicts, newest last
# Each dict: { date, calories, protein, carbs, fat, match_score }
_history:    dict[str, list] = {}


def _get_session_email() -> str:
    return session.get("user_email", "")


def _get_user_record(email: str) -> dict:
    if email not in _user_store:
        _user_store[email] = {
            "goals": {"calories": 2200, "protein": 150, "carbs": 220,
                      "fat": 70, "goal_type": "maintain"},
            "body":  {"weight_lbs": 0, "height_in": 0, "age": 0,
                      "sex": "male", "activity": "moderate"},
            "name":  email.split("@")[0].replace(".", " ").title(),
        }
    return _user_store[email]


def _get_todays_log(email: str) -> list:
    today = str(date.today())
    if _log_date.get(email) != today:
        # Save yesterday's log to history before clearing
        if email in _log_store and _log_store[email]:
            _archive_day(email, _log_date.get(email, ""))
        _log_store[email] = []
        _log_date[email]  = today
    return _log_store.get(email, [])


def _archive_day(email: str, day_str: str):
    """Save a completed day's totals + match score to history."""
    log   = _log_store.get(email, [])
    goals = _get_user_record(email).get("goals", {})
    totals = {
        "calories": sum(e.get("calories", 0) for e in log),
        "protein":  sum(e.get("protein",  0) for e in log),
        "carbs":    sum(e.get("carbs",    0) for e in log),
        "fat":      sum(e.get("fat",      0) for e in log),
    }
    score = _score_day(totals, goals)
    entry = {"date": day_str, **totals, "match_score": score}
    hist  = _history.setdefault(email, [])
    # Keep last 30 days
    hist.append(entry)
    if len(hist) > 30:
        _history[email] = hist[-30:]


def _consumed_today(email: str) -> dict:
    log = _get_todays_log(email)
    return {
        "calories": sum(e.get("calories", 0) for e in log),
        "protein":  sum(e.get("protein",  0) for e in log),
        "carbs":    sum(e.get("carbs",    0) for e in log),
        "fat":      sum(e.get("fat",      0) for e in log),
    }


# ─────────────────────────────────────────────────────────────
#  REAL PROGRESS TRACKING
# ─────────────────────────────────────────────────────────────
def _score_day(totals: dict, goals: dict) -> int:
    """
    Score a full day's consumption 0-100 against daily goals.
    Same weights as per-meal scoring: protein 40%, calories 30%,
    carbs 20%, fat 10%.
    """
    def _pct(actual, target):
        if target == 0:    return 100.0
        if actual == 0:    return 50.0
        ratio = actual / target
        return max(0.0, 100.0 - abs(ratio - 1.0) * 100.0)

    score = (
        _pct(totals.get("protein",  0), goals.get("protein",  150)) * 0.40 +
        _pct(totals.get("calories", 0), goals.get("calories", 2200)) * 0.30 +
        _pct(totals.get("carbs",    0), goals.get("carbs",    220))  * 0.20 +
        _pct(totals.get("fat",      0), goals.get("fat",       70))  * 0.10
    )
    return round(score)


def _compute_stats(email: str) -> dict:
    """
    Compute live progress stats from _log_store and _history.
    Returns everything /api/stats needs.
    """
    goals  = _get_user_record(email).get("goals",
             {"calories": 2200, "protein": 150, "carbs": 220, "fat": 70})
    hist   = _history.get(email, [])
    today  = str(date.today())

    # Build 7-day window (last 6 archived days + today)
    week = []
    for i in range(6, 0, -1):
        d = str(date.today() - timedelta(days=i))
        match = next((h for h in hist if h["date"] == d), None)
        week.append(match)   # None means no data for that day

    # Add today (live)
    today_totals = _consumed_today(email)
    today_score  = _score_day(today_totals, goals) if any(today_totals.values()) else None
    week.append({"date": today, **today_totals, "match_score": today_score} if today_score is not None else None)

    # Days with data
    days_with_data = [d for d in week if d is not None]
    scores         = [d["match_score"] for d in days_with_data]

    # Days on target (score ≥ 70)
    ON_TARGET_THRESHOLD = 70
    days_on_target = sum(1 for s in scores if s >= ON_TARGET_THRESHOLD)

    # Streak — count consecutive days from today backwards that are on target
    streak = 0
    for d in reversed(week):
        if d and d["match_score"] is not None and d["match_score"] >= ON_TARGET_THRESHOLD:
            streak += 1
        else:
            break

    # Avg match score
    avg_match = round(sum(scores) / len(scores)) if scores else 0

    # Best day
    best = max(days_with_data, key=lambda d: d["match_score"]) if days_with_data else None
    best_day = ""
    if best:
        try:
            best_day = datetime.strptime(best["date"], "%Y-%m-%d").strftime("%A")
        except Exception:
            best_day = best["date"]

    # 7-day spark scores (0 for missing days)
    weekly_scores = []
    for d in week:
        if d and d.get("match_score") is not None:
            weekly_scores.append(d["match_score"])
        else:
            weekly_scores.append(0)

    # Weekly macro averages (from days with data)
    def _avg(key):
        vals = [d[key] for d in days_with_data if d.get(key) is not None]
        return round(sum(vals) / len(vals)) if vals else 0

    return {
        "total_meals":       len(_load_meals_from_json()),
        "restaurant_count":  len(_get_restaurants()),
        "scraped_date":      _load_meals_from_json()[0].get("scraped_date") if _meal_cache else None,
        "weekly_avg_match":  avg_match,
        "days_on_target":    days_on_target,
        "streak":            streak,
        "best_day":          best_day or "N/A",
        "weekly_scores":     weekly_scores,
        "on_target_threshold": ON_TARGET_THRESHOLD,
        "weekly_macros": {
            "protein_avg":   _avg("protein"),  "protein_goal":  goals.get("protein",  150),
            "carbs_avg":     _avg("carbs"),    "carbs_goal":    goals.get("carbs",    220),
            "fat_avg":       _avg("fat"),      "fat_goal":      goals.get("fat",       70),
            "calories_avg":  _avg("calories"), "calories_goal": goals.get("calories", 2200),
        },
        # Today's live progress for the progress page
        "today": {
            **today_totals,
            "match_score": today_score or 0,
            "goals": goals,
        }
    }


# ─────────────────────────────────────────────────────────────
#  BMR / TDEE
# ─────────────────────────────────────────────────────────────
ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2, "light": 1.375, "moderate": 1.55,
    "active": 1.725, "very_active": 1.9,
}

def _calculate_recommendations(weight_lbs, height_in, age,
                                sex="male", activity="moderate",
                                goal_type="maintain") -> dict:
    if not all([weight_lbs, height_in, age]):
        return {}
    weight_kg = weight_lbs * 0.453592
    height_cm = height_in * 2.54
    bmr = (10 * weight_kg + 6.25 * height_cm - 5 * age +
           (5 if sex != "female" else -161))
    tdee = round(bmr * ACTIVITY_MULTIPLIERS.get(activity, 1.55))
    cal  = round(tdee * (0.80 if goal_type == "weight_loss" else
                         1.10 if goal_type == "muscle_gain" else 1.0))
    if goal_type == "muscle_gain":
        p, c, f = cal * 0.35 / 4, cal * 0.40 / 4, cal * 0.25 / 9
    elif goal_type == "weight_loss":
        p, c, f = cal * 0.40 / 4, cal * 0.35 / 4, cal * 0.25 / 9
    else:
        p, c, f = cal * 0.25 / 4, cal * 0.50 / 4, cal * 0.25 / 9
    return {"bmr": round(bmr), "tdee": tdee, "calories": cal,
            "protein": round(p), "carbs": round(c), "fat": round(f),
            "goal_type": goal_type}


# ─────────────────────────────────────────────────────────────
#  MACRO PARSING + TIER SCORING
# ─────────────────────────────────────────────────────────────
def _parse_g(val) -> float:
    if not val: return 0.0
    m = re.search(r"[\d.]+", str(val))
    return float(m.group()) if m else 0.0


def _extract_macros(nutrition: dict) -> dict:
    macros = nutrition.get("macros", {})
    def _get(keys):
        for k in keys:
            if k in macros: return _parse_g(macros[k])
        return 0.0
    return {
        "calories":  int(nutrition.get("calories", 0) or 0),
        "protein":   _get(["Protein", "Protein (g)"]),
        "carbs":     _get(["Total Carbohydrates", "Total Carbohydrates (g)"]),
        "fat":       _get(["Total Fat", "Total Fat (g)"]),
        "fiber":     _get(["Dietary Fiber", "Dietary Fiber (g)"]),
        "sugar":     _get(["Sugars", "Sugar (g)"]),
        "allergens": nutrition.get("allergens", "None"),
        "all_macros": macros,
    }


def _score_meal(meal: dict, goals: dict) -> dict:
    g_cal  = goals.get("calories", 2200) / 3
    g_pro  = goals.get("protein",  150)  / 3
    g_carb = goals.get("carbs",    220)  / 3
    g_fat  = goals.get("fat",      70)   / 3

    def _pct(actual, target):
        if target == 0: return 100.0
        if actual == 0: return 50.0
        return max(0.0, 100.0 - abs(actual / target - 1.0) * 100.0)

    score = round(
        _pct(meal.get("protein",  0), g_pro)  * 0.40 +
        _pct(meal.get("calories", 0), g_cal)  * 0.30 +
        _pct(meal.get("carbs",    0), g_carb) * 0.20 +
        _pct(meal.get("fat",      0), g_fat)  * 0.10
    )
    tier = "green" if score >= 80 else ("yellow" if score >= 50 else "red")
    return {"match_pct": score, "tier": tier}


# ─────────────────────────────────────────────────────────────
#  DATA LOADING
# ─────────────────────────────────────────────────────────────
_meal_cache: list[dict] = []

def _load_meals_from_json(filepath: str = DATA_FILE) -> list[dict]:
    global _meal_cache
    if _meal_cache:
        return _meal_cache
    try:
        with open(filepath) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"[!] {filepath} not found — meal cache empty")
        return []

    scraped_date = raw.get("date", str(date.today()))
    meals, meal_id = [], 1
    for restaurant, periods in raw.get("restaurants", {}).items():
        for period, items in periods.items():
            for item in items:
                if not item.get("title"): continue
                macros = _extract_macros(item.get("nutrition", {}))
                meals.append({
                    "id": f"m{meal_id}", "title": item["title"].strip(),
                    "description": (item.get("description") or "").strip(),
                    "restaurant": restaurant.strip(), "period": period,
                    "scraped_date": scraped_date, **macros,
                })
                meal_id += 1
    _meal_cache = meals
    print(f"[+] Loaded {len(meals)} meals from {filepath}")
    return meals


def _get_meals(restaurant=None, period=None, tier=None, goals=None):
    raw = _load_meals_from_json()
    if restaurant: raw = [m for m in raw if m["restaurant"] == restaurant]
    if period:     raw = [m for m in raw if m["period"] == period]
    g = goals or {"calories": 2200, "protein": 150, "carbs": 220, "fat": 70}
    scored = [{**m, **_score_meal(m, g)} for m in raw]
    if tier: scored = [m for m in scored if m["tier"] == tier]
    return scored


def _get_restaurants():
    seen = []
    for m in _load_meals_from_json():
        if m["restaurant"] not in seen: seen.append(m["restaurant"])
    return seen


def _get_periods():
    seen = []
    for m in _load_meals_from_json():
        if m["period"] not in seen: seen.append(m["period"])
    return seen


# ─────────────────────────────────────────────────────────────
#  AUTO-SCRAPER — runs on startup and every day at midnight
# ─────────────────────────────────────────────────────────────
_scraper_lock = threading.Lock()
_scraper_status = {"running": False, "last_run": None, "last_result": None}


def run_scraper(target_date: str = None) -> dict:
    """
    Run the web scraper for target_date (defaults to today).
    Uses a threading lock so it never runs twice simultaneously.
    Busts the meal cache when done so fresh data loads immediately.
    """
    global _meal_cache
    if not _scraper_lock.acquire(blocking=False):
        return {"success": False, "error": "Scraper already running"}

    # Default to today — always current
    target_date = target_date or str(date.today())
    _scraper_status["running"] = True
    res = {}

    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from Scraper.scraper_main import RestaurantScraper  # type: ignore

        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu_data.json")
        print(f"[+] Starting scrape for {target_date} → {output_file}")

        scraper = RestaurantScraper(target_date=target_date, headless=True)
        result  = scraper.scrapeToJson(output_file)
        scraper.quit()

        # Bust cache so /api/meals returns fresh data immediately
        _meal_cache = []

        n_restaurants = len([r for r, v in result.get("restaurants", {}).items() if v])
        n_items       = sum(
            len(items)
            for periods in result.get("restaurants", {}).values()
            for items in periods.values()
        )
        res = {
            "success":     True,
            "date":        target_date,
            "restaurants": n_restaurants,
            "items":       n_items,
        }
        print(f"[+] Scrape complete: {n_items} items from {n_restaurants} restaurants")

    except ImportError as e:
        res = {"success": False,
               "error": f"Selenium not installed. Run: pip install selenium webdriver-manager — {e}"}
        print(f"[!] Import error: {e}")
    except RuntimeError as e:
        # Our friendly "no browser found" message from scraper_main
        res = {"success": False, "error": str(e)}
        print(f"[!] Browser error: {e}")
    except Exception as e:
        res = {"success": False, "error": str(e)}
        print(f"[!] Scraper error: {e}")
    finally:
        _scraper_status["running"]     = False
        _scraper_status["last_run"]    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _scraper_status["last_result"] = res
        _scraper_lock.release()

    return res


def _data_is_stale() -> bool:
    """Returns True if menu_data.json is missing or from a previous day."""
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
        return d.get("date") != str(date.today())
    except FileNotFoundError:
        return True


def _schedule_midnight_scrape():
    """Schedule the next scrape to run at the next midnight."""
    now       = datetime.now()
    tomorrow  = (now + timedelta(days=1)).replace(hour=0, minute=1,
                                                   second=0, microsecond=0)
    delay_sec = (tomorrow - now).total_seconds()
    print(f"[+] Next auto-scrape scheduled in {delay_sec/3600:.1f}h "
          f"(at {tomorrow.strftime('%Y-%m-%d %H:%M')})")

    def _run_then_reschedule():
        run_scraper(str(date.today()))
        _schedule_midnight_scrape()   # schedule next day's run

    t = threading.Timer(delay_sec, _run_then_reschedule)
    t.daemon = True   # won't block process exit
    t.start()


def _auto_scrape_on_startup():
    """
    Called once when Flask starts.
    If today's data is missing/stale, kick off a background scrape immediately.
    Then schedule the next midnight run regardless.
    """
    def _startup_worker():
        if _data_is_stale():
            print(f"[+] Menu data stale — auto-scraping for {date.today()}…")
            run_scraper(str(date.today()))
        else:
            print(f"[+] Menu data is current ({date.today()}) — no scrape needed")
        _schedule_midnight_scrape()

    t = threading.Thread(target=_startup_worker, daemon=True)
    t.start()


# ─────────────────────────────────────────────────────────────
#  AUTH HELPERS
# ─────────────────────────────────────────────────────────────
def _is_miami_email(email: str) -> bool:
    return email.strip().lower().endswith("@miamioh.edu")


def _current_user() -> dict:
    email = _get_session_email()
    if not email:
        return {"email": "", "name": "Guest", "logged_in": False,
                "goals": {"calories": 2000, "protein": 100, "carbs": 250,
                          "fat": 65, "goal_type": "maintain"},
                "consumed_today": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}}
    record = _get_user_record(email)
    return {
        "email":         email,
        "name":          record.get("name", email.split("@")[0].title()),
        "goals":         record.get("goals", {}),
        "body":          record.get("body", {}),
        "consumed_today": _consumed_today(email),
        "logged_in":     True,
    }


# ─────────────────────────────────────────────────────────────
#  ROUTES — Pages
# ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not _get_session_email():
        return redirect("/")
    return render_template("dashboard.html")


# ─────────────────────────────────────────────────────────────
#  ROUTES — Auth
# ─────────────────────────────────────────────────────────────
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data  = request.get_json()
    email = data.get("email", "").strip()
    pw    = data.get("password", "")
    if not _is_miami_email(email):
        return jsonify({"success": False,
                        "error": "Only @miamioh.edu email addresses are allowed."}), 403
    if not pw:
        return jsonify({"success": False, "error": "Password is required."}), 400
    session["user_email"] = email
    session["user_name"]  = _get_user_record(email).get("name", "")
    return jsonify({"success": True, "redirect": "/dashboard"})


@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    data  = request.get_json()
    email = data.get("email", "").strip()
    name  = data.get("name", "").strip()
    if not _is_miami_email(email):
        return jsonify({"success": False,
                        "error": "Only @miamioh.edu email addresses can create an account."}), 403
    if not name:
        return jsonify({"success": False, "error": "Full name is required."}), 400
    record = _get_user_record(email)
    record["name"] = name
    session["user_email"] = email
    session["user_name"]  = name
    return jsonify({"success": True, "redirect": "/dashboard"})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True, "redirect": "/"})


@app.route("/auth/google")
def google_stub():
    return redirect("/?error=google_oauth_not_configured")


# ─────────────────────────────────────────────────────────────
#  ROUTES — User & Goals
# ─────────────────────────────────────────────────────────────
@app.route("/api/user")
def api_user():
    return jsonify(_current_user())


@app.route("/api/goals", methods=["PATCH"])
def api_update_goals():
    email = _get_session_email()
    if not email:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data    = request.get_json()
    allowed = {"calories", "protein", "carbs", "fat", "goal_type"}
    goals   = {k: v for k, v in data.items() if k in allowed}
    record  = _get_user_record(email)
    record["goals"].update(goals)
    return jsonify({"success": True, "goals": record["goals"]})


@app.route("/api/body", methods=["PATCH"])
def api_update_body():
    email = _get_session_email()
    if not email:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data    = request.get_json()
    allowed = {"weight_lbs", "height_in", "age", "sex", "activity"}
    body    = {k: v for k, v in data.items() if k in allowed}
    record  = _get_user_record(email)
    record.setdefault("body", {}).update(body)
    return jsonify({"success": True, "body": record["body"]})


@app.route("/api/recommendations")
def api_recommendations():
    email = _get_session_email()
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    record    = _get_user_record(email)
    body      = record.get("body", {})
    goal_type = record.get("goals", {}).get("goal_type", "maintain")
    recs = _calculate_recommendations(
        weight_lbs=body.get("weight_lbs", 0), height_in=body.get("height_in", 0),
        age=body.get("age", 0), sex=body.get("sex", "male"),
        activity=body.get("activity", "moderate"), goal_type=goal_type)
    if not recs:
        return jsonify({"error": "Please fill in height, weight, and age first."}), 400
    return jsonify(recs)


# ─────────────────────────────────────────────────────────────
#  ROUTES — Meals
# ─────────────────────────────────────────────────────────────
@app.route("/api/meals")
def api_meals():
    restaurant = request.args.get("restaurant")
    period     = request.args.get("period")
    tier       = request.args.get("tier")
    search     = request.args.get("search", "").lower()
    goals      = _current_user().get("goals", {})
    meals      = _get_meals(restaurant=restaurant, period=period,
                            tier=tier, goals=goals)
    if search:
        meals = [m for m in meals if search in m["title"].lower()
                 or search in m.get("description", "").lower()]
    meals.sort(key=lambda m: m["match_pct"], reverse=True)
    return jsonify(meals)


@app.route("/api/meals/<meal_id>")
def api_meal_detail(meal_id):
    goals = _current_user().get("goals", {})
    meal  = next((m for m in _get_meals(goals=goals) if m["id"] == meal_id), None)
    return jsonify(meal) if meal else (jsonify({"error": "Not found"}), 404)


@app.route("/api/restaurants")
def api_restaurants():
    return jsonify(_get_restaurants())


@app.route("/api/periods")
def api_periods():
    return jsonify(_get_periods())


@app.route("/api/suggestions")
def api_suggestions():
    goals = _current_user().get("goals", {})
    meals = _get_meals(goals=goals)
    top   = sorted([m for m in meals if m["tier"] == "green"],
                   key=lambda m: m["match_pct"], reverse=True)[:10]
    return jsonify(top)


# ─────────────────────────────────────────────────────────────
#  ROUTES — Meal Log
# ─────────────────────────────────────────────────────────────
@app.route("/api/meal_log")
def api_meal_log():
    email = _get_session_email()
    return jsonify(_get_todays_log(email) if email else [])


@app.route("/api/meal_log", methods=["POST"])
def api_log_meal():
    email = _get_session_email()
    if not email:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data  = request.get_json()
    entry = {**data, "user_email": email, "date": str(date.today()),
             "logged_at": datetime.now().strftime("%I:%M %p"),
             "log_id": f"log_{int(datetime.now().timestamp()*1000)}"}
    log = _get_todays_log(email)
    log.append(entry)
    _log_store[email] = log
    return jsonify({"success": True, "entry": entry}), 201


@app.route("/api/meal_log/<log_id>", methods=["DELETE"])
def api_delete_log(log_id):
    email = _get_session_email()
    if not email:
        return jsonify({"success": False}), 401
    _log_store[email] = [e for e in _get_todays_log(email)
                         if e.get("log_id") != log_id]
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
#  ROUTES — Scraper
# ─────────────────────────────────────────────────────────────
@app.route("/api/scraper/run", methods=["POST"])
def api_run_scraper():
    data = request.get_json()
    target_date = data.get("date", str(date.today()))
    if _scraper_status["running"]:
        return jsonify({"success": False, "error": "Scraper is already running"}), 409
    # Run in background so request returns immediately
    t = threading.Thread(target=run_scraper, args=(target_date,), daemon=True)
    t.start()
    return jsonify({"success": True, "message": f"Scraper started for {target_date}"})


@app.route("/api/scraper/status")
def api_scraper_status():
    status = {**_scraper_status}
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
        total = sum(len(items)
                    for periods in d.get("restaurants", {}).values()
                    for items in periods.values())
        status.update({
            "loaded": True,
            "scraped_date":     d.get("date"),
            "is_today":         d.get("date") == str(date.today()),
            "restaurant_count": len(d.get("restaurants", {})),
            "total_items":      total,
        })
    except Exception as e:
        status.update({"loaded": False, "error": str(e)})
    return jsonify(status)


# ─────────────────────────────────────────────────────────────
#  ROUTES — Stats (real progress tracking)
# ─────────────────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    email = _get_session_email()
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(_compute_stats(email))


if __name__ == "__main__":
    _load_meals_from_json()     # warm meal cache
    _auto_scrape_on_startup()   # check staleness + schedule midnight runs
    app.run(debug=True, port=5000, use_reloader=False)
    # use_reloader=False prevents the background thread from starting twice
