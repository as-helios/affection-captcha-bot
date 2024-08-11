# affection-captcha-bot

Users are auto muted by default. They can unmute themself if they successfully click the correct 4 numbers. The number pad is randomized each time. Difficulty, attempts, and time to expiration can be set in the env file.

## Getting Started

### Bare Metal

- Clone the repo
- Open the `app` folder
- Rename `sample.env` to `.env`
- Enter your Telegram bot token from @botfather
- Run by typing `python main.py`

### Docker

- Run by typing `docker compose up -d` in the repo's root folder

### Telegram

- Add the bot to your supergroup as admin
- The bot only works for supergroups (public)