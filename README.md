# Fast Discord Channel Summarizer


A Python 3 tool that **scrapes Discord messages, summarises them with OpenRouter-hosted LLMs, and posts the digest back to Discord**.
Everything is handled by **`fast_summarizer.py`** – no other runner scripts are required.

---

## 1. Features

• Fetches messages from multiple channels concurrently via lightweight HTTP (no privileged intents needed).
• Generates information-dense summaries using any OpenRouter model (defaults to Google Gemini Flash).
• Dual-token delivery: tries your **bot token** first, then falls back to your **user token** if the bot lacks send permissions.
• Two built-in configurations: **DeFi** and **Ordinals** (pick with `--config`).
• `--debug` mode prints the raw conversation instead of summarising—perfect for testing.

---

## 2. Prerequisites

1. **Python 3.9 +** (tested on 3.10).
2. A free [OpenRouter](https://openrouter.ai) account & API key.
3. A Discord **bot** (for sending) *and* optionally a **user token** (for reading & fallback).
   • The bot only needs "Send Messages" + "Read Message History".
   • If you do not supply a user token the fetcher can still work, but some endpoints (e.g. private servers) may be inaccessible.

---

## 3. Quick Start (copy-paste)

```bash
# 1. Clone repo & enter folder
git clone https://github.com/youruser/DiscordV2Bot.git
cd DiscordV2Bot

# 2. (Optional but recommended) create and activate a venv
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create a .env file (see template below)
cp .env.example .env           # or create manually

# 5. Run (DeFi config)
python fast_summarizer.py --config defi
```

---

## 4. `.env` Template

```dotenv
################################
# REQUIRED FOR ALL CONFIGS
################################
OPENROUTER_API_KEY=pk-xxxxxxxxxxxxxxxx          # get from https://openrouter.ai
BOT_TOKEN=MTSx...                               # Discord Bot token
DISCORD_TOKEN=eyJ...                            # (optional) user account token for fallback/extra fetch rights

################################
# -------- DeFi --------------
################################
DEFI_CHANNEL_IDS=123456789012345678,987654321098765432
DEFI_OUTPUT_CHANNEL_ID=111222333444555666

################################
# -------- Ordinals ----------
################################
ORDINALS_CHANNEL_IDS=222333444555666777
ORDINALS_OUTPUT_CHANNEL_ID=777666555444333222
```

**Naming convention matters:** the script upper-cases the `--config` flag and prefixes environment variable names automatically (`DEFI_…`, `ORDINALS_…`).
If you only care about one config, simply omit the other block.

---

## 5. Command-line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--config {defi,ordinals}` | `defi` | Which channel set & prompt to use. |
| `--hours N` | `12` | How many hours of history to fetch. |
| `--limit N` | `50` | *Informational only* ( kept for legacy ); actual fetch loops until the time window ends. |
| `--debug` | off | Print raw messages to terminal; no summarisation, nothing sent to Discord. |

Example:

```bash
# Summarise the last 6 hours of Ordinals chat and print only (no Discord I/O)
python fast_summarizer.py --config ordinals --hours 6 --debug
```

---

## 6. How It Works (high-level)

1. Fetcher (`fetcher.py`) pulls recent messages via Discord’s public HTTP API.
2. Text is concatenated and passed to `generate_summary()` (OpenRouter).
3. The summary is chunk-split to respect Discord’s 2 000 char limit (`utils.split_message`).
4. Sender (`sender.py`) tries to post via bot. If that fails it retries once with your user token.

---

## 7. Output Example

```
**Aggregated DeFi Summary: 4 Channels (127 msgs): alpha-chat, news-feed, call-outs, whale-watch**

1. **Top Signals**
- Mixed, cautious mood after CPI print.
- **XYZ Finance** – Mentions: 3/18 – Positive
- **MegaSwap** – Mentions: 2/11 – Mixed (bull-lean)

2. **Detail Sections**

‣ **XYZ Finance**
Mentions: 3/18 Sentiment: Positive
Links: https://xyz.fi/docs https://twitter.com/xyzfi
Key Points
🚀 Launching ve-tokenomics tonight
⚠️ Audit pending; @SecuGuy notes two medium risk issues

...
```

(The structure adapts automatically when you use `--config ordinals`.)

---

## 8. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "`OPENROUTER_API_KEY not set`" | Missing / wrong key | Check `.env`, ensure no quotes or spaces. |
| Bot starts but never sends | Bot lacks permission in the target channel | Give it "Send Messages" & "Read History". |
| "Unauthorized (401/403)" during fetch | Invalid `DISCORD_TOKEN` or server not accessible to that user | Use a valid user token with access. |
| `discord.PrivilegedIntentsRequired` | Your bot has "Message Content" intent disabled | Enable it in the Developer Portal *or* rely on HTTP fetcher + user token. |

---

## 9. Updating Prompts

Prompt files live in the repo root:

* `prompt.txt` – DeFi
* `ordinals-prompt.txt` – Ordinals

Edit them freely; the summariser reads the correct file based on `--config`.

---

## 10. Contributing

PRs and issue reports are welcome! Focus areas:

* Cleaner prompt engineering
* More granular error handling
* Additional summarisation models

---

Happy summarising! 🎉