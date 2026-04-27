"""
groq_why_bro.py — quick helper to verify Groq access.
"""
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

client = Groq(api_key=GROQ_API_KEY)
try:
    # Attempt a lightweight call to ensure credentials work
    models = client.models.list()
    for m in models:
        print(m.id)
except Exception as exc:
    print("Groq client error:", exc)