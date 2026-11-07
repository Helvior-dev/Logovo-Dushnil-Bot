# Logovo Dushnil Bot

A Telegram group bot with chat games, reputation commands, polls, and temporary moderation actions.

## Commands

| Command | Description |
| --- | --- |
| `/raketka` | Random game outcome, including temporary moderation actions |
| `/duel` | Challenge the user whose message you reply to |
| `/lottery` | Start a 30-second group lottery; reply with `+` to join |
| `/roulette` | Play chat roulette |
| `/pandora` | Trigger a random group effect |
| `/plus`, `/minus` | Change another member's reputation by replying to their message |
| `/stats` | Show your moderation and reputation counters |
| `/vip` | Send a random VIP message |
| `/compliment` | Send a random compliment |
| `/vote` | Start a vote about muting a member by replying to their message |

## Requirements

- Python 3.10 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

The bot needs administrator permissions in its group to delete messages, restrict members, ban members, and grant or revoke administrator rights. Some random outcomes may fail if a required permission is missing or the target has higher privileges.

## Run locally

1. Clone the repository and enter its directory:

   ```bash
   git clone https://github.com/Helvior-dev/Logovo-Dushnil-Bot.git
   cd Logovo-Dushnil-Bot
   ```

2. Create and activate a virtual environment:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   On Linux or macOS, use `python3 -m venv venv` and `source venv/bin/activate`.

3. Install dependencies and configure the token:

   ```bash
   pip install -r requirements.txt
   ```

   Copy `.env.example` to `.env` and set `BOT_TOKEN`. Keep `.env` private; it is excluded by `.gitignore`.

4. Start the bot:

   ```bash
   python main.py
   ```

The included `Procfile` starts the bot as a worker with `python main.py`.

## Data and limitations

Moderation counters, reputation, and active games are stored in memory. They reset when the process restarts. Do not run multiple bot instances with the same token; Telegram polling supports only one active `getUpdates` consumer.

## Repository description

Telegram group bot with chat games, polls, reputation commands, and temporary moderation actions.
