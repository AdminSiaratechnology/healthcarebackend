from google import genai
import json
import re

from app.database.config import settings


# ✅ new client
client = genai.Client(api_key=settings.GEMINI_API_KEY)


def build_prompt(text: str, subcat_names: list[str]) -> str:
    return f"""
You are a medical assistant.

Extract and map the clinical text into these sections:

{subcat_names}

Rules:
- Only use given section names
- If not found, return ""
- Return STRICT JSON only

Text:
{text}
"""


async def call_llm(prompt: str) -> dict:
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",  # ✅ FIXED MODEL
            contents=prompt,
        )

        text = response.text

        # 🔥 remove markdown
        text = re.sub(r"```json|```", "", text).strip()

        return json.loads(text)

    except Exception as e:
        print("LLM ERROR:", e)
        return {}

