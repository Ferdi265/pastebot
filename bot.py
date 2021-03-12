import os
import os.path
import sys
import string
import logging
import mimetypes

from typing import *
from random import choice

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

    message.reply_text(PASTE_URL + id)

def upload_data(message: Message, data: bytes, ext: str):
    id = generate_unique_filename(GENERATE_LENGTH, GENERATE_TRIES, ext)

    with open(PASTE_DIR + id, "wb") as f:
        f.write(data)

    message.reply_text(PASTE_URL + id)

# --- handler helpers ---

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
            message.reply_text("ignoring unrecognized caption")
        elif not all(c in extchars for c in capext):
            message.reply_text("extension contains chars that are not alphanumeric, underscore, or dash")
        else:
            ext = capext

    return ext

def ext_parse_mime(message: Message, mime: Optional[str], ext: Optional[str]) -> Optional[str]:
    if ext is None and mime is not None:
        mimeext = mimetypes.guess_extension(mime)

        if mimeext is None:
            message.reply_text("ignoring unrecognized MIME type")
        elif mimeext.startswith("."):
            ext = mimeext[1:]
        else:
            ext = mimeext

        # hack: python on debian confusingly guesses jpe for image/jpeg
        if ext == 'jpe':
            ext = 'jpg'

    return ext

# --- handlers ---

def handle_start(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    message.reply_text(
        "Hi! I'm the tmp.yrlf.at bot.\n" +
        "\n" +
        "Send me stuff and I'll host it!"
    )

def handle_text(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    text = message.text
    if text is None:
        return

    if not text.startswith("/text"):
        return

    parts = text.split('\n', 1)
    if len(parts) != 2:
        return
    cmdline, data = parts

    args = cmdline.split(' ', 1)
    if len(args) != 2:
        caption = None
    else:
        caption = args[1]

    ext = None
    ext = ext_parse_caption(message, caption, ext)
    if ext is None:
        ext = "txt"

    upload_data(message, data.encode('utf-8'), ext)

def handle_photo(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    photo = photo_get_best(message.photo)
    if photo is None:
        logger.warning("photo list was empty")
        return

    ext = None
    ext = ext_parse_caption(message, message.caption, ext)
    if ext is None:
        ext = "jpg"

    upload_file(message, photo.get_file(), ext)

def handle_document(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    document = message.document
    if document is None:
        logger.warning("document was empty")
        return

    ext = None
    ext = ext_parse_caption(message, message.caption, ext)
    ext = ext_parse_mime(message, document.mime_type, ext)
    if ext is None:
        message.reply_text("unknown extension, defaulting to .bin")
        ext = "bin"

    upload_file(message, document.get_file(), ext)

def handle_audio(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    audio = message.audio
    if audio is None:
        logger.warning("audio was empty")
        return

    ext = None
    ext = ext_parse_caption(message, message.caption, ext)
    ext = ext_parse_mime(message, audio.mime_type, ext)
    if ext is None:
        message.reply_text("unknown extension, defaulting to .audio")
        ext = "audio"

    upload_file(message, audio.get_file(), ext)

def handle_voice(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    voice = message.voice
    if voice is None:
        logger.warning("voice was empty")
        return

    ext = None
    ext = ext_parse_caption(message, message.caption, ext)
    ext = ext_parse_mime(message, voice.mime_type, ext)
    if ext is None:
        message.reply_text("unknown extension, defaulting to .voice")
        ext = "voice"

    upload_file(message, voice.get_file(), ext)

def handle_video(update: Update, context: CallbackContext):
    message = update.message
    if message is None:
        return

    video = message.video
    if video is None:
        logger.warning("video was empty")
        return

    ext = None
    ext = ext_parse_caption(message, message.caption, ext)
    ext = ext_parse_mime(message, video.mime_type, ext)
    if ext is None:
        message.reply_text("unknown extension, defaulting to .video")
        ext = "video"

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
    def WMessageHandler(filters, *args, **kwargs):
        return MessageHandler(whitelist & filters, *args, **kwargs)
    def WCommandHandler(cmd, handler, *args, **kwargs):
        if 'filters' in kwargs:
            kwargs['filters'] &= whitelist
        return CommandHandler(cmd, handler, *args, **kwargs)

    dispatcher.add_handler(WCommandHandler("start", handle_start))
    dispatcher.add_handler(WCommandHandler("text", handle_text))
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
