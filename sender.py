import requests
import discord
import asyncio

async def send_bot_message(bot_client, channel_id, content):
    try:
        channel = bot_client.get_channel(channel_id)
        if not channel:
            channel = await bot_client.fetch_channel(channel_id)
        if not channel:
            print(f"Bot could not find channel {channel_id}")
            return False
        await channel.send(content)
        return True
    except discord.Forbidden:
        print(f"Bot lacks permissions for channel {channel_id}")
        return False
    except Exception as e:
        print(f"Bot send error: {e}")
        return False

def send_user_message(channel_id, content, user_token):
    if not user_token:
        print("User token not available for fallback send.")
        return False
    headers = {
        'Authorization': user_token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
    }
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    payload = {"content": content}
    try:
        resp = requests.post(url, headers=headers, json=payload)
        return resp.status_code == 200
    except:
        return False