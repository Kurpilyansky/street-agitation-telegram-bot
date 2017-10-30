
BOT_TOKEN = "BOT_TOKEN"

BOT_USERNAME = 'Bot'

TELEGRAM_CLI_HOSTNAME = 'localhost'
TELEGRAM_CLI_PORT = 2390

admin_telegram_user_ids = [12211357, 425776827]


def is_admin_user_id(user_id):
    return user_id in admin_telegram_user_ids


error_chat_id = -1001147651737
bug_reports_chat_id = -1001147651737
