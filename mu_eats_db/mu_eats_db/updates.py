from datetime import datetime
from db import get_db

def update_user_stats(email: str, new_height: float = None, new_weight: float = None):
    db = get_db()
    users = db["users"]

    user = users.find_one({"email": email})
    if not user:
        return {"error": "User not found"}, 404

    update_fields = {}

    # Update height if provided

    if new_height is not None:
        update_fields["height"] = new_height

    # Update weight + log weight history
    if new_weight is not None:
        update_fields["weight"] = new_weight

        # Add to weight history
        users.update_one({"email": email},
                        {"$push": {"weight_history": {
                            "weight": new_weight,
                            "timestamp": datetime.now()
                        }}})

    # Apply updates
    
    if update_fields:
        users.update_one({"email": email}, {"$set": update_fields})
        return {"message": "User stats updated successfully"}, 200
    else:
        return {"message": "No updates provided"}, 400