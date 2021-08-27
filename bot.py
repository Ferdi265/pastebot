import os
import os.path
import sys
import string
import logging
import mimetypes

from typing import List, Dict, Optional
from random import choice
from functools import wraps
from dataclasses import dataclass
from time import sleep

from telegram import Update, Message, PhotoSize, File
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

logging.basicConfig(
    format='%(asctime)s [%(name)s - %(levelname)s] %(message)s', level = logging.INFO
)
logger = logging.getLogger(__name__)

# --- configuration globals ---

TOKEN = os.environ.get("TMPBOT_TELEGRAM_TOKEN")
WHITELIST = os.environ.get("TMPBOT_TELEGRAM_WHITELIST", "theFerdi265").split(":")
BOT_NAME = os.environ.get("TMPBOT_BOT_NAME", "tmp.yrlf.at")
PASTE_URL = os.environ.get("TMPBOT_PASTE_URL", "https://tmp.yrlf.at")
PASTE_DIR = os.environ.get("TMPBOT_PASTE_DIR", "tmp")
GENERATE_LENGTH = int(os.environ.get("TMPBOT_GENERATE_LENGTH", "20"))
GENERATE_TRIES = int(os.environ.get("TMPBOT_GENERATE_TRIES", "20"))
DELETE_PASSWORD = os.environ.get("TMPBOT_DEL_ALL", "")
BASE_URL= os.environ.get("TMPBOT_BASE_URL", "")
TIMEOUT = int(os.environ.get("TMPBOT_TIMEOUT", 5))

# --- state globals ---

user_custom_ext: Dict[str, str] = {}

# --- users dict ---
@dataclass
class UserContext:
    total_text: str = ""
    unkown_commands: int = 0
    long_string: bool = False

user_cache: Dict[str, UserContext] = {}

# --- upload implementation details ---

def generate_id(length: int) -> str:
    return ''.join(choice(string.ascii_letters + string.digits) for _ in range(length))

def generate_filename(length: int, ext: str) -> str:
    return f"/{generate_id(length)}.{ext}"

def generate_unique_filename(length: int, tries: int, ext: str) -> str:
    for _ in range(tries):
        id = generate_filename(length, ext)
        if not os.path.exists(id):
            return id

    raise RuntimeError(f"failed to find unique filename after {tries} tries")

# --- upload API ---

def upload_file(message: Message, file: File, ext: str):
    if(ext == "php"):
        ext = "txt"
    id = generate_unique_filename(GENERATE_LENGTH, GENERATE_TRIES, ext)

    with open(PASTE_DIR + id, "wb") as f:
        logger.info(f"Timeout is set to {TIMEOUT}")
        file.download(out = f, timeout=TIMEOUT)

    logger.info(f"uploaded file {PASTE_URL + id}")
    message.reply_text(PASTE_URL + id)

def upload_data(message: Message, data: bytes, ext: str):
    if(ext == "php"):
        ext = "txt"
    id = generate_unique_filename(GENERATE_LENGTH, GENERATE_TRIES, ext)

    with open(PASTE_DIR + id, "wb") as f:
        f.write(data)

    logger.info(f"uploaded file {PASTE_URL + id}")
    message.reply_text(PASTE_URL + id)

# --- handler helpers ---

def message_get_username(message: Message) -> str:
    user = message.from_user
    if user is None:
        name = "unknown user"
    elif user.username is not None:
        name = f"@{user.username}"
    else:
        name = f"@{user.id}"

    return name

def photo_get_best(photos: List[PhotoSize]) -> Optional[PhotoSize]:
    if len(photos) == 0:
        return None

    best = None
    best_size = 0
    for photo in photos:
        if best is None:
            best = photo

        if photo.file_size is not None and photo.file_size > best_size:
            best = photo
            best_size = photo.file_size

    return best

def ext_parse_caption(message: Message, caption: Optional[str], ext: Optional[str]) -> Optional[str]:
    if ext is None and caption is not None:
        extchars = string.ascii_letters + string.digits + '_' + '-'
        capext = caption[1:]

        if not caption.startswith("."):
            message.reply_text("(ignoring unrecognized caption)")
        elif not all(c in extchars for c in capext):
            message.reply_text("(extension contains chars that are not alphanumeric, underscore, or dash)")
        else:
            ext = capext

    return ext

def ext_custom_extension(name: str) -> Optional[str]:
    ext = user_custom_ext.get(name)
    if ext is not None:
        del user_custom_ext[name]

    return ext

def ext_find_extension(message: Message, name: str, default: str, mime: Optional[str] = None, caption: Optional[str] = None, try_custom: bool = True, noisy: bool = True) -> str:
    if caption is None:
        caption = message.caption

    ext = ext_custom_extension(name) if try_custom else None
    ext = ext_parse_caption(message, caption, ext)
    ext = ext_parse_mime(message, mime, ext)
    if ext is None:
        if noisy:
            message.reply_text(f"(unknown extension, defaulting to .{default})")
        ext = default

    return ext

def ext_parse_mime(message: Message, mime: Optional[str], ext: Optional[str]) -> Optional[str]:
    if ext is None and mime is not None:
        mimeext = mimetypes.guess_extension(mime)

        if mimeext is None:
            message.reply_text("(ignoring unrecognized MIME type)")
        elif mimeext.startswith("."):
            ext = mimeext[1:]
        else:
            ext = mimeext

        # hack: python on debian confusingly guesses jpe for image/jpeg
        if ext == 'jpe':
            ext = 'jpg'

    return ext

def wrap_exceptions(fn):
    @wraps(fn)
    def handler(update: Update, context: CallbackContext):
        try:
            fn(update, context)
        except Exception as e:
            logger.exception("uncaught exception in message handler")

            message = update.message
            if message is None:
                return

            message.reply_text(f"sorry, something went wrong there.\n({e})")

    return handler

def remember_user(fn):
    @wraps(fn)
    def handler(update: Update, context: CallbackContext):
        if update.message is not None:
            username = message_get_username(update.message)
            if username not in user_cache:
                user_cache[username] = UserContext()
        fn(update, context)
    return handler

# --- handlers ---

@wrap_exceptions
@remember_user
def handle_start(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    name = message_get_username(message)
    logger.info(f"start message received from {name}")

    message.reply_text(
        f"Hi! I'm the {BOT_NAME} bot.\n" +
        "\n" +
        "Send me stuff and I'll host it!"
    )

@wrap_exceptions
@remember_user
def handle_text(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    text = message.text or ""
    name = message_get_username(message)

    long_str = user_cache[name].long_string
    too_long = (len(text) == 4094)

    if text.startswith("/extension"):
        logger.info(f"custom extension request received from {name}")
        cmd = "extension"
        default_ext = ""
    elif text.startswith("/text"):
        user_cache[name].total_text = ""
        logger.info(f"text upload received from {name}")
        cmd = "text"
        default_ext = "txt"
        if not long_str and len(text) >= 4094:
            user_cache[name].long_string = True
    elif text.startswith("/help"):
        logger.info(f"help requested from {name}")
        cmd = "help"
        default_ext = ""
    elif text.startswith("/debug"):
        cmd = "debug"
        default_ext = ""
    elif not long_str:
        message.reply_text("That's not a valid command, try /text or /extension (or send me a photo or file)")
        user_cache[name].unkown_commands += 1
        if user_cache[name].unkown_commands > 4:
            message.reply_text("Please stop that! It is very anoying!!")
            user_cache[name].unkown_commands = 0
        return
    elif long_str:
        cmd = "append_text"
        default_ext = "txt"
    else:
        logger.info("Unhandled case.")

    parts = text.split('\n', 1)
    cmdline = parts[0]

    args = cmdline.split(' ', 1)
    if len(args) != 2:
        caption = None
    else:
        caption = args[1]


    ext = ext_find_extension(
        message, name, default_ext, caption = caption,
        try_custom = cmd != "extension", noisy = False
    )

    if ext == "php":
        ext = "txt"

    if cmd == "extension":
        if ext == default_ext:
            message.reply_text(f"Uhh, I don't understand what extension you mean")
        else:
            user_custom_ext[name] = ext
            message.reply_text(f"Got it! The next file you upload will have the extension '.{ext}'")
    elif cmd == "text" and not too_long:
        if len(parts) < 2:
            message.reply_text("Huh? You didn't send me anything to upload.")
            return

        data = parts[1]
        upload_data(message, data.encode('utf-8'), ext)
    elif cmd == "append_text":
        data = parts[1]
        user_cache[name].total_text += data
        if len(text) < 4094:
            user_cache[name].long_string = False
            upload_data(message, user_cache[name].total_text.encode('utf-8'), ext)
    elif cmd == "help":
        message.reply_text(f"Here is your help, {name}!\n/help displays this help message.\nYou can use /text to upload text simply by writing it in the line after the command (eg. newline)\n/extension lets you set a custom extension for the file coming after the message.\nIf you want to save a file, just upload it!")
    elif cmd == "debug":
        if name.split("@", 1)[1] == WHITELIST[0]:
            message.reply_text(f"Here is all i know:\n\n{user_cache=}\n\n{user_custom_ext=}")
    
    if long_str == False:
        user_cache[name].long_string = (len(text) >= 4094)

@wrap_exceptions
@remember_user
def handle_photo(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    photo = photo_get_best(message.photo)
    if photo is None:
        logger.warning("photo list was empty")
        return

    name = message_get_username(message)
    logger.info(f"photo upload received from {name}")

    ext = ext_find_extension(message, name, "jpg", noisy = False)
    upload_file(message, photo.get_file(), ext)

@wrap_exceptions
@remember_user
def handle_document(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    document = message.document
    if document is None:
        logger.warning("document was empty")
        return

    name = message_get_username(message)
    logger.info(f"document upload received from {name}")

    ext = ext_find_extension(message, name, "txt", document.mime_type)
    upload_file(message, document.get_file(timeout=TIMEOUT), ext)

@wrap_exceptions
@remember_user
def handle_audio(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    audio = message.audio
    if audio is None:
        logger.warning("audio was empty")
        return

    name = message_get_username(message)
    logger.info(f"audio upload received from {name}")

    ext = ext_find_extension(message, name, "mp3", audio.mime_type)
    upload_file(message, audio.get_file(), ext)

@wrap_exceptions
@remember_user
def handle_voice(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    voice = message.voice
    if voice is None:
        logger.warning("voice was empty")
        return

    name = message_get_username(message)
    logger.info(f"voice upload received from {name}")

    ext = ext_find_extension(message, name, "voice", voice.mime_type)
    upload_file(message, voice.get_file(), ext)

@wrap_exceptions
@remember_user
def handle_video(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    video = message.video
    if video is None:
        logger.warning("video was empty")
        return

    name = message_get_username(message)
    logger.info(f"video upload received from {name}")

    ext = ext_find_extension(message, name, "video", video.mime_type)
    upload_file(message, video.get_file(), ext)

@wrap_exceptions
@remember_user
def handle_video_note(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return

    video_note = message.video_note
    if video_note is None:
        logger.warning("video-note was empty")
        return

    name = message_get_username(message)
    logger.info(f"video-note upload received from {name}")

    ext = ext_find_extension(message, name, "mp4")
    upload_file(message, video_note.get_file(), ext)

@wrap_exceptions
@remember_user
def handle_contact(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return
    
    contact = message.contact
    if contact is None:
        logger.warning("invalid contact")
        return
    
    name = message_get_username(message)
    logger.info(f"contact upload received from {name}")
    upload_data(message, contact.vcard.encode('utf-8'), "vcf")

@wrap_exceptions
@remember_user
def handle_sticker(update: Update, _: CallbackContext):
    message = update.message
    if message is None:
        return
    
    sticker = message.sticker
    if sticker is None:
        logger.warning("invalid sticker")
        return

    _file = sticker.get_file()

    name = message_get_username(message)
    logger.info(f"sticker upload received from {name}")
    upload_file(message, _file, _file.file_path.rsplit('.', 1)[1])

@wrap_exceptions
def check_user(update: Update, _: CallbackContext):
    username = message_get_username(update.message).split("@",1)[1]
    if username not in WHITELIST:
        update.message.reply_text(f"Sorry, you are not on my whitelist, @{username}!")

@wrap_exceptions
def handle_delete(update: Update, _: CallbackContext):
    message = update.message
    message.delete()
    name = message_get_username(message)
    if DELETE_PASSWORD == "":
        logger.info("Deleting is deactivated.")
        return
    if name.split("@", 1)[1] != WHITELIST[0]:
        logger.warning(f"User {name} made a unauthorized request to delete all files!")
        bot_msg = message.reply_text(f"You are unauthorized!")
        sleep(1)
        bot_msg.delete()
        return
    splitted = message.text.split(" ", 1)
    if len(splitted) != 2:
        return
    password = splitted[1]
    if password == DELETE_PASSWORD:
        bot_msg = message.reply_text("Deleting files...")
        sleep(.6)
        bot_msg.delete()
        files = os.listdir(PASTE_DIR)
        files.remove("index.php")
        files.remove("README.md")
        files.remove("PERSIST")
        del_messages = []
        for _file in files:
            if PASTE_DIR[0] != "/":
                filename = f"{os.getcwd()}/{PASTE_DIR}/{_file}"
            else:
                filename = f"{PASTE_DIR}/{_file}"
            os.remove(filename)
            del_messages.append(message.reply_text(f"Deleting file '{filename}'..."))
        sleep(3)
        for msg in del_messages:
            msg.delete()

def main():
    if TOKEN is None:
        logger.error("no TMPBOT_TELEGRAM_TOKEN supplied")
        sys.exit(1)

    if "TMPBOT_TELEGRAM_WHITELIST" not in os.environ:
        logger.warning(f"no TELEGRAM_WHITELIST supplied, defaulting to {WHITELIST}")

    if "TMPBOT_BOT_NAME" not in os.environ:
        logger.warning(f"no TMPBOT_BOT_NAME supplied, defaulting to {BOT_NAME}")

    if "TMPBOT_PASTE_URL" not in os.environ:
        logger.warning(f"no TMPBOT_PASTE_URL supplied, defaulting to {PASTE_URL}")

    if "TMPBOT_PASTE_DIR" not in os.environ:
        logger.warning(f"no TMPBOT_PASTE_DIR supplied, defaulting to {PASTE_DIR}")

    if "TMPBOT_GENERATE_LENGTH" not in os.environ:
        logger.warning(f"no TMPBOT_GENERATE_LENGTH supplied, defaulting to {GENERATE_LENGTH}")

    if "TMPBOT_GENERATE_TRIES" not in os.environ:
        logger.warning(f"no TMPBOT_GENERATE_TRIES supplied, defaulting to {GENERATE_TRIES}")

    if not os.path.exists(PASTE_DIR):
        logger.error(f"PASTE_DIR directory does not exist")
        sys.exit(1)

    if BASE_URL != "":
        updater = Updater(TOKEN, base_url=BASE_URL)
    else:
        updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    whitelist = Filters.user(username = WHITELIST)
    WMessageHandler = lambda filters, handler: MessageHandler(whitelist & filters, handler)
    WCommandHandler = lambda cmd, handler: CommandHandler(cmd, handler, filters = whitelist)

    dispatcher.add_handler(WCommandHandler("start", handle_start))
    dispatcher.add_handler(WCommandHandler("text", handle_text))
    dispatcher.add_handler(WCommandHandler("help", handle_text))
    dispatcher.add_handler(WCommandHandler("extension", handle_text))
    dispatcher.add_handler(WCommandHandler("debug", handle_text))
    dispatcher.add_handler(WCommandHandler("delete", handle_delete))
    dispatcher.add_handler(WMessageHandler(Filters.text, handle_text))
    dispatcher.add_handler(WMessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(WMessageHandler(Filters.document, handle_document))
    dispatcher.add_handler(WMessageHandler(Filters.audio, handle_audio))
    dispatcher.add_handler(WMessageHandler(Filters.voice, handle_voice))
    dispatcher.add_handler(WMessageHandler(Filters.video, handle_video))
    dispatcher.add_handler(WMessageHandler(Filters.video_note, handle_video_note))
    dispatcher.add_handler(WMessageHandler(Filters.sticker, handle_sticker))
    dispatcher.add_handler(WMessageHandler(Filters.contact, handle_contact))
    dispatcher.add_handler(MessageHandler(Filters.text, check_user))

    try:
        updater.start_polling()
    except KeyboardInterrupt:
        logger.info("shutting down")
    except Exception:
        logger.exception("uncaught exception")
        logger.info("shutting down")

if __name__ == '__main__':
    main()
