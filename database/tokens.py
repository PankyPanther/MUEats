import jwt
from datetime import datetime, timedelta
import os

SECRET = os.getenv("JWT_SECRET", "dev_secret_key")

def create_token(email: str) -> str:
    payload = {
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=24)  # Token expires in 24 hours
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    return token

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return payload["email"]
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")
