
BOT_TOKEN = "BOT_TOKEN"

admin_telegram_user_ids = [12211357]


def is_admin_user_id(user_id):
    return user_id in admin_telegram_user_ids
