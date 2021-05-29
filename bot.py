import os
import os.path
import sys
import string
import logging
import mimetypes

from typing import *
from random import choice
from functools import wraps

from telegram import Update, Message, PhotoSize, File
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

logging.basicConfig(
    format='%(asctime)s [%(name)s - %(levelname)s] %(message)s', level = logging.INFO
)
logger = logging.getLogger(__name__)

# --- configuration globals ---

TOKEN = os.environ.get("TMPBOT_TELEGRAM_TOKEN")
WHITELIST = os.environ.get("TMPBOT_TELEGRAM_WHITELIST", "theFerdi265").split(":")
PASTE_URL = os.environ.get("TMPBOT_PASTE_URL", "https://tmp.yrlf.at")
PASTE_DIR = os.environ.get("TMPBOT_PASTE_DIR", "tmp")
GENERATE_LENGTH = int(os.environ.get("TMPBOT_GENERATE_LENGTH", "20"))
GENERATE_TRIES = int(os.environ.get("TMPBOT_GENERATE_TRIES", "20"))

# --- state globals ---

user_custom_ext: Dict[str, str] = {}

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
    id = generate_unique_filename(GENERATE_LENGTH, GENERATE_TRIES, ext)

    with open(PASTE_DIR + id, "wb") as f:
        file.download(out = f)

    logger.info(f"uploaded file {PASTE_URL + id}")
    message.reply_text(PASTE_URL + id)

def upload_data(message: Message, data: bytes, ext: str):
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

def ext_custom_extension(message: Message, name: str) -> Optional[str]:
    ext = user_custom_ext.get(name)
    if ext is not None:
        del user_custom_ext[name]

    return ext

def ext_find_extension(message: Message, name: str, default: str, mime: Optional[str] = None, caption: Optional[str] = None, try_custom: bool = True, noisy: bool = True) -> str:
    if caption is None:
        caption = message.caption

    ext = ext_custom_extension(message, name) if try_custom else None
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

# --- handlers ---

@wrap_exceptions
def handle_start(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    name = message_get_username(message)
    logger.info(f"start message received from {name}")

    message.reply_text(
        "Hi! I'm the tmp.yrlf.at bot.\n" +
        "\n" +
        "Send me stuff and I'll host it!"
    )

@wrap_exceptions
def handle_text(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    text = message.text
    if text is None:
        return

    name = message_get_username(message)

    if text.startswith("/extension"):
        logger.info(f"custom extension request received from {name}")
        cmd = "extension"
        default_ext = ""
    elif text.startswith("/text"):
        logger.info(f"text upload received from {name}")
        cmd = "text"
        default_ext = "txt"
    else:
        message.reply_text("(ignoring invalid command)")
        return

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

    if cmd == "extension":
        if ext == default_ext:
            message.reply_text(f"Uhh, I don't understand what extension you mean")
        else:
            user_custom_ext[name] = ext
            message.reply_text(f"Got it! The next file you upload will have the extension '.{ext}'")
    elif cmd == "text":
        if len(parts) < 2:
            message.reply_text("Huh? You didn't send me anything to upload.")
            return

        data = parts[1]
        upload_data(message, data.encode('utf-8'), ext)

@wrap_exceptions
def handle_photo(update: Update, context: CallbackContext):
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
def handle_document(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    document = message.document
    if document is None:
        logger.warning("document was empty")
        return

    name = message_get_username(message)
    logger.info(f"document upload received from {name}")

    ext = ext_find_extension(message, name, "bin", document.mime_type)
    upload_file(message, document.get_file(), ext)

@wrap_exceptions
def handle_audio(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    audio = message.audio
    if audio is None:
        logger.warning("audio was empty")
        return

    name = message_get_username(message)
    logger.info(f"audio upload received from {name}")

    ext = ext_find_extension(message, name, "audio", audio.mime_type)
    upload_file(message, audio.get_file(), ext)

@wrap_exceptions
def handle_voice(update: Update, context: CallbackContext):
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
def handle_video(update: Update, context: CallbackContext):
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

def main():
    if TOKEN is None:
        logger.error("no TMPBOT_TELEGRAM_TOKEN supplied")
        sys.exit(1)

    if "TMPBOT_TELEGRAM_WHITELIST" not in os.environ:
        logger.warning(f"no TELEGRAM_WHITELIST supplied, defaulting to {WHITELIST}")

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

    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    whitelist = Filters.user(username = WHITELIST)
    WMessageHandler = lambda filters, handler: MessageHandler(whitelist & filters, handler)
    WCommandHandler = lambda cmd, handler: CommandHandler(cmd, handler, filters = whitelist)

    dispatcher.add_handler(WCommandHandler("start", handle_start))
    dispatcher.add_handler(WCommandHandler("text", handle_text))
    dispatcher.add_handler(WCommandHandler("extension", handle_text))
    dispatcher.add_handler(WMessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(WMessageHandler(Filters.document, handle_document))
    dispatcher.add_handler(WMessageHandler(Filters.audio, handle_audio))
    dispatcher.add_handler(WMessageHandler(Filters.voice, handle_voice))
    dispatcher.add_handler(WMessageHandler(Filters.video, handle_video))

    try:
        updater.start_polling()
    except KeyboardInterrupt:
        logger.info("shutting down")
    except Exception:
        logger.exception("uncaught exception")
        logger.info("shutting down")

if __name__ == '__main__':
    main()
