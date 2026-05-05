import bcrypt
from db import get_db
from metrics import calculate_bmi, calculate_goal_bmi
from datetime import datetime
from updates import update_user_stats


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def create_user(username: str, email: str, password: str,
                height: float, weight: float, birthday: str, goal_weight: float):
    db = get_db()
    users = db["users"]

    # Check if user already exists
    if users.find_one({"email": email}) or users.find_one({"username": username}):
        return {"error": "User already exists"}, 400

    hashed_password = hash_password(password)

    user_doc = {
        "username": username,
        "email": email,
        "password": hashed_password,
        "height": height,
        "weight": weight,
        "birthday": birthday,
        "goal_weight": goal_weight,
        "weight_history": [
                        {"weight": weight, "timestamp": datetime.now()}
                        ]
    }

    result = users.insert_one(user_doc)
    print(f"User created with ID: {result.inserted_id}")
    return {"message": "User created successfully"}, 201

def get_user_profile(email: str):
    db = get_db()
    users = db["users"]

    user = users.find_one({"email": email})
    if not user:
        return None
    bmi = calculate_bmi(user["weight"], user["height"])
    goal_bmi = calculate_goal_bmi(user["goal_weight"], user["height"])

    profile = {
        "username": user["username"],
        "email": user["email"],
        "height": user["height"],
        "weight": user["weight"],
        "age": user["age"],
        "goal_weight": user["goal_weight"],
        "bmi": bmi,
        "goal_bmi": goal_bmi
    }
    return profile


def login(email: str, password: str):
    db = get_db()
    users = db["users"]

    # FIXED: this must be user, not users
    user = users.find_one({"email": email})

    if not user:
        print("User not found.")
        return False

    if verify_password(password, user["password"]):
        print("Login successful.")
        return True
    else:
        print("Invalid password.")
        return False
    
