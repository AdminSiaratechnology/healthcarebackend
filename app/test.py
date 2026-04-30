
from google import genai

# 🔑 Client init
client = genai.Client(api_key="YOUR_API_KEY")

def test_gemini():
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents="Hello"
        )

        print(response.text)

    except Exception as e:
        print("Error:", e)

test_gemini()