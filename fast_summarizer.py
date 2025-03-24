#!/usr/bin/env python3
"""
Fast Discord Channel Summarizer
This version skips the Discord API scraping by using a direct HTTP approach
"""
import requests
import json
import time
import datetime
import argparse
import os
from datetime import datetime, timedelta
import tiktoken
from dotenv import load_dotenv
import discord
import asyncio

# Load environment variables
load_dotenv()

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Discord Fast Channel Summarizer')
parser.add_argument('--hours', type=int, default=12, help='Number of hours of chat history to fetch (default: 12)')
parser.add_argument('--limit', type=int, default=50, help='Maximum number of messages per channel (default: 50)')
parser.add_argument('--debug', action='store_true', help='Print messages to console instead of summarizing')
args = parser.parse_args()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')  # Discord user token
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Discord bot token
CHANNEL_IDS = [int(id) for id in os.getenv('CHANNEL_IDS', '').split(',') if id]  # Channels to monitor
OUTPUT_CHANNEL_ID = int(os.getenv('OUTPUT_CHANNEL_ID', '0'))  # Channel to send summaries
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Set up headers for Discord API
headers = {
    'Authorization': TOKEN,
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
}

# Set up Discord bot client
# For newer versions of discord.py that require intents
intents = discord.Intents.default()
bot_client = discord.Client(intents=intents)

def fetch_channel_info(channel_id):
    """Fetch channel name and other info"""
    url = f"https://discord.com/api/v9/channels/{channel_id}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print(f"Error fetching channel info: {response.status_code}")
        return None

def load_prompt():
    """Load the prompt from prompt.txt file"""
    try:
        with open('prompt.txt', 'r') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading prompt.txt: {e}")
        # Fallback prompt if file can't be loaded
        return "Please summarize the following text in bullet point format for a cryptocurrency trader looking for alpha so he can act on important ideas. If the bullet point doesn't have anything to do with defi or crypto, just skip it."

def fetch_messages(channel_id, limit=100, hours=12):
    """Fetch messages from a channel without scraping members"""
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit={limit}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        messages = response.json()
        
        # Filter by time
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        cutoff_str = cutoff_time.isoformat()
        
        # Keep messages newer than cutoff
        filtered_messages = [msg for msg in messages if msg['timestamp'] > cutoff_str]
        
        return filtered_messages
    else:
        print(f"Error fetching messages: {response.status_code}")
        return []

async def send_bot_message(channel_id, content):
    """Send a message using the bot client"""
    try:
        channel = bot_client.get_channel(channel_id)
        if not channel:
            channel = await bot_client.fetch_channel(channel_id)
        
        await channel.send(content)
        return True
    except Exception as e:
        print(f"Error sending message via bot: {e}")
        return False

def send_message(channel_id, content):
    """Send a message to a Discord channel using user token (fallback)"""
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    payload = {"content": content}
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        return True
    else:
        print(f"Error sending message: {response.status_code}")
        return False

def generate_summary(text, model_name="google/gemini-2.0-flash-001"):
    """Generate a summary using OpenRouter API"""
    print(f"Generating summary using {model_name}...")
    
    # Load the prompt from file
    prompt = load_prompt()
    
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://github.com/DiscordV2Bot",  # Optional but useful for tracking
                "X-Title": "Discord Fast Channel Summarizer"  # Optional but useful for tracking
            },
            json={
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant for text summarization.",
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n{text}",
                    },
                ],
                "max_tokens": 8000,  # Gemini 2.0 Flash supports up to 8k output tokens
                "temperature": 0.7,
            }
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"OpenRouter API error: {response.status_code}, {response.text}")
            return f"Error generating summary: API returned status code {response.status_code}"
            
    except Exception as e:
        print(f"Error in OpenRouter API call: {e}")
        return f"Error generating summary: {e}"

def split_message(message, max_length=2000):
    """Split a message into chunks of max_length while preserving blockquote formatting"""
    if len(message) <= max_length:
        return [message]

    parts = []
    lines = message.split("\n")
    current_part = ""
    
    # Find where the header ends and the blockquote begins
    header = ""
    blockquote_start = 0
    for i, line in enumerate(lines):
        if line.startswith(">"):
            blockquote_start = i
            header = "\n".join(lines[:i])
            break
    
    # If no blockquote found, use regular splitting
    if not header:
        current_part = ""
        for line in lines:
            if len(current_part) + len(line) + 1 <= max_length:
                current_part += line + "\n"
            else:
                parts.append(current_part.rstrip())
                current_part = line + "\n"
        
        if current_part:
            parts.append(current_part.rstrip())
        return parts
    
    # Process the blockquote part with proper formatting
    current_part = header + "\n"
    for i in range(blockquote_start, len(lines)):
        line = lines[i]
        if len(current_part) + len(line) + 1 <= max_length:
            current_part += line + "\n"
        else:
            parts.append(current_part.rstrip())
            # Make sure continuation parts start with the blockquote marker
            current_part = "> " + line[2:] if line.startswith("> ") else "> " + line
            current_part += "\n"
    
    if current_part:
        parts.append(current_part.rstrip())
    
    return parts

async def process_channels():
    """Process all channels and generate a single aggregated summary"""
    print(f"Fast Discord Channel Summarizer")
    print(f"Fetching messages from the last {args.hours} hours, limit {args.limit} per channel")
    
    # Aggregate all messages from all channels
    all_messages = []
    channel_names = {}
    
    # First pass: collect all messages and channel names
    for channel_id in CHANNEL_IDS:
        try:
            # Get channel info
            channel_info = fetch_channel_info(channel_id)
            if not channel_info:
                print(f"Skipping channel {channel_id} - could not fetch info")
                continue
                
            channel_name = channel_info.get('name', f'Unknown-{channel_id}')
            channel_names[channel_id] = channel_name
            print(f"Processing channel: {channel_name}")
            
            # Fetch messages
            messages = fetch_messages(channel_id, limit=args.limit, hours=args.hours)
            
            if not messages:
                print(f"No messages found in the last {args.hours} hours for {channel_name}")
                continue
                
            print(f"Found {len(messages)} messages in {channel_name}")
            
            # Add messages to the aggregate list
            for msg in messages:
                if msg.get('content'):
                    author = msg.get('author', {}).get('username', 'Unknown')
                    all_messages.append({
                        'channel': channel_name,
                        'author': author,
                        'content': msg['content']
                    })
            
        except Exception as e:
            print(f"Error processing channel {channel_id}: {e}")
    
    if not all_messages:
        print("No messages found in any channels")
        return
    
    # Sort messages by timestamp if available
    all_messages.sort(key=lambda x: x.get('timestamp', ''))
    
    # Create aggregated conversation text
    conversation_text = ""
    for msg in all_messages:
        conversation_text += f"[{msg['channel']}] {msg['author']}: {msg['content']}\n"
    
    # Debug mode - print to console
    if args.debug:
        print("\n" + "="*50)
        print("AGGREGATED CONVERSATION FROM ALL CHANNELS")
        print("="*50)
        print(conversation_text)
        print("="*50 + "\n")
        
        # Debug mode doesn't send anything to Discord
        
    else:
        # Generate summary using OpenRouter
        print(f"Generating aggregated summary for {len(all_messages)} messages...")
        summary = generate_summary(conversation_text)
        
        # Send summary to Discord using bot
        print(f"Sending summary to Discord using bot...")
        # Add blockquote formatting, but trim the last '>' if it creates a blank line at the end
        formatted_lines = [f"> {line}" for line in summary.split("\n")]
        # Remove any trailing empty quote line
        if formatted_lines and formatted_lines[-1] == "> ":
            formatted_lines = formatted_lines[:-1]
        formatted_summary = "\n".join(formatted_lines)
        
        # Create header with channel list
        channel_list = ", ".join(channel_names.values())
        message_parts = split_message(f"**Aggregated Summary of {len(channel_names)} Channels:**\n{channel_list}\n\n{formatted_summary}")
        
        for part in message_parts:
            success = await send_bot_message(OUTPUT_CHANNEL_ID, part)
            if not success:
                print("Failed to send via bot, falling back to user token")
                send_message(OUTPUT_CHANNEL_ID, part)
            await asyncio.sleep(1)  # Add a small delay between messages
    
    print("Processing complete")

@bot_client.event
async def on_ready():
    """Event handler when the bot is ready"""
    print(f'Bot logged in as {bot_client.user}')
    await process_channels()
    await bot_client.close()  # Close the bot after processing is complete

def main():
    """Main function to run the script"""
    if args.debug:
        # In debug mode, we don't need the bot
        for channel_id in CHANNEL_IDS:
            try:
                channel_info = fetch_channel_info(channel_id)
                channel_name = channel_info.get('name', f'Unknown-{channel_id}') if channel_info else f'Unknown-{channel_id}'
                
                messages = fetch_messages(channel_id, limit=args.limit, hours=args.hours)
                
                if messages:
                    conversation_text = ""
                    for msg in messages:
                        if msg.get('content'):
                            author = msg.get('author', {}).get('username', 'Unknown')
                            conversation_text += f"{author}: {msg['content']}\n"
                    
                    print("\n" + "="*50)
                    print(f"CONVERSATION FROM CHANNEL: {channel_name}")
                    print("="*50)
                    print(conversation_text)
                    print("="*50 + "\n")
            except Exception as e:
                print(f"Error in debug mode for channel {channel_id}: {e}")
    else:
        # Run the bot
        try:
            bot_client.run(BOT_TOKEN)
        except Exception as e:
            print(f"Failed to run bot: {e}")
            print("Falling back to user token method...")
            # Fallback to the old method
            for channel_id in CHANNEL_IDS:
                try:
                    channel_info = fetch_channel_info(channel_id)
                    if not channel_info:
                        continue
                        
                    channel_name = channel_info.get('name', f'Unknown-{channel_id}')
                    messages = fetch_messages(channel_id, limit=args.limit, hours=args.hours)
                    
                    if not messages:
                        continue
                        
                    conversation_text = ""
                    for msg in messages:
                        if msg.get('content'):
                            author = msg.get('author', {}).get('username', 'Unknown')
                            conversation_text += f"{author}: {msg['content']}\n"
                    
                    if not conversation_text:
                        continue
                        
                    summary = generate_summary(conversation_text)
                    formatted_lines = [f"> {line}" for line in summary.split("\n")]
                    if formatted_lines and formatted_lines[-1] == "> ":
                        formatted_lines = formatted_lines[:-1]
                    formatted_summary = "\n".join(formatted_lines)
                    message_parts = split_message(f"**Summary of {channel_name}:**\n{formatted_summary}")
                    
                    for part in message_parts:
                        send_message(OUTPUT_CHANNEL_ID, part)
                        time.sleep(1)
                        
                except Exception as e:
                    print(f"Error processing channel {channel_id}: {e}")

if __name__ == "__main__":
    main() 