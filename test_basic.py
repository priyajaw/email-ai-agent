from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

print("Making API call with Gemini 2.5 Flash...")

response = client.models.generate_content(
    model="models/gemini-2.5-flash",  # ← Correct model name!
    contents="Todays news in india regarding gold and silver prices"
)

print("\n✅ Success!")
print(response.text)