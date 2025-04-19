import os
import argparse
from dotenv import load_dotenv

load_dotenv()

def parse_args():
    parser = argparse.ArgumentParser(description='Discord Fast Channel Summarizer')
    parser.add_argument('--hours', type=int, default=12, help='Number of hours of chat history to fetch (default: 12)')
    parser.add_argument('--limit', type=int, default=50, help='Maximum number of messages per channel (default: 50)')
    parser.add_argument('--debug', action='store_true', help='Print messages to console instead of summarizing')
    parser.add_argument('--config', type=str, default='defi', choices=['defi', 'ordinals'], help='Configuration type to use (defi or ordinals)')
    return parser.parse_args()

class Config:
    def __init__(self, args):
        self.args = args
        self.config_type = args.config.upper()

        self.TOKEN = os.getenv('DISCORD_TOKEN')
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')
        self.OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

        channel_ids_str = os.getenv(f'{self.config_type}_CHANNEL_IDS', '')
        self.CHANNEL_IDS = [int(cid) for cid in channel_ids_str.split(',') if cid]

        self.OUTPUT_CHANNEL_ID = int(os.getenv(f'{self.config_type}_OUTPUT_CHANNEL_ID', '0'))

        self.validate()

    def validate(self):
        if not self.CHANNEL_IDS or self.OUTPUT_CHANNEL_ID == 0:
            print(f"Error: Missing or invalid environment variables for config '{self.args.config}':")
            if not self.CHANNEL_IDS:
                print(f"- {self.config_type}_CHANNEL_IDS")
            if self.OUTPUT_CHANNEL_ID == 0:
                print(f"- {self.config_type}_OUTPUT_CHANNEL_ID")
            exit(1)

        if not self.args.debug and not self.OPENROUTER_API_KEY:
            print("Error: OPENROUTER_API_KEY environment variable not set. Cannot generate summaries.")
            exit(1)

        if not self.args.debug and not self.BOT_TOKEN and not self.TOKEN:
            print("Error: Neither BOT_TOKEN nor DISCORD_TOKEN environment variables are set. Cannot send messages.")
            exit(1)
        elif not self.TOKEN:
            print("Warning: DISCORD_TOKEN not set. Fallback method will not work if the bot fails.")