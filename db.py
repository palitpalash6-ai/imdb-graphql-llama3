import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "imdb")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

movies_col = db["movies"]
actors_col = db["actors"]
