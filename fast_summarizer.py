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

# Load environment variables
load_dotenv()

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Discord Fast Channel Summarizer')
parser.add_argument('--hours', type=int, default=12, help='Number of hours of chat history to fetch (default: 12)')
parser.add_argument('--limit', type=int, default=1000, help='Maximum number of messages per channel (default: 1000)')
parser.add_argument('--debug', action='store_true', help='Print messages to console instead of summarizing')
args = parser.parse_args()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')  # Discord user token
CHANNEL_IDS = [int(id) for id in os.getenv('CHANNEL_IDS', '').split(',') if id]  # Channels to monitor
OUTPUT_CHANNEL_ID = int(os.getenv('OUTPUT_CHANNEL_ID', '0'))  # Channel to send summaries
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Set up headers for Discord API
headers = {
    'Authorization': TOKEN,
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
}

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

def send_message(channel_id, content):
    """Send a message to a Discord channel"""
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
    """Split a message into chunks of max_length"""
    if len(message) <= max_length:
        return [message]

    parts = []
    current_part = ""
    words = message.split(" ")

    for word in words:
        if len(current_part) + len(word) + 1 <= max_length:
            current_part += " " + word if current_part else word
        else:
            parts.append(current_part)
            current_part = word

    if current_part:
        parts.append(current_part)

    return parts

def main():
    print(f"Fast Discord Channel Summarizer")
    print(f"Fetching messages from the last {args.hours} hours, limit {args.limit} per channel")
    
    # Process each channel
    for channel_id in CHANNEL_IDS:
        try:
            # Get channel info
            channel_info = fetch_channel_info(channel_id)
            if not channel_info:
                print(f"Skipping channel {channel_id} - could not fetch info")
                continue
                
            channel_name = channel_info.get('name', f'Unknown-{channel_id}')
            print(f"Processing channel: {channel_name}")
            
            # Fetch messages
            messages = fetch_messages(channel_id, limit=args.limit, hours=args.hours)
            
            if not messages:
                print(f"No messages found in the last {args.hours} hours for {channel_name}")
                continue
                
            print(f"Found {len(messages)} messages in {channel_name}")
            
            # Extract content
            conversation_text = ""
            for msg in messages:
                if msg.get('content'):
                    author = msg.get('author', {}).get('username', 'Unknown')
                    conversation_text += f"{author}: {msg['content']}\n"
            
            if not conversation_text:
                print(f"No text content found in messages for {channel_name}")
                continue
                
            # Debug mode - print to console
            if args.debug:
                print("\n" + "="*50)
                print(f"CONVERSATION FROM CHANNEL: {channel_name}")
                print("="*50)
                print(conversation_text)
                print("="*50 + "\n")
                
                # Debug mode doesn't send anything to Discord
                
            else:
                # Generate summary using OpenRouter
                print(f"Generating summary for {channel_name}...")
                summary = generate_summary(conversation_text)
                
                # Send summary to Discord
                print(f"Sending summary to Discord...")
                message_parts = split_message(f"**Summary of {channel_name}:**\n{summary}\n")
                for part in message_parts:
                    send_message(OUTPUT_CHANNEL_ID, part)
                    time.sleep(1)  # Add a small delay between messages
                
        except Exception as e:
            print(f"Error processing channel {channel_id}: {e}")
    
    print("Processing complete")

if __name__ == "__main__":
    main() 