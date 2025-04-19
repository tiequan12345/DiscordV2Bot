import asyncio
import discord

from config import parse_args, Config
from fetcher import fetch_and_process_channel_data
from summarizer import generate_summary
from sender import send_bot_message, send_user_message
from utils import split_message

def build_summary_text(messages):
    text = ""
    for m in messages:
        if m.get('content'):
            text += f"[{m['channel']}] {m['author']}: {m['content']}\n"
    return text

async def process_and_summarize(cfg):
    all_msgs, channel_names, total_msgs = await fetch_and_process_channel_data(
        cfg.CHANNEL_IDS, cfg.args.hours, cfg.TOKEN
    )
    if not all_msgs:
        print("No messages found.")
        return None

    convo_text = build_summary_text(all_msgs)
    if not convo_text.strip():
        print("No message content to summarize.")
        return None

    print(f"Generating summary for {total_msgs} messages...")
    summary = await generate_summary(convo_text, cfg.config_type, cfg.OPENROUTER_API_KEY)
    header = f"**Aggregated Summary ({cfg.args.config}) of {len(channel_names)} Channels ({total_msgs} msgs):**\n"
    header += ", ".join(channel_names.values()) + "\n\n"
    ending = "\n\n\n```\n* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊ ¸* . ﹢ ˖ ✦ ¸ . ﹢ ° ¸. ° ˖ ･ ·̩ ｡ ☆ ﾟ ＊\n```"
    return header + summary.strip() + ending

def run_debug(cfg):
    print("--- DEBUG MODE ---")
    all_msgs, channel_names, total_msgs = asyncio.run(
        fetch_and_process_channel_data(cfg.CHANNEL_IDS, cfg.args.hours, cfg.TOKEN)
    )
    if not all_msgs:
        print("No messages found.")
        return
    convo_text = build_summary_text(all_msgs)
    print("="*50)
    print(f"AGGREGATED CONVERSATION ({cfg.args.config}) - {total_msgs} messages")
    print(", ".join(channel_names.values()))
    print("="*50)
    print(convo_text)
    print("="*50)

def run_fallback(cfg):
    print("--- FALLBACK MODE ---")
    all_msgs, channel_names, total_msgs = asyncio.run(
        fetch_and_process_channel_data(cfg.CHANNEL_IDS, cfg.args.hours, cfg.TOKEN)
    )
    if not all_msgs:
        print("No messages found.")
        return
    convo_text = build_summary_text(all_msgs)
    summary = asyncio.run(generate_summary(convo_text, cfg.config_type, cfg.OPENROUTER_API_KEY))
    header = f"**Aggregated Summary ({cfg.args.config}) of {len(channel_names)} Channels ({total_msgs} msgs) (Fallback):**\n"
    header += ", ".join(channel_names.values()) + "\n\n"
    formatted = "\n".join([f"> {line}" for line in summary.split("\n") if line.strip()])
    full_msg = header + formatted
    parts = split_message(full_msg)
    for part in parts:
        send_user_message(cfg.OUTPUT_CHANNEL_ID, part, cfg.TOKEN)
        import time; time.sleep(1)

def main():
    args = parse_args()
    cfg = Config(args)

    if args.debug:
        run_debug(cfg)
        return

    intents = discord.Intents.default()
    bot_client = discord.Client(intents=intents)

    @bot_client.event
    async def on_ready():
        print(f"Bot logged in as {bot_client.user}")
        try:
            summary_msg = await process_and_summarize(cfg)
        except Exception as e:
            print(f"Error during summarization: {e}")
            summary_msg = None

        if summary_msg:
            parts = split_message(summary_msg)
            success = 0
            for part in parts:
                ok = await send_bot_message(bot_client, cfg.OUTPUT_CHANNEL_ID, part)
                if ok:
                    success +=1
                else:
                    print("Failed to send part via bot.")
                await asyncio.sleep(1)
            if success != len(parts):
                print("Some parts failed, attempting fallback...")
                run_fallback(cfg)
        else:
            print("No summary generated, attempting fallback...")
            run_fallback(cfg)

        await bot_client.close()

    try:
        bot_client.run(cfg.BOT_TOKEN)
    except Exception as e:
        print(f"Bot failed to start: {e}")
        print("Attempting fallback...")
        run_fallback(cfg)

if __name__ == "__main__":
    main()