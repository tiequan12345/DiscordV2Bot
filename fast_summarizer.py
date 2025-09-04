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
import re
import openai

# Load environment variables
load_dotenv()

# Configure OpenAI if key is provided
if os.getenv('OPENAI_API_KEY'):
    openai.api_key = os.getenv('OPENAI_API_KEY')

# Set default model based on provider
if DEFAULT_AI_PROVIDER == 'openai':
    default_model = DEFAULT_OPENAI_MODEL
else:
    default_model = "google/gemini-2.5-flash-preview"

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Discord Fast Channel Summarizer')
parser.add_argument('--hours', type=int, default=12, help='Number of hours of chat history to fetch (default: 12)')
parser.add_argument('--limit', type=int, default=50, help='Maximum number of messages per channel (default: 50, currently informational)') # Note: Limit arg isn't strictly enforced in fetch logic anymore
parser.add_argument('--debug', action='store_true', help='Print messages to console instead of summarizing')
parser.add_argument('--config', type=str, default='defi', choices=['defi', 'ordinals'], help='Configuration type to use (defi or ordinals)')
args = parser.parse_args()

# Determine config type
config_type = args.config.upper() # Use uppercase for env var names

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')  # Discord user token (used for fallback and channel info)
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Discord bot token (primary method)
# Load channel IDs based on config
channel_ids_str = os.getenv(f'{config_type}_CHANNEL_IDS', '')
CHANNEL_IDS = [int(id) for id in channel_ids_str.split(',') if id]
# Load output channel ID based on config
OUTPUT_CHANNEL_ID = int(os.getenv(f'{config_type}_OUTPUT_CHANNEL_ID', '0'))
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DEFAULT_AI_PROVIDER = os.getenv('DEFAULT_AI_PROVIDER', 'openai').lower()
DEFAULT_OPENAI_MODEL = os.getenv('DEFAULT_OPENAI_MODEL', 'gpt-5-mini-2025-08-07')

# Validate required config (common for both bot and fallback)
if not CHANNEL_IDS or OUTPUT_CHANNEL_ID == 0:
    print(f"Error: Missing or invalid environment variables for config '{args.config}':")
    if not CHANNEL_IDS:
        print(f"- {config_type}_CHANNEL_IDS")
    if OUTPUT_CHANNEL_ID == 0:
        print(f"- {config_type}_OUTPUT_CHANNEL_ID")
    exit(1) # Exit if config is missing

# Validate API keys needed for summarization (if not in debug mode)
if not args.debug:
    if DEFAULT_AI_PROVIDER == 'openai' and not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set. Cannot generate summaries.")
        exit(1)
    elif DEFAULT_AI_PROVIDER != 'openai' and not OPENROUTER_API_KEY:
        print("Error: OPENROUTER_API_KEY environment variable not set. Cannot generate summaries.")
        exit(1)

# Validate token presence (need at least one)
if not args.debug and not BOT_TOKEN and not TOKEN:
     print("Error: Neither BOT_TOKEN nor DISCORD_TOKEN environment variables are set. Cannot send messages.")
     exit(1)
elif not TOKEN:
     print("Warning: DISCORD_TOKEN not set. Fallback method will not work if the bot fails.")


# Global headers dictionary removed as it's no longer broadly needed.
# Functions requiring headers will create them locally.
# Set up Discord bot client
intents = discord.Intents.default()
# Required for message content access if your bot needs it, but we fetch via HTTP API
# intents.message_content = True # Uncomment if direct bot message reading is ever added
bot_client = discord.Client(intents=intents)

# --- Helper Functions ---

# Original fetch_channel_info removed, logic moved to fetch_and_process_channel_data
def load_prompt(config_type_local):
    """Load the prompt from the appropriate file based on config"""
    prompt_file = 'prompt.txt' if config_type_local.lower() == 'defi' else 'ordinals-prompt.txt'
    # Build an absolute path relative to this script's directory so cron executions work
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, prompt_file)
    try:
        with open(prompt_path, 'r') as file:
            return file.read()
    except Exception as e:
        print(f"Warning: Error loading {prompt_path}: {e}. Using default prompt.")
        # Fallback prompt if file can't be loaded
        return ("Please summarize the following text in bullet point format for a cryptocurrency trader "
                "looking for alpha so he can act on important ideas. If the bullet point doesn't have "
                "anything to do with defi or crypto, just skip it.")

# Original fetch_messages removed, logic moved to fetch_and_process_channel_data

async def fetch_and_process_channel_data(channel_ids_to_fetch, hours_to_fetch, user_token_for_fetching):
    """
    Fetches channel info and messages concurrently, aggregates, and sorts them.
    Uses the provided user token for fetching operations if available.
    """
    print(f"Fetching data for {len(channel_ids_to_fetch)} channels using {'User Token' if user_token_for_fetching else 'No Token (Info Only)'}...")

    all_messages_data = []
    channel_names = {}
    total_messages_found = 0

    # Need headers for user token requests if token is provided
    local_headers = {}
    if user_token_for_fetching:
        local_headers = {
            'Authorization': user_token_for_fetching,
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
        }

    # Define internal helper to fetch messages for a single channel using the provided token
    async def _fetch_messages_internal(channel_id, cutoff_time):
        if not user_token_for_fetching:
            print(f"Skipping message fetch for {channel_id}: User token not provided for fetching.")
            return []

        messages_list = []
        last_id = None
        while True:
            url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=100"
            if last_id:
                url += f"&before={last_id}"
            try:
                # Use local_headers with the potentially provided user token
                response = await asyncio.to_thread(requests.get, url, headers=local_headers)
                if response.status_code == 401 or response.status_code == 403:
                    print(f"Error fetching messages for {channel_id}: Unauthorized (401/403). Check User Token permissions.")
                    break
                if response.status_code != 200:
                    print(f"Error fetching messages for {channel_id}: {response.status_code}")
                    break

                messages = response.json()
                if not messages: break

                page_messages_in_window = []
                hit_cutoff_in_page = False
                for msg in messages:
                    msg_timestamp_str = msg.get('timestamp')
                    if not msg_timestamp_str: continue
                    try:
                        # Ensure msg_time is timezone-aware for comparison
                        msg_time = datetime.datetime.fromisoformat(msg_timestamp_str.replace('Z', '+00:00'))
                        if msg_time > cutoff_time: # cutoff_time is already timezone-aware
                            page_messages_in_window.append(msg)
                        else:
                            hit_cutoff_in_page = True
                    except ValueError:
                        print(f"Warning: Could not parse timestamp: {msg_timestamp_str}")
                        continue

                messages_list.extend(page_messages_in_window)
                if hit_cutoff_in_page: break
                last_id = messages[-1]['id']
                await asyncio.sleep(0.5) # Rate limiting
            except Exception as e:
                print(f"Exception during _fetch_messages_internal page request for {channel_id}: {e}")
                break
        # Final filter (redundant because of hit_cutoff_in_page logic, but safe)
        return [
            msg for msg in messages_list
            if datetime.datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')) > cutoff_time
        ]


    # Define internal helper to fetch channel info
    async def _fetch_channel_info_internal(channel_id):
         if not user_token_for_fetching:
             print(f"Skipping channel info fetch for {channel_id}: User token not provided for fetching.")
             return {'name': f'Unknown-{channel_id}'}
         url = f"https://discord.com/api/v9/channels/{channel_id}"
         try:
             response = await asyncio.to_thread(requests.get, url, headers=local_headers)
             if response.status_code == 200:
                 return response.json()
             else:
                 print(f"Error fetching channel info for {channel_id}: {response.status_code}")
                 return {'name': f'ErrorFetching-{channel_id}'}
         except Exception as e:
             print(f"Exception during _fetch_channel_info_internal for {channel_id}: {e}")
             return {'name': f'Exception-{channel_id}'}

    # --- Concurrently fetch info and messages ---
    fetch_tasks = []
    channel_processing_tasks = {} # Store tuples of (info_task, messages_task)

    # Ensure cutoff time is timezone-aware
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_to_fetch)

    for channel_id in channel_ids_to_fetch:
        info_task = asyncio.create_task(_fetch_channel_info_internal(channel_id))
        # Pass the cutoff time to the message fetcher
        messages_task = asyncio.create_task(_fetch_messages_internal(channel_id, cutoff))
        fetch_tasks.append(messages_task) # We primarily wait on messages
        channel_processing_tasks[channel_id] = (info_task, messages_task)

    # Wait for all message fetches to complete
    await asyncio.gather(*fetch_tasks)

    # Process results
    for channel_id, (info_task, messages_task) in channel_processing_tasks.items():
        try:
            channel_info = await info_task # Get info result
            channel_name = channel_info.get('name', f'Unknown-{channel_id}')
            channel_names[channel_id] = channel_name
            print(f"Processing channel data: {channel_name} ({channel_id})")

            messages = messages_task.result() # Get message result (already awaited)

            if not messages:
                print(f"  No relevant messages found in the last {hours_to_fetch} hours.")
                continue

            print(f"  Found {len(messages)} relevant messages.")
            total_messages_found += len(messages)

            for msg in messages:
                if msg.get('content'):
                    author = msg.get('author', {}).get('global_name') or msg.get('author', {}).get('username', 'Unknown')
                    all_messages_data.append({
                        'channel': channel_name,
                        'author': author,
                        'content': msg['content'],
                        'timestamp': msg.get('timestamp') # Keep timestamp for sorting
                    })
        except Exception as e:
            print(f"Error processing results for channel {channel_id}: {e}")

    # Sort messages by timestamp
    all_messages_data.sort(key=lambda x: x.get('timestamp', ''))

    return all_messages_data, channel_names, total_messages_found
async def send_bot_message(channel_id, content):
    """Send a message using the bot client"""
    try:
        channel = bot_client.get_channel(channel_id)
        if not channel:
            channel = await bot_client.fetch_channel(channel_id) # Fetch if not cached

        if not channel:
             print(f"Error: Bot could not find channel {channel_id}")
             return False

        await channel.send(content)
        return True
    except discord.Forbidden:
        print(f"Error sending message via bot: Bot lacks permissions for channel {channel_id}.")
        return False
    except Exception as e:
        print(f"Error sending message via bot: {e}")
        return False

def send_user_message(channel_id, content):
    """Send a message to a Discord channel using user token (fallback)"""
    if not TOKEN:
        print(f"Cannot send fallback message to {channel_id}: DISCORD_TOKEN not available.")
        return False

    # Create headers locally for this request
    local_headers = {
        'Authorization': TOKEN, # We already checked TOKEN exists
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
    }

    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    payload = {"content": content}
    try:
        # Use requests directly with locally created headers
        response = requests.post(url, headers=local_headers, json=payload)
        if response.status_code == 200:
            return True
        else:
            print(f"Error sending message via user token: {response.status_code}, {response.text}")
            return False
    except Exception as e:
        print(f"Exception sending message via user token: {e}")
        return False
#async def generate_summary(text, config_type_local, model_name="deepseek/deepseek-r1-0528:free"):
async def generate_summary(text, config_type_local, model_name=default_model):
    """Generate a summary using selected AI provider asynchronously"""
    print(f"Generating summary using {model_name} ({DEFAULT_AI_PROVIDER}) for config '{config_type_local.lower()}'...")
    prompt = load_prompt(config_type_local)

    if DEFAULT_AI_PROVIDER == 'openai':
        # Use OpenAI API
        request_payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for text summarization."},
                {"role": "user", "content": f"{prompt}\n{text}"},
            ],
            "temperature": 0.7,
        }
        try:
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
                **request_payload
            )
            content = response.choices[0].message.content
            # Post-process content similar to OpenRouter
            modified_content = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'[\1](<\2>)', content)
            modified_content = re.sub(r'(?<![<(])(https?://[^\s<>]+)(?![)>])', r'<\1>', modified_content)
            return modified_content
        except Exception as e:
            print(f"Error in OpenAI API call: {e}")
            return f"Error generating summary: {e}"

    else:
        # Use OpenRouter API
        request_payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for text summarization."},
                {"role": "user", "content": f"{prompt}\n{text}"},
            ],
            "temperature": 0.7,
            "reasoning": {
                "enabled": True,
                "effort": "high",
                "exclude": True
            }
        }
        request_headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/DiscordV2Bot", # Optional: Identify your app
            "X-Title": "Discord Fast Channel Summarizer" # Optional: Identify your app
        }

        try:
            response = await asyncio.to_thread(
                requests.post,
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=request_headers,
                json=request_payload,
                timeout=180 # Add a timeout (e.g., 3 minutes)
            )
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # 1. Wrap URLs in markdown links: [Title](URL) -> [Title](<URL>)
                modified_content = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'[\1](<\2>)', content)
                # 2. Wrap plain URLs: http://... -> <http://...> (avoiding those already wrapped or in markdown links)
                modified_content = re.sub(r'(?<![<(])(https?://[^\s<>]+)(?![)>])', r'<\1>', modified_content)
                return modified_content
            else:
                print(f"OpenRouter API error: {response.status_code}, {response.text}")
                return f"Error generating summary: API returned status code {response.status_code}"
        except requests.Timeout:
            print("Error in OpenRouter API call: Request timed out.")
            return "Error generating summary: Request timed out."
        except Exception as e:
            print(f"Error in OpenRouter API call: {e}")
            return f"Error generating summary: {e}"

def split_message(message, max_length=2000):
    """Split a message into chunks of max_length."""
    if len(message) <= max_length:
        return [message]

    parts = []
    lines = message.split("\n")
    current_part = ""

    for line in lines:
        # Check if adding the next line exceeds the max length
        # Add 1 for the newline character that will join lines
        if len(current_part) + len(line) + 1 > max_length:
            # If current_part is not empty, add it to parts
            if current_part:
                parts.append(current_part.rstrip())
            # Start the new part with the current line
            # Handle the case where a single line is longer than max_length
            if len(line) > max_length:
                 # If a single line is too long, split it aggressively
                 # This is a basic split; more sophisticated word boundary splitting could be added
                 for i in range(0, len(line), max_length):
                     parts.append(line[i:i+max_length])
                 current_part = "" # Reset current part after handling the long line
            else:
                 current_part = line + "\n"
        else:
            # Add the line to the current part
            current_part += line + "\n"

    # Add the last part if it's not empty
    if current_part:
        parts.append(current_part.rstrip())

    # Handle edge case where the input message was empty or only newlines
    if not parts and not message.strip():
        return []
    elif not parts: # If message had content but resulted in no parts (e.g., single long line handled)
         # This case might be redundant due to the aggressive split logic, but safe to keep
         if len(message) > max_length:
             # Re-apply aggressive split if somehow missed
             for i in range(0, len(message), max_length):
                 parts.append(message[i:i+max_length])
         elif message: # Non-empty message shorter than max_length wasn't added
             parts.append(message)


    # Ensure no empty strings are in the final list, unless the original message was effectively empty
    final_parts = [p for p in parts if p]
    if not final_parts and message.strip(): # Original had content, but parts are empty? Append original.
        return [message] if len(message) <= max_length else parts # Fallback to original parts if split failed unexpectedly
    elif not final_parts and not message.strip(): # Original was empty/whitespace
        return []
    else:
        return final_parts


async def process_channels_and_summarize(config_type_local):
    """
    Uses the unified fetch function, generates a summary, and prepares the message content.
    This version is intended for the primary (bot) execution path.
    """
    print(f"--- Starting Channel Processing ({config_type_local.lower()}) ---")
    print(f"Fetching messages from the last {args.hours} hours.")

    # Use the unified function. Pass the global user TOKEN for fetching info/messages,
    # as this path originally relied on it via fetch_channel_info/fetch_messages.
    # Note: TOKEN is a global variable loaded from environment.
    all_messages_data, channel_names, total_messages_found = await fetch_and_process_channel_data(
        CHANNEL_IDS, args.hours, TOKEN
    )

    if not all_messages_data:
        print("No messages found in any channels to summarize.")
        return None # Indicate no summary generated

    # Aggregated text creation
    conversation_text = ""
    for msg in all_messages_data:
        # Ensure content exists before appending
        if msg.get('content'):
            conversation_text += f"[{msg['channel']}] {msg['author']}: {msg['content']}\n"

    if not conversation_text.strip():
        print("No message content found to summarize after filtering.")
        return None

    # Generate summary
    print(f"Generating aggregated summary for {total_messages_found} messages...")
    # Pass config_type for prompt loading within generate_summary
    summary = await generate_summary(conversation_text, config_type_local)

    # Format summary (using raw summary as per original logic in the bot path)
    formatted_summary = summary.strip() # Remove leading/trailing whitespace

    # Create header
    channel_list = ", ".join(channel_names.values())
    header = f"**Aggregated Summary ({config_type_local.lower().capitalize()}) of {len(channel_names)} Channels ({total_messages_found} msgs):**\n{channel_list}\n\n"

    # Ending ASCII art
    ending_ascii_art = """* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊"""
    
    # Keep main message without ASCII art
    full_message = header + formatted_summary

    # Return ASCII art separately to be sent in its own message
    ending_art_code_block = f"```\n{ending_ascii_art}\n```"

    print("--- Channel Processing Complete ---")
    return full_message, ending_art_code_block

# --- Bot Event Handler ---

@bot_client.event
async def on_ready():
    """Event handler when the bot is ready"""
    print(f'Bot logged in as {bot_client.user} (ID: {bot_client.user.id})')
    print('------')

    summary_message = ending_art = None
    try:
        summary_message, ending_art = await process_channels_and_summarize(config_type)
    except Exception as e:
        print(f"Error during channel processing and summarization: {e}")
        # Optionally try to send an error message via bot
        try:
            await send_bot_message(OUTPUT_CHANNEL_ID, f"An error occurred during summarization: {e}")
        except Exception as send_e:
             print(f"Failed to send error message via bot: {send_e}")

    if summary_message:
        print(f"Sending summary to Discord channel {OUTPUT_CHANNEL_ID} using bot...")
        # Send main message parts first
        message_parts = split_message(summary_message)
        success_count = 0
        for i, part in enumerate(message_parts):
            success = await send_bot_message(OUTPUT_CHANNEL_ID, part)
            if success:
                success_count += 1
            await asyncio.sleep(1) # Delay between parts

        # Send ASCII art in separate message if it exists
        if ending_art:
            await send_bot_message(OUTPUT_CHANNEL_ID, ending_art)
            if success:
                success_count += 1
            else:
                print(f"Failed to send part {i+1} of the summary via bot.")
                # No automatic fallback here anymore, main() handles initial failure
            await asyncio.sleep(1) # Delay between parts

        if success_count == len(message_parts):
             print("Summary sent successfully via bot.")
        else:
             print(f"Failed to send {len(message_parts) - success_count} parts of the summary via bot.")

    else:
        print("No summary was generated or an error occurred.")

    # Close the bot connection gracefully
    print("Processing complete. Closing bot connection...")
    await bot_client.close()
    print("Bot connection closed.")


# --- Fallback Logic ---

def run_fallback_synchronously(config_type_fallback):
    """
    Fetches messages using the unified function, summarizes, and sends using user token.
    Runs synchronously using asyncio.run().
    """
    print("--- Starting Fallback Processing (User Token) ---")

    if not TOKEN:
        print("Error: DISCORD_TOKEN not set. Cannot run fallback.")
        return

    # Use globally loaded CHANNEL_IDS and OUTPUT_CHANNEL_ID for the specified config
    if not CHANNEL_IDS or OUTPUT_CHANNEL_ID == 0:
         print(f"Error: Missing environment variables for fallback config '{config_type_fallback.lower()}'. Cannot proceed.")
         return

    # --- Fetch data using the unified function ---
    print(f"Fetching messages from the last {args.hours} hours (fallback).")
    try:
        # Run the async fetch function synchronously, passing the user token
        all_messages_data_fallback, channel_names_fallback, total_messages_fallback = asyncio.run(
            fetch_and_process_channel_data(CHANNEL_IDS, args.hours, TOKEN)
        )
    except Exception as e:
        print(f"Error during data fetching in fallback: {e}")
        return # Stop if fetching fails

    if not all_messages_data_fallback:
        print("No messages found in any channels for fallback.")
        return

    # --- Aggregate and Summarize ---
    conversation_text_fallback = ""
    for msg in all_messages_data_fallback:
        if msg.get('content'):
            conversation_text_fallback += f"[{msg['channel']}] {msg['author']}: {msg['content']}\n"

    if not conversation_text_fallback.strip():
        print("No message content found to summarize after filtering (fallback).")
        return

    # Generate summary (run async helper synchronously)
    print(f"Generating aggregated summary for {total_messages_fallback} messages (fallback)...")
    try:
        summary_fallback = asyncio.run(generate_summary(conversation_text_fallback, config_type_fallback))
    except Exception as e:
        print(f"Error during summary generation in fallback: {e}")
        summary_fallback = f"Error generating summary: {e}" # Use error message as summary

    # --- Format and Send ---
    # Use the original fallback formatting with ">"
    formatted_lines_fallback = [f"> {line}" for line in summary_fallback.split("\n") if line.strip()]
    formatted_summary_fallback = "\n".join(formatted_lines_fallback)

    # Create header
    channel_list_fallback = ", ".join(channel_names_fallback.values())
    header_fallback = f"**Aggregated Summary ({config_type_fallback.lower().capitalize()}) of {len(channel_names_fallback)} Channels ({total_messages_fallback} msgs) (Fallback):**\n{channel_list_fallback}\n\n"
    # Note: Fallback doesn't include the ASCII art ending block
    full_message_fallback = header_fallback + formatted_summary_fallback

    # Send summary using user token
    print(f"Sending summary to Discord channel {OUTPUT_CHANNEL_ID} using user token (fallback)...")
    message_parts_fallback = split_message(full_message_fallback)
    success_count_fallback = 0
    for i, part in enumerate(message_parts_fallback):
        # Use the global OUTPUT_CHANNEL_ID
        if send_user_message(OUTPUT_CHANNEL_ID, part):
            success_count_fallback += 1
        else:
            print(f"Failed to send part {i+1} via user token.")
        time.sleep(1) # Delay between parts

    if success_count_fallback == len(message_parts_fallback):
        print("Summary sent successfully via user token (fallback).")
    else:
        print(f"Failed to send {len(message_parts_fallback) - success_count_fallback} parts via user token (fallback).")
    print("--- Fallback Processing Complete ---")


# --- Main Execution Logic ---

def run_debug_mode():
    """
    Runs the message fetching using the unified function and prints the aggregated
    conversation text to the console. Runs synchronously using asyncio.run().
    """
    print("--- Running in DEBUG mode ---")
    config_type_debug = args.config.upper() # Use the global config_type

    # Use globally loaded CHANNEL_IDS
    if not CHANNEL_IDS:
         print(f"Error: No channel IDs configured for debug config '{args.config}'. Cannot proceed.")
         return

    # --- Fetch data using the unified function ---
    print(f"Fetching messages from the last {args.hours} hours (debug).")
    try:
        # Run the async fetch function synchronously, passing the user token (needed for fetching)
        all_messages_debug, channel_names_debug, total_messages_debug = asyncio.run(
            fetch_and_process_channel_data(CHANNEL_IDS, args.hours, TOKEN)
        )
    except Exception as e:
        print(f"Error during data fetching in debug mode: {e}")
        return # Stop if fetching fails

    if not all_messages_debug:
        print("No messages found in any channels for debug.")
        return

    # --- Aggregate and Print ---
    conversation_text_debug = ""
    for msg in all_messages_debug:
        if msg.get('content'):
            conversation_text_debug += f"[{msg['channel']}] {msg['author']}: {msg['content']}\n"

    if not conversation_text_debug.strip():
        print("No message content found to print after filtering (debug).")
        return

    print("\n" + "="*50)
    print(f"AGGREGATED CONVERSATION ({config_type_debug.lower().capitalize()}) - {total_messages_debug} messages")
    channel_list_debug = ", ".join(channel_names_debug.values())
    print(f"Channels: {channel_list_debug}")
    print("="*50)
    print(conversation_text_debug)
    print("="*50 + "\n")
    print("--- Debug Mode Complete ---")


def main():
    """Main function to route execution based on args."""
    if args.debug:
        run_debug_mode()
    else:
        # --- Try running with Bot Token ---
        print(f"Attempting to start bot with config: {args.config}")
        if not BOT_TOKEN:
            print("Error: BOT_TOKEN not set. Attempting fallback to user token method...")
            run_fallback_synchronously(config_type)
            return # Exit after fallback attempt

        try:
            # Start the bot. discord.py manages its own event loop.
            # on_ready will be called, which runs process_channels_and_summarize,
            # sends messages, and then calls bot_client.close().
            bot_client.run(BOT_TOKEN)

            # If bot_client.run() completes without a critical startup error,
            # it means the bot ran successfully and closed itself via on_ready.
            print("Bot execution cycle finished.")

        except discord.LoginFailure:
             print("Error: Invalid BOT_TOKEN. Falling back to user token method...")
             run_fallback_synchronously(config_type)
        except discord.PrivilegedIntentsRequired:
             print("Error: Bot is missing privileged intents (like Message Content or Server Members).")
             print("Please enable required intents in the Discord Developer Portal.")
             # Optionally attempt fallback if intents are the issue
             print("Falling back to user token method...")
             run_fallback_synchronously(config_type)
        except Exception as e:
            # Catch other potential critical startup errors (network, etc.)
            print(f"Failed to run bot due to unexpected error during startup: {e}")
            print("Falling back to user token method...")
            run_fallback_synchronously(config_type)


# --- Script Entry Point ---
if __name__ == "__main__":
    print("--- Discord Fast Channel Summarizer ---")
    print(f"Configuration: {args.config}")
    print(f"Target Channel IDs: {CHANNEL_IDS}")
    print(f"Output Channel ID: {OUTPUT_CHANNEL_ID}")
    print(f"History Hours: {args.hours}")
    print("-" * 30)

    try:
        main() # Execute the main logic
    except Exception as e:
        # Catch any unexpected errors not handled within main() or its calls
        print(f"FATAL ERROR in script execution: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging

    print("-" * 30)
    print("Script finished.")