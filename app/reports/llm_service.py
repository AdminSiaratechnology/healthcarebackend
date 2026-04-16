# app/services/llm_service.py

from openai import AsyncOpenAI
import json

client = AsyncOpenAI(api_key="YOUR_API_KEY")


def build_prompt(text: str, subcat_names: list[str]) -> str:
    return f"""
You are a medical assistant.

Your task is to extract and map the given clinical text into the provided sections.

Sections:
{subcat_names}

Rules:
- Only use the given section names as keys
- If information belongs to a section, put it there
- If not found, return empty string ""
- Do not create extra keys
- Keep answers short and relevant

Text:
{text}

Output JSON only.
"""


async def call_llm(prompt: str) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a medical data extractor."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except:
        return {}