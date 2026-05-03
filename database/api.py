from flask import Flask, request, jsonify
from auth import create_user, login, get_user_profile
from meals import create_meal, get_user_meals
from updates import update_user_stats
from analytics import get_weekly_summary
from functools import wraps
from tokens import verify_token
from flask_cors import CORS
from validators import require_fields, require_types, ValidationError
import traceback
from bson import ObjectId
from datetime import datetime

CORS(app, origins=["http://localhost:3000", "https://mu_eats.app"]) # allow CORS for local frontend development 

app = Flask(__name__)

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Authorization token required"}), 401
        email = verify_token(token)
        if not email:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(email=email, *args, **kwargs)
    return wrapper

def get_current_meal_period():
    now = datetime.now()
    hour = now.hour

    for period, (start, end) in MEAL_PERIODS.items():
        if start <= hour <= end:
            return period
    
    return None # No meal period matches

# User creation
@app.route("/users/create", methods=["POST"])
def api_create_user():
    data = request.json

    # Required fields
    error = required_fields(data, ["username", "email", "password",
                                    "height", "weight", "birthday",
                                    "goal_weight"])
    if error:
        return jsonify(error), 400

    # Type checking
    error = require_types(data, {
        "username": str,
        "email": str,
        "password": str,
        "height": (int, float),
        "weight": (int, float),
        "birthday": str,
        "goal_weight": (int, float)
    })
    if error:
        return jsonify(error), 400

    response, status = create_user(
        username=data["username"],
        email=data["email"],
        password=data["password"],
        height=data["height"],
        weight=data["weight"],
        birthday=data["birthday"],
        goal_weight=data["goal_weight"]
    )
    return jsonify(response), status



# User login
@app.route("/users/login", methods=["POST"])
def api_login():
    data = request.json

    error = require_fields(data, ["email", "password"])
    if error:
        return jsonify(error), 400

    error = require_types(data, {
        "email": str,
        "password": str
    })
    if error:
        return jsonify(error), 400
    
    success = login(data["email"], data["password"])
    if not success:
        return jsonify({success": False, "error": "Invalid email or password"}), 401
                        
    token = create_token(data["email"])
    return jsonify({"success": True, "token": token}), 200



# User profile
@app.route("/users/profile", methods=["GET"])
def api_profile():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email query parameter required"}), 400

    profile = get_user_profile(email)
    if not profile:
        return jsonify({"error": "User not found"}), 404

    return jsonify(profile), 200



# Update user stats
@app.route("/users/update", methods=["PATCH"])
@require_auth
def api_update_stats():
    data = request.json

    error = require_types(data, {
        "height": (int, float, type(None)),
        "weight": (int, float, type(None))
    })
    if error:
        return jsonify({"error": error}), 400

    response, status = update_user_stats(
        request.email,
        data.get("height"),
        data.get("weight")
    )
    return jsonify(response), status



# Log a meal
@app.route("/meals/user", methods=["GET"])
@require_auth
def api_get_meals():
    data = request.json

    error = require_fields(data, {"meal_type", "foods", "calories"})
    if error:
        return jsonify({"error": error}), 400

    response, status = create_meal(
        request.email,
        data["meal_type"],
        data["foods"],
        data["calories"]
    )
    return jsonify(response), status



# Weekly analytics
@app.route("/analytics/weekly", methods=["GET"])
@require_auth
def api_weekly_summary():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email query parameter required"}), 400

    summary = get_weekly_summary(email)
    if "error" in summary:
        return jsonify(summary), 404

    return jsonify(summary), 200



# Get all restaurants
@app.route("/restaurants", methods=["GET"])
def api_get_restaurants():
    db = get_db()
    restaurants = list(db["restaurants"].find({}, {"_id": 0})) # exclude _id for cleaner output
    return jsonify(restaurants), 200



# Get meal periods for a restaurant
@app.route("/restaurants/<name>/meal_perdios", methods=["GET"])
def api_get_meal_periods(name):
    db = get_db()
    restaurant = db["restaurants"].find_one({"name": name}, {"_id": 0})

    if not restaurant:
        return jsonify({"error": "Restaurant not found"}), 404
    
    return jsonify(restaurant.get("meal_periods", [])), 200



# Get menu items for a restaurant
@app.route("/restaurants/<name>/items", methods=["GET"])
    db = get_db()
    period = request.args.get("period")

    query = {"restaurant": name}

    # If filtering by meal period

    if period:
        query["meal_periods"] = period

    items = list(db["menu_items"].find(query, {"_id": 0}))
    return jsonify(items), 200


# Search menu items by name
@app.route("/menu_items/search", methods=["GET"])
def api_search_items():
    query = request.args.get("query", "")
    db = get_db()

    items = list(db["menu_items"].find(
        {"name": {"$regex": query, "$options": "i"}}, # case-insensitive search
        {"_id": 0}
    ))
    return jsonify(items), 200



# Get a single menu item by id
@app.route("/menu_itmes/<item_id>", methods=["GET"])
def api_get_item(item_id):
    db = get_db()

    try:
        item = db["menu_items"].find_one({"_id": ObjectId(item_id)}, {"_id": 0})
    except:
        return jsonify({"error": "Invalid item ID"}), 400

    if not item:
        return jsonify({"error": "Item not found"}), 404

    item["_id"] = str(item["_id"]) # convert ObjectId to string for cleaner output
    return jsonify(item), 200



# Log a meal using a menu item
@app.route("/meals/add_item", methods=["POST"])
@require_auth
def api_add_meal_item():
    data = request.json
    item_id = data.get("item_id")

    if not item_id:
        return jsonify({"error": "item_id is required"}), 400

    db = get_db()

    try:
        item = db["menu_items"].find_one({"_id": ObjectId(item_id)})
    except:
        return jsonify({"error": "Invalid item ID"}), 400
    
    if not item:
        return jsonify({"error": "Item not found"}), 404

    meal_doc = {
        "email": request.email,
        "item_name": item["name"],
        "restaurant": item["restaurant"],
        "calories": item["calories"],
        "macros": item["macros"],
        "timestamp": datetime.now()
    }

    db["meals"].insert_one(meal_doc)
    return jsonify({"message": "Meal logged successfully"}), 201



# Get meal items available now
@app.route("/menu_items/now", methods=["GET"])
def api_get_items_now():

    current_period = get_current_meal_period()

    # If it's a time with no meal period

    if not current_period:
        reutrn jsonify({
            "meal_period": None,
            "items": []
        }), 200
    
    # Query for items available now

    items = list(db["menu_items"].find(
        {
            "$or": [
                {"meal_periods": current_period}, # dining hall items
                {"meal_periods": "Every Day"} # regular restaurants
            ]
        },
        {"_id": 0}
    ))

    return jsonify({
        "meal_period": current_period,
        "items": items
    }), 200

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the full traceback for debugging

    print("ERROR": e)
    traceback.print_exc()

    # Return a clean JSON response

    return jsonify({"error": "An unexpected error occurred",
        "details": str(e)"}), 500

        

@app.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify({"error": "Validation error", "details": str(e)}), 400



@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad request", "details": str(e)}), 400



@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"error": "Unauthorized", "details": str(e)}), 401



@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found", "details": str(e)}), 404



class ValidationError(Exception):
    pass




# Run server
if __name__ == "__main__":
    app.run(debug=True)


