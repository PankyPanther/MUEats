import json
import sys
from db import get_db

DINING_HALLS = [
    "Western Dining Hall",
    "Garden Commons",
    "Maple Street Station",
    "Martin Dining Hall"
]

print("Loading menu data ...")

def load_menu_data(path):
    db = get_db()
    restaurants_col = db["restaurants"]
    items_col = db["menu_items"]   # FIXED — correct variable name

    with open(path) as f:
        data = json.load(f)

    for restaurant_name, info in data["restaurants"].items():

        print("Restaurant:", restaurant_name)
        print("Keys:", list(info.keys()))

        # Determine if dining hall
        is_dining_hall = restaurant_name in DINING_HALLS

        # Meal periods = all keys that contain lists
        meal_periods = [k for k, v in info.items() if isinstance(v, list)]

        # Insert restaurant
        restaurants_col.update_one(
            {"name": restaurant_name},
            {
                "$set": {
                    "type": "dining_hall" if is_dining_hall else "restaurant",
                    "availability": ["Every Day"],
                    "meal_periods": meal_periods
                }
            },
            upsert=True
        )

        # Loop through each meal period
        for period, items in info.items():

            # Skip metadata keys
            if not isinstance(items, list):
                continue

            # Insert each item
            for item in items:
                items_col.insert_one({
                    "restaurant": restaurant_name,
                    "name": item["title"],
                    "description": item.get("description", ""),
                    "calories": item["nutrition"]["calories"],
                    "allergens": item["nutrition"].get("allergens", []),
                    "macros": item["nutrition"].get("macros", {}),
                    "meal_periods": [period]
                })

if __name__ == "__main__":
    print("Starting menu data load ...")

    if len(sys.argv) < 2:
        print("Usage: python load_menu_data.py <json_file>")
        exit(1)

    json_path = sys.argv[1]
    print("Loading", json_path)

    load_menu_data(json_path)
    print(f"Loaded menu data from {json_path} successfully.")