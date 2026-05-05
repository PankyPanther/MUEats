from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

uri = os.getenv("MONGO_URI")
client = MongoClient(uri)

# create database
db = client["mu_eats"]

# create collection
users = db["users"]

def get_db():
    return db
