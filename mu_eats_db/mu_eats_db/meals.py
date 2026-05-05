from datetime import datetime
from db import get_db

def create_meal(email: str, meal_type: str, foods: list, calories: int):
    db = get_db()
    meals = db["meals"]

    meal_doc = {
        "email": email,
        "meal_type": meal_type, # Breakfast, lunch, dinner, snack
        "foods": foods, # list of strings
        "calories": calories,
        "timestamp": datetime.now()
    }

    result = meals.insert_one(meal_doc)
    print(f"Meal created with ID: {result.inserted_id}")
    return {"message": "Meal created successfully"}, 201

def get_user_meals(email: str):
    db = get_db()
    meals = db["meals"]

    user_meals = list(meals.find({"email": email}))

    # convert objectID + dattime to strings for clean output

    for meal in user_meals:
        meal["_id"] = str(meal["_id"])  # Convert ObjectId to string for JSON serialization
    return user_meals