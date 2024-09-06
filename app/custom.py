import json
import os
import random

import httpx
from multicolorcaptcha import CaptchaGenerator
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest
from telegram.ext import ContextTypes


def get_name_from_user(user):
    if hasattr(user, 'username') and user.username:
        name = "@{}".format(user.username)
    else:
        name = []
        if user.first_name:
            name.append(user.first_name)
        if user.last_name:
            name.append(user.last_name)
        name = ' '.join(name)
    return name if name else 'ser'


async def delete_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    try:
        await context.bot.delete_message(chat_id=job.data['chat_id'], message_id=job.data['message_id'])
    except BadRequest:
        pass


def generate_numpad(pressed=None):
    if not pressed:
        pressed = []
    numbers = list(range(0, 10))
    random.shuffle(numbers)
    keyboard = [
        [InlineKeyboardButton("*{}*".format(str(n)) if n in pressed else str(n), callback_data="key_{}".format(str(n))) for n in numbers[0:3]],
        [InlineKeyboardButton("*{}*".format(str(n)) if n in pressed else str(n), callback_data="key_{}".format(str(n))) for n in numbers[3:6]],
        [InlineKeyboardButton("*{}*".format(str(n)) if n in pressed else str(n), callback_data="key_{}".format(str(n))) for n in numbers[6:9]],
        [InlineKeyboardButton("🫣", callback_data="restart"), InlineKeyboardButton("*{}*".format(str(numbers[9])) if numbers[9] in pressed else str(numbers[9]), callback_data="key_{}".format(str(numbers[9]))), InlineKeyboardButton("😵‍💫", callback_data="regenerate")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


async def solve_captcha(update, context, user_data):
    text = os.getenv('CAPTCHA_TEXT')
    reply_markup = generate_numpad()
    if update.callback_query:
        msg = await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        msg = await update.message.reply_photo("{}/{}".format(os.getenv('DATA_FOLDER'), user_data["captcha_file"]), caption=text, reply_markup=reply_markup)
        user_data['captcha_message_id'] = msg.message_id
        save_case_file(update.message.chat.id, user_data)
    context.job_queue.run_once(delete_message, int(os.getenv('CAPTCHA_EXPIRES')), data={'chat_id': msg.chat_id, 'message_id': msg.message_id})


async def generate_captcha_image(user_id, mode):
    generator = CaptchaGenerator(2)
    images_folder = "{}/images".format(os.getenv('DATA_FOLDER'))
    os.makedirs(images_folder, exist_ok=True)
    if mode == "math":
        math_captcha = generator.gen_math_captcha_image(difficult_level=int(os.getenv('CAPTCHA_DIFFICULTY')))
        math_image = math_captcha.image
        math_equation_string = math_captcha.equation_str
        math_equation_result = math_captcha.equation_result
        math_image.save("{}/{}_math.png".format(images_folder, user_id), "png")
        return math_equation_string, math_equation_result
    elif mode == "random":
        captcha = generator.gen_captcha_image(difficult_level=int(os.getenv('CAPTCHA_DIFFICULTY')))
        image = captcha.image
        characters = captcha.characters
        image.save("{}/{}_random.png".format(images_folder, user_id), "png")
        return characters, characters
    else:
        raise Exception("No such mode for captchas")


async def generate_case_file(update, user, perms):
    chat_id = update.message.chat_id
    mode = os.getenv("CAPTCHA_MODE")
    question, answer = await generate_captcha_image(user.id, mode)
    user_data = {
        "id": user.id,
        "message_id": update.message.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "permissions": perms,
        "captcha_mode": mode,
        "captcha_file": "images/{}_{}.png".format(user.id, mode),
        "captcha_question": question,
        "captcha_answer": answer,
        "captcha_answer_submitted": "",
        "captcha_attempts": 0,
        "captcha_solved": False
    }
    save_case_file(chat_id, user_data)
    return user_data


async def update_caption_attempts(update, user_data):
    text = os.getenv('CAPTCHA_TEXT')
    if str(user_data["captcha_attempts"]) == os.getenv("CAPTCHA_MAX_ATTEMPTS"):
        text += ". Last chance... "
    text = "{} (Attempts: {})".format(text, user_data["captcha_attempts"])
    await update.callback_query.edit_message_caption(
        caption=text,
        reply_markup=generate_numpad()
    )


async def regenerate_captcha_for_case_file(update, user_data):
    query = update.callback_query
    mode = os.getenv("CAPTCHA_MODE")
    question, answer = await generate_captcha_image(query.from_user.id, mode)
    user_data["captcha_file"] = "images/{}_{}.png".format(query.from_user.id, mode)
    user_data["captcha_question"] = question
    user_data["captcha_answer"] = answer
    user_data["captcha_answer_submitted"] = ""
    user_data["captcha_attempts"] += 1
    # change the captcha photo
    await update.callback_query.edit_message_media(
        media=InputMediaPhoto(open("{}/{}".format(os.getenv('DATA_FOLDER'), user_data["captcha_file"]), "rb")),
        reply_markup=generate_numpad()
    )
    # save the user_data
    save_case_file(query.message.chat.id, user_data)
    return user_data


def load_case_file(chat_id, user_id):
    channel_folder = "{}/channels/{}".format(os.getenv('DATA_FOLDER'), chat_id)
    os.makedirs(channel_folder, exist_ok=True)
    try:
        return json.load(open("{}/{}.json".format(channel_folder, user_id), "r"))
    except FileNotFoundError:
        return {}


def save_case_file(chat_id, user_data):
    channel_folder = "{}/channels/{}".format(os.getenv('DATA_FOLDER'), chat_id)
    os.makedirs(channel_folder, exist_ok=True)
    open("{}/{}.json".format(channel_folder, user_data["id"]), "w").write(json.dumps(user_data, indent=4))


async def is_user_cas_banned(user_id):
    r = httpx.get("https://api.cas.chat/check?user_id={}".format(user_id))
    try:
        resp = r.json()
    except json.decoder.JSONDecodeError:
        return False
    else:
        if resp["ok"] is True:
            if resp["result"]["offenses"] > 0:
                return True
        else:
            return False
