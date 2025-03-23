# Fast Discord Channel Summarizer

A tool that fetches messages from Discord channels and generates summaries using OpenRouter AI.

## Setup

1. Install required packages:
   ```
   pip install requests python-dotenv tiktoken
   ```

2. Create a `.env` file in the project root with the following variables:
   ```
   DISCORD_TOKEN=your_discord_token
   CHANNEL_IDS=channel_id1,channel_id2
   OUTPUT_CHANNEL_ID=output_channel_id
   OPENROUTER_API_KEY=your_openrouter_api_key
   ```

3. Customize `prompt.txt` with your desired prompt for the AI summarizer. This file contains the instructions for how the summaries should be generated.

4. Run the script:
   ```
   python fast_summarizer.py
   ```

## Command-line Options

- `--hours`: Number of hours of chat history to fetch (default: 12)
- `--limit`: Maximum number of messages per channel (default: 100)
- `--debug`: Print messages to console instead of summarizing. In debug mode, nothing will be sent to Discord.
