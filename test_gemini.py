import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ GEMINI_API_KEY not found in .env")
    exit()

client = genai.Client(api_key=api_key)

try:
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input="Say hello in one sentence."
    )

    print("\n✅ Gemini Connected Successfully!")
    print("Response:", interaction.output_text)

except Exception as e:
    print("\n❌ Gemini Error:")
    print(e)