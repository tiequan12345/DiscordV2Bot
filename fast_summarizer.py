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
# Add config argument
parser.add_argument('--config', type=str, default='defi', choices=['defi', 'ordinals'], help='Configuration type to use (defi or ordinals)')
args = parser.parse_args()

# Determine config type
config_type = args.config.upper() # Use uppercase for env var names

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')  # Discord user token
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Discord bot token
# Load channel IDs based on config
channel_ids_str = os.getenv(f'{config_type}_CHANNEL_IDS', '')
CHANNEL_IDS = [int(id) for id in channel_ids_str.split(',') if id]
# Load output channel ID based on config
OUTPUT_CHANNEL_ID = int(os.getenv(f'{config_type}_OUTPUT_CHANNEL_ID', '0'))
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Validate required config
if not CHANNEL_IDS or OUTPUT_CHANNEL_ID == 0:
    print(f"Error: Missing or invalid environment variables for config '{args.config}':")
    if not CHANNEL_IDS:
        print(f"- {config_type}_CHANNEL_IDS")
    if OUTPUT_CHANNEL_ID == 0:
        print(f"- {config_type}_OUTPUT_CHANNEL_ID")
    exit(1) # Exit if config is missing

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

# Use asyncio.to_thread for blocking I/O
async def fetch_channel_info(channel_id):
    """Fetch channel name and other info asynchronously"""
    url = f"https://discord.com/api/v9/channels/{channel_id}"
    
    try:
        # Run the synchronous requests.get in a separate thread
        response = await asyncio.to_thread(requests.get, url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"Error fetching channel info: {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception during fetch_channel_info: {e}")
        return None

def load_prompt(config_type):
    """Load the prompt from the appropriate file based on config"""
    prompt_file = 'prompt.txt' if config_type.lower() == 'defi' else 'ordinals-prompt.txt'
    try:
        with open(prompt_file, 'r') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading {prompt_file}: {e}")
        # Fallback prompt if file can't be loaded
        return "Please summarize the following text in bullet point format for a cryptocurrency trader looking for alpha so he can act on important ideas. If the bullet point doesn't have anything to do with defi or crypto, just skip it."

async def fetch_messages(channel_id, limit=100, hours=12):
    """Fetch all messages from a channel within the time window using pagination asynchronously"""
    cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    cutoff_str = cutoff_time.isoformat()
    
    all_messages = []
    last_id = None
    
    while True:
        # Build URL with pagination
        url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=100"
        if last_id:
            url += f"&before={last_id}"
            
        try:
            # Run the synchronous requests.get in a separate thread
            response = await asyncio.to_thread(requests.get, url, headers=headers)
            
            if response.status_code != 200:
                print(f"Error fetching messages: {response.status_code}")
                break
                
            messages = response.json()
            if not messages:  # No more messages to fetch
                break
                
            # Filter by time and add to our list
            processed_count = 0
            for msg in messages:
                # Ensure timestamp is valid before comparison
                msg_timestamp_str = msg.get('timestamp')
                if not msg_timestamp_str:
                    continue # Skip messages without timestamps

                try:
                    # Attempt to parse the timestamp
                    msg_time = datetime.datetime.fromisoformat(msg_timestamp_str.replace('Z', '+00:00'))
                    if msg_time <= cutoff_time:
                        # We've hit our time cutoff for messages fetched in this batch
                        # Return messages collected so far
                        if processed_count == 0: # If the very first message is too old
                           return all_messages
                        else: # Return messages collected before hitting the cutoff
                           # Need to signal outer loop to stop
                           # Let's refine this logic: Fetch pages until the *last* message of a page is older
                           pass # Continue processing this batch

                except ValueError:
                    print(f"Warning: Could not parse timestamp: {msg_timestamp_str}")
                    continue # Skip messages with invalid timestamps

                all_messages.append(msg)
                processed_count += 1

            # Check if the last message of the batch is older than the cutoff
            last_msg_time_str = messages[-1].get('timestamp')
            if last_msg_time_str:
                try:
                    last_msg_time = datetime.datetime.fromisoformat(last_msg_time_str.replace('Z', '+00:00'))
                    if last_msg_time <= cutoff_time:
                        # Last message in this batch is older than cutoff, no need to fetch more pages
                        break
                except ValueError:
                    pass # Ignore parse error for cutoff check

            # Update last_id for next page
            last_id = messages[-1]['id']
            
            # Optional: Add a small async delay to avoid hammering the API
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Exception during fetch_messages page request: {e}")
            break # Stop fetching on error
    
    # Filter final list again just in case (though the loop logic should handle it)
    final_filtered_messages = [
        msg for msg in all_messages
        if datetime.datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')) > cutoff_time
    ]
    return final_filtered_messages


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

async def generate_summary(text, config_type, model_name="google/gemini-2.0-flash-001"):
    """Generate a summary using OpenRouter API asynchronously"""
    print(f"Generating summary using {model_name} for config '{config_type.lower()}'...")

    # Load the prompt from file based on config
    prompt = load_prompt(config_type) # load_prompt is synchronous, no change needed

    request_payload = {
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
        "max_tokens": 8000,
        "temperature": 0.7,
    }
    
    request_headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/DiscordV2Bot",
        "X-Title": "Discord Fast Channel Summarizer"
    }

    try:
        # Run the synchronous requests.post in a separate thread
        response = await asyncio.to_thread(
            requests.post,
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=request_headers,
            json=request_payload
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

async def process_channels(config_type):
    """Process all channels for the given config and generate a single aggregated summary"""
    print(f"Fast Discord Channel Summarizer - Config: {config_type.lower()}")
    print(f"Fetching messages from the last {args.hours} hours, limit {args.limit} per channel")

    # Aggregate all messages from all channels
    all_messages = []
    channel_names = {}

    # First pass: collect all messages and channel names
    for channel_id in CHANNEL_IDS:
        try:
            # Get channel info asynchronously
            channel_info = await fetch_channel_info(channel_id)
            if not channel_info:
                print(f"Skipping channel {channel_id} - could not fetch info")
                continue

            channel_name = channel_info.get('name', f'Unknown-{channel_id}')
            channel_names[channel_id] = channel_name
            print(f"Processing channel: {channel_name}")

            # Fetch messages asynchronously
            messages = await fetch_messages(channel_id, hours=args.hours) # Removed limit=args.limit as it's not used effectively

            if not messages:
                print(f"No messages found in the last {args.hours} hours for {channel_name}")
                continue

            print(f"Found {len(messages)} messages in {channel_name}")

            # Removed duplicate print statement

            # Add messages to the aggregate list
            for msg in messages:
                # Ensure the message has content before adding
                if msg.get('content'):
                    author = msg.get('author', {}).get('username', 'Unknown')
                    all_messages.append({
                        'channel': channel_name,
                        'author': author,
                        'content': msg['content'],
                        'timestamp': msg.get('timestamp') # Keep timestamp for sorting
                    })
        # This except block should be aligned with the 'try' block above
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
        # Ensure author and content exist before adding to text
        author = msg.get('author', 'Unknown')
        content = msg.get('content', '')
        channel_name = msg.get('channel', 'UnknownChannel')
        conversation_text += f"[{channel_name}] {author}: {content}\n"


    # Debug mode - print to console
    if args.debug:
        print("\n" + "="*50)
        print("AGGREGATED CONVERSATION FROM ALL CHANNELS")
        print("="*50)
        print(conversation_text)
        print("="*50 + "\n")
        # Debug mode doesn't send anything to Discord
    else:
        # Generate summary using OpenRouter asynchronously
        print(f"Generating aggregated summary for {len(all_messages)} messages...")
        summary = await generate_summary(conversation_text, config_type)

        # Send summary to Discord using bot
        print(f"Sending summary to Discord using bot...")
        # Add blockquote formatting, but trim the last '>' if it creates a blank line at the end
        formatted_lines = [f"> {line}" for line in summary.split("\n")]
        if formatted_lines and formatted_lines[-1] == "> ":
            formatted_lines = formatted_lines[:-1]
        formatted_summary = "\n".join(formatted_lines)

        # Create header with channel list and config type
        channel_list = ", ".join(channel_names.values())
        message_parts = split_message(f"**Aggregated Summary ({config_type.lower().capitalize()}) of {len(channel_names)} Channels:**\n{channel_list}\n\n{formatted_summary}")

        for part in message_parts:
            success = await send_bot_message(OUTPUT_CHANNEL_ID, part)
            if not success:
                print("Failed to send via bot, falling back to user token (fallback handled in main())")
            await asyncio.sleep(1)

    print("Processing complete")


@bot_client.event
async def on_ready():
    """Event handler when the bot is ready"""
    print(f'Bot logged in as {bot_client.user} (ID: {bot_client.user.id})')
    print('------')
    
    try:
        await process_channels(args.config.upper())
    except Exception as e:
        print(f"Error in process_channels: {e}")
    finally:
        # Ensure the bot closes gracefully
        print("Closing bot connection...")
        await bot_client.close()
        print("Bot connection closed.")

# --- Main Execution Logic ---

async def run_debug_mode():
    """Runs the message fetching and printing logic synchronously for debug mode."""
    print("Running in DEBUG mode. Fetching messages synchronously...")
    config_type_debug = args.config.upper()
    channel_ids_str_debug = os.getenv(f'{config_type_debug}_CHANNEL_IDS', '')
    channel_ids_debug = [int(id) for id in channel_ids_str_debug.split(',') if id]

    if not channel_ids_debug:
         print(f"Error: Missing environment variables for debug config '{args.config}'. Cannot proceed.")
         return

    all_messages_debug = []
    channel_names_debug = {}

    # Fetch all channel info and messages asynchronously first
    fetch_tasks = []
    channel_info_tasks = {}

    for channel_id in channel_ids_debug:
        # Create tasks to fetch info and messages concurrently
        info_task = asyncio.create_task(fetch_channel_info(channel_id))
        messages_task = asyncio.create_task(fetch_messages(channel_id, hours=args.hours)) # Removed limit=args.limit as it's not used effectively
        fetch_tasks.append(messages_task)
        channel_info_tasks[channel_id] = (info_task, messages_task) # Store both tasks

    # Wait for all tasks to complete
    await asyncio.gather(*fetch_tasks, *[t[0] for t in channel_info_tasks.values()]) # Gather info and message tasks

    # Process results
    for channel_id, (info_task, messages_task) in channel_info_tasks.items():
        try:
            channel_info = info_task.result()
            channel_name = channel_info.get('name', f'Unknown-{channel_id}') if channel_info else f'Unknown-{channel_id}'
            channel_names_debug[channel_id] = channel_name

            messages = messages_task.result()

            if messages:
                print(f"Found {len(messages)} messages in {channel_name}")
                for msg in messages:
                    if msg.get('content'):
                        author = msg.get('author', {}).get('username', 'Unknown')
                        all_messages_debug.append({
                            'channel': channel_name,
                            'author': author,
                            'content': msg['content'],
                            'timestamp': msg.get('timestamp')
                        })
            else:
                 print(f"No messages found in the last {args.hours} hours for {channel_name}")

        except Exception as e:
            print(f"Error processing results for channel {channel_id} in debug mode: {e}")


    if not all_messages_debug:
        print("No messages found in any channels for debug.")
        return

    all_messages_debug.sort(key=lambda x: x.get('timestamp', ''))
    conversation_text_debug = ""
    for msg in all_messages_debug:
        # Ensure author and content exist before adding to text
        author = msg.get('author', 'Unknown')
        content = msg.get('content', '')
        channel_name = msg.get('channel', 'UnknownChannel')
        conversation_text_debug += f"[{channel_name}] {author}: {content}\n"


    print("\n" + "="*50)
    print(f"AGGREGATED CONVERSATION FROM ALL CHANNELS ({config_type_debug.lower().capitalize()})")
    print("="*50)
    print(conversation_text_debug)
    print("="*50 + "\n")


if __name__ == "__main__":
    if args.debug:
        # Run the debug logic using asyncio.run
        try:
            asyncio.run(run_debug_mode())
        except Exception as e:
            print(f"Error running debug mode: {e}")
    else:
        # Run the Discord bot
        if not BOT_TOKEN:
             print("Error: BOT_TOKEN environment variable not set. Cannot start bot.")
        else:
            try:
                print("Starting Discord bot...")
                bot_client.run(BOT_TOKEN)
            except discord.LoginFailure:
                 print("Error: Invalid BOT_TOKEN. Please check your .env file.")
            except Exception as e:
                print(f"Error starting bot: {e}")

def main():
    """Main function to run the script"""
    if args.debug:
        # In debug mode, we don't need the bot, run synchronously
        config_type_debug = args.config.upper()
        channel_ids_str_debug = os.getenv(f'{config_type_debug}_CHANNEL_IDS', '')
        channel_ids_debug = [int(id) for id in channel_ids_str_debug.split(',') if id]

        if not channel_ids_debug:
             print(f"Error: Missing environment variables for debug config '{args.config}'. Cannot proceed.")
             return

        all_messages_debug = []
        channel_names_debug = {}
        for channel_id in channel_ids_debug:
            try:
                # Run async fetch_channel_info synchronously for debug
                channel_info = asyncio.run(fetch_channel_info(channel_id))
                channel_name = channel_info.get('name', f'Unknown-{channel_id}') if channel_info else f'Unknown-{channel_id}'
                channel_names_debug[channel_id] = channel_name

                # Run async fetch_messages synchronously for debug
                messages = asyncio.run(fetch_messages(channel_id, limit=args.limit, hours=args.hours))

                if messages:
                    print(f"Found {len(messages)} messages in {channel_name}")
                    for msg in messages:
                        if msg.get('content'):
                            author = msg.get('author', {}).get('username', 'Unknown')
                            all_messages_debug.append({
                                'channel': channel_name,
                                'author': author,
                                'content': msg['content'],
                                'timestamp': msg.get('timestamp')
                            })
            except Exception as e:
                print(f"Error in debug mode for channel {channel_id}: {e}")

        if not all_messages_debug:
            print("No messages found in any channels for debug.")
            return

        all_messages_debug.sort(key=lambda x: x.get('timestamp', ''))
        conversation_text_debug = ""
        for msg in all_messages_debug:
            # Ensure author and content exist before adding to text
            author = msg.get('author', 'Unknown')
            content = msg.get('content', '')
            channel_name = msg.get('channel', 'UnknownChannel')
            conversation_text_debug += f"[{channel_name}] {author}: {content}\n"


        print("\n" + "="*50)
        print(f"AGGREGATED CONVERSATION FROM ALL CHANNELS ({config_type_debug.lower().capitalize()})")
        print("="*50)
        print(conversation_text_debug)
        print("="*50 + "\n")

def main():
    """Main function to run the script"""
    if args.debug:
        # In debug mode, we don't need the bot, run synchronously
        config_type_debug = args.config.upper()
        channel_ids_str_debug = os.getenv(f'{config_type_debug}_CHANNEL_IDS', '')
        channel_ids_debug = [int(id) for id in channel_ids_str_debug.split(',') if id]

        if not channel_ids_debug:
             print(f"Error: Missing environment variables for debug config '{args.config}'. Cannot proceed.")
             return

        all_messages_debug = []
        channel_names_debug = {}
        for channel_id in channel_ids_debug:
            try:
                # Run async fetch_channel_info synchronously for debug
                channel_info = asyncio.run(fetch_channel_info(channel_id))
                channel_name = channel_info.get('name', f'Unknown-{channel_id}') if channel_info else f'Unknown-{channel_id}'
                channel_names_debug[channel_id] = channel_name

                # Run async fetch_messages synchronously for debug
                messages = asyncio.run(fetch_messages(channel_id, limit=args.limit, hours=args.hours))

                if messages:
                    print(f"Found {len(messages)} messages in {channel_name}")
                    for msg in messages:
                        if msg.get('content'):
                            author = msg.get('author', {}).get('username', 'Unknown')
                            all_messages_debug.append({
                                'channel': channel_name,
                                'author': author,
                                'content': msg['content'],
                                'timestamp': msg.get('timestamp')
                            })
            except Exception as e:
                print(f"Error in debug mode for channel {channel_id}: {e}")

        if not all_messages_debug:
            print("No messages found in any channels for debug.")
            return

        all_messages_debug.sort(key=lambda x: x.get('timestamp', ''))
        conversation_text_debug = ""
        for msg in all_messages_debug:
            # Ensure author and content exist before adding to text
            author = msg.get('author', 'Unknown')
            content = msg.get('content', '')
            channel_name = msg.get('channel', 'UnknownChannel')
            conversation_text_debug += f"[{channel_name}] {author}: {content}\n"


        print("\n" + "="*50)
        print(f"AGGREGATED CONVERSATION FROM ALL CHANNELS ({config_type_debug.lower().capitalize()})")
        print("="*50)
        print(conversation_text_debug)
        print("="*50 + "\n")

    else:
        # Run the bot asynchronously
        try:
            # discord.py manages its own event loop when run is called
            print(f"Starting bot with config: {args.config}")
            if not BOT_TOKEN:
                print("Error: BOT_TOKEN is not set in the environment variables.")
                # Attempt fallback directly if bot token is missing
                raise Exception("BOT_TOKEN missing, attempting fallback.")

            bot_client.run(BOT_TOKEN)

        except Exception as e:
            print(f"Failed to run bot: {e}")
            print("Falling back to user token method...")
            # Fallback logic remains the same
            config_type_fallback = args.config.upper()
            channel_ids_str_fallback = os.getenv(f'{config_type_fallback}_CHANNEL_IDS', '')
            channel_ids_fallback = [int(id) for id in channel_ids_str_fallback.split(',') if id]
            output_channel_id_fallback = int(os.getenv(f'{config_type_fallback}_OUTPUT_CHANNEL_ID', '0'))

            if not channel_ids_fallback or output_channel_id_fallback == 0:
                 print(f"Error: Missing fallback environment variables for config '{args.config}'. Cannot proceed with user token fallback.")
                 return

            # Aggregate messages first for fallback
            all_messages_fallback = []
            channel_names_fallback = {}
            for channel_id in channel_ids_fallback:
                try:
                    # Run async fetch_channel_info synchronously for fallback
                    channel_info = asyncio.run(fetch_channel_info(channel_id))
                    if not channel_info:
                        print(f"Skipping channel {channel_id} in fallback - could not fetch info")
                        continue

                    channel_name = channel_info.get('name', f'Unknown-{channel_id}')
                    channel_names_fallback[channel_id] = channel_name
                    print(f"Processing channel (fallback): {channel_name}")

                    # Run async fetch_messages synchronously for fallback
                    messages = asyncio.run(fetch_messages(channel_id, limit=args.limit, hours=args.hours))

                    if not messages:
                        print(f"No messages found in the last {args.hours} hours for {channel_name} (fallback)")
                        continue

                    print(f"Found {len(messages)} messages in {channel_name} (fallback)")

                    for msg in messages:
                        if msg.get('content'):
                            author = msg.get('author', {}).get('username', 'Unknown')
                            all_messages_fallback.append({
                                'channel': channel_name,
                                'author': author,
                                'content': msg['content'],
                                'timestamp': msg.get('timestamp')
                            })

                except Exception as e:
                    print(f"Error processing channel {channel_id} in fallback mode: {e}")

            if not all_messages_fallback:
                print("No messages found in any channels for fallback.")
                return

            all_messages_fallback.sort(key=lambda x: x.get('timestamp', ''))
            conversation_text_fallback = ""
            for msg in all_messages_fallback:
                # Ensure author and content exist before adding to text
                author = msg.get('author', 'Unknown')
                content = msg.get('content', '')
                channel_name = msg.get('channel', 'UnknownChannel')
                conversation_text_fallback += f"[{channel_name}] {author}: {content}\n"


            # Generate single summary for fallback (run async generate_summary synchronously)
            print(f"Generating aggregated summary for {len(all_messages_fallback)} messages (fallback)...")
            summary_fallback = asyncio.run(generate_summary(conversation_text_fallback, config_type_fallback))

            # Format and send summary for fallback
            formatted_lines_fallback = [f"> {line}" for line in summary_fallback.split("\n")]
            if formatted_lines_fallback and formatted_lines_fallback[-1] == "> ":
                formatted_lines_fallback = formatted_lines_fallback[:-1]
            formatted_summary_fallback = "\n".join(formatted_lines_fallback)

            channel_list_fallback = ", ".join(channel_names_fallback.values())
            message_parts_fallback = split_message(f"**Aggregated Summary ({config_type_fallback.lower().capitalize()}) of {len(channel_names_fallback)} Channels (Fallback):**\n{channel_list_fallback}\n\n{formatted_summary_fallback}")

            print(f"Sending summary to Discord using user token (fallback)...")
            for part in message_parts_fallback:
                send_message(output_channel_id_fallback, part)
                time.sleep(1)

            print("Fallback processing complete.")


# Add the script entry point check
if __name__ == "__main__":
    # Initialize logging
    print("Starting Discord Fast Channel Summarizer")
    print(f"Configuration: {args.config}")
    print(f"Channel IDs: {CHANNEL_IDS}")
    print(f"Output Channel ID: {OUTPUT_CHANNEL_ID}")

    try:
        main()
    except Exception as e:
        print(f"Fatal error occurred in main execution: {e}")
        # Optionally re-raise or handle differently
        # raise e