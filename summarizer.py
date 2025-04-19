import requests
import asyncio

def load_prompt(config_type):
    prompt_file = 'prompt.txt' if config_type.lower() == 'defi' else 'ordinals-prompt.txt'
    try:
        with open(prompt_file, 'r') as f:
            return f.read()
    except:
        return "Please summarize the following text in bullet point format for a cryptocurrency trader looking for alpha so he can act on important ideas. If the bullet point doesn't have anything to do with defi or crypto, just skip it."

#async def generate_summary(text, config_type, api_key, model_name="google/gemini-2.0-flash-001"):
async def generate_summary(text, config_type, api_key, model_name="openrouter/quasar-alpha"):
    prompt = load_prompt(config_type)
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for text summarization."},
            {"role": "user", "content": f"{prompt}\n{text}"}
        ],
        "max_tokens": 8000,
        "temperature": 0.7
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/DiscordV2Bot",
        "X-Title": "Discord Fast Channel Summarizer"
    }
    try:
        resp = await asyncio.to_thread(
            requests.post,
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=180
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            return f"Error generating summary: API returned {resp.status_code}"
    except Exception as e:
        return f"Error generating summary: {e}"
