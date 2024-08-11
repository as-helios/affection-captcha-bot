import logging
import sys
import traceback

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler
from telegram.ext import MessageHandler

from custom import *

load_dotenv()
log_file = '{}/app.log'.format(os.getenv('DATA_FOLDER'))
logging.basicConfig(
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
for package in (silence_packages := (
        'httpx',
        'requests',
        'apscheduler',
)):
    logging.getLogger(package).setLevel(logging.ERROR)


def is_bot(update):
    if message := update.edited_message if update.edited_message else update.message:
        if message.from_user.is_bot:
            return message.from_user.id
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ignore other bots
    if is_bot(update):
        return
    # ignore groups where muting isn't available
    elif update.effective_chat.type not in ('supergroup',):
        return

    restricted_perms = {"can_send_messages": False, "can_send_other_messages": False}
    # new user join the chat
    if update.message.new_chat_members:
        for user in update.message.new_chat_members:
            # skip if bot
            if user.is_bot:
                continue
            # mute the user
            await context.bot.restrict_chat_member(
                update.message.chat_id,
                update.message.from_user.id,
                restricted_perms
            )
            # checks if user is cas banned, do not unmute or give them a captcha
            if await is_user_cas_banned(user.id):
                # ban the user from this channel too
                await context.bot.ban_chat_member(
                    update.message.chat_id,
                    user.id
                )
                # announce user is already cas banned
                await update.message.reply_text(text="{} is CAS Banned!".format(get_name_from_user(user)))
            else:
                # create a captcha file for the user
                user_data = await generate_case_file(update, user, restricted_perms)
                # show the captcha solver
                await solve_captcha(update, context, user_data)
        return


async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # check if captcha file exists for the user
    channel_folder = "{}/channels/{}".format(os.getenv('DATA_FOLDER'), query.message.chat.id)
    os.makedirs(channel_folder, exist_ok=True)
    if not os.path.exists("{}/{}.json".format(channel_folder, query.from_user.id)):
        return
    else:
        # check if user's captcha is already solved
        user_data = load_case_file(query.message.chat.id, query.from_user.id)
        if user_data["captcha_solved"] is True:
            return
        if user_data["message_id"] != query.message.reply_to_message.message_id:
            return
    await query.answer()
    # load the user data
    user_data = load_case_file(query.message.chat.id, query.from_user.id)
    # answer callback query
    await context.bot.answer_callback_query(query.id)
    # check for input
    if not query.data.startswith("key_"):
        if query.data not in ("regenerate", "restart",):
            return
        # do not allow refreshing the captcha too many times
        if user_data["captcha_attempts"] + 1 > int(os.getenv('CAPTCHA_MAX_ATTEMPTS')):
            return
        match query.data:
            case "regenerate":
                # regenerate user data
                await regenerate_captcha_for_case_file(update, user_data)
                # update the caption but not the captcha
                await update_caption_attempts(update, user_data)
            case "restart":
                # reset the answer input
                user_data["captcha_answer_submitted"] = ""
                user_data["captcha_attempts"] += 1
                # save the user_data
                save_case_file(query.message.chat.id, user_data)
                # update the caption but not the captcha
                await update_caption_attempts(update, user_data)
    else:
        # get the number pressed
        number = query.data.replace("key_", "")
        # save the value
        user_data["captcha_answer_submitted"] += str(number)
        # check if the values match
        if user_data["captcha_answer"] == user_data["captcha_answer_submitted"]:
            # reverse perms
            user_data["permissions"] = {k: True for k in user_data["permissions"]}
            # unmute the user
            await context.bot.restrict_chat_member(
                query.message.chat.id,
                user_data["id"],
                user_data["permissions"]
            )
            # log attempts
            user_data["captcha_attempts"] += 1
            # mark captcha is solved
            user_data["captcha_solved"] = True
            # delete the captcha
            await context.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
            # show welcome message to the joiner
            await query.message.reply_to_message.reply_text(os.getenv('WELCOME_MESSAGE').format(get_name_from_user(query.from_user)))
        # check if captcha is the same length but wrong, start over
        elif len(user_data["captcha_answer_submitted"]) >= len(user_data["captcha_answer"]):
            # user ran out of attempts
            if user_data["captcha_attempts"] + 1 > int(os.getenv('CAPTCHA_MAX_ATTEMPTS')):
                # log attempts
                user_data["captcha_attempts"] += 1
                # delete the captcha
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
            else:
                # regenerate user data
                await regenerate_captcha_for_case_file(update, user_data)
                # update the caption but not the captcha
                await update_caption_attempts(update, user_data)
        # save the user_data
        save_case_file(query.message.chat.id, user_data)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    logging.error(tb_string)


if __name__ == '__main__':
    logging.info("-" * 50)
    logging.info("Affection TG Captcha Bot")
    logging.info("-" * 50)
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()
    app.add_handler(MessageHandler(None, handle_message))
    app.add_handler(CallbackQueryHandler(menu_button))
    app.add_error_handler(error_handler)
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
