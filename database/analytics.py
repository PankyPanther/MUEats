from datetime import datetime, timedelta
from db import get_db
from metrics import calculate_bmi

def get_weekly_calories(email: str):
    db = get_db()
    meals = db["meals"]

    one_week_ago = datetime.now() - timedelta(days=7)

    recent_meals = list(meals.find({
        "email": email,
        "timestamp": {"$gte": one_week_ago}
    }))

    total_calories = sum(meal["calories"] for meal in recent_meals)

    daily_breakdown = {}
    for meal in recent_meals:
        day = meal["timestamp"].strftime("%Y-%m-%d")
        daily_breakdown.setdefault(day, 0)
        daily_breakdown[day] = daily_breakdown.get(day, 0) + meal["calories"]

    return {
        "total_weekly_calories": total_calories,
        "daily_breakdown": daily_breakdown
    }

def get_weight_trend(email: str):
    db = get_db()
    users = db["users"]

    user = users.find_one({"email": email})
    if not user:
        return {"error": "User not found"}, 404

    weight_history = user.get("weight_history", [])
    if len(history) < 2:
        return {"message": "Not enough data to determine trend"}, 200
    
    start_weight = weight_history[0]["weight"]
    current_weight = weight_history[-1]["weight"]
    change = abs(current_weight - start_weight)

    return {
        "start_weight": start_weight,
        "current_weight": current_weight,
        "change": change
    }

def get_bmi_change(email: str):
    db = get_db()
    users = db["users"]

    user = users.find_one({"email": email})
    if not user:
        return {"error": "User not found"}, 404

    height = user["height"]
    weight_history = user.get("weight_history", [])

    if len(weight_history) < 2:
        return {"message": "Not enough data to determine BMI change"}, 200
    
    start_bmi = calculate_bmi(weight_history[0]["weight"], height)
    current_bmi = calculate_bmi(weight_history[-1]["weight"], height)

    return {
        "start_bmi": start_bmi,
        "current_bmi": current_bmi,
        "change": round(current_bmi - start_bmi, 2)
    }

def get_goal_progress(email: str):
    db = get_db()
    users = db["users"]

    user = users.find_one({"email": email})
    if not user:
        return {"error": "User not found"}, 404

    current_weight = user["weight"]
    goal_weight = user["goal_weight"]

    return {
        "current_weight": current_weight,
        "goal_weight": goal_weight,
        "remaining": abs(goal_weight - current_weight)
    }

def get_weekly_summary(email: str):
    return {
        "calories": get_weekly_calories(email),
        "weight_trend": get_weight_trend(email),
        "bmi_change": get_bmi_change(email),
        "goal_progress": get_goal_progress(email)
    }
