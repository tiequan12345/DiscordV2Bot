# Fast Discord Channel Summarizer

A tool that fetches messages from Discord channels and generates summaries using OpenRouter AI. This tool can use either your own Discord user token for reading messages and a bot token for sending summaries.

## Setup

1. Install required packages:
   ```
   pip install requests python-dotenv tiktoken discord.py
   ```

2. Create a `.env` file in the project root with the following variables:
   ```
   # Discord user token (for reading messages)
   DISCORD_TOKEN=your_discord_user_token
   
   # Discord bot token (for sending summaries)
   BOT_TOKEN=your_discord_bot_token
   
   # Comma-separated list of channel IDs to monitor
   CHANNEL_IDS=channel_id1,channel_id2
   
   # Channel ID where summaries will be sent
   OUTPUT_CHANNEL_ID=output_channel_id
   
   # OpenRouter API key for AI summaries
   OPENROUTER_API_KEY=your_openrouter_api_key
   ```

3. Customize `prompt.txt` with your desired prompt for the AI summarizer. This file contains the instructions for how the summaries should be generated.

4. Run the script:
   ```
   python fast_summarizer.py
   ```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" tab and click "Add Bot"
4. Under the "TOKEN" section, click "Copy" to copy your bot token
5. Add this token to your `.env` file as `BOT_TOKEN`
6. Enable necessary Intents for your bot (the script uses default intents)
7. Invite the bot to your server using the OAuth2 URL Generator:
   - Select "bot" scope
   - Select permissions: "Send Messages", "Read Message History"
   - Use the generated URL to invite the bot to your server

## Dual Token System

This tool uses two different tokens:
- **User Token** (`DISCORD_TOKEN`): Used to read messages from source channels
- **Bot Token** (`BOT_TOKEN`): Used to send summary messages to the output channel

If the bot fails to send messages, the script will fall back to using the user token as a backup.

## Command-line Options

- `--hours`: Number of hours of chat history to fetch (default: 12)
- `--limit`: Maximum number of messages per channel (default: 50)
- `--debug`: Print messages to console instead of summarizing. In debug mode, nothing will be sent to Discord.
