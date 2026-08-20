import os
import logging
import asyncio
import aiofiles
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# ========== CONFIG ==========
TOKEN = os.getenv("BOT_TOKEN", "7904092194:AAFsCdvYCGRQyaytKHs59rtBP8sVKNWGhjc")  # Replace or set env
ADMIN_ID = "@mac_37x"  # or numeric user ID if known

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporary download folder
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ========== YT-DLP OPTIONS ==========
def get_ydl_opts(format_type="video"):
    """Return yt-dlp options for video or audio."""
    if format_type == "audio":
        return {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
    else:
        return {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

# ========== HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me a social media link (Instagram, YouTube, etc.) or use:\n"
        "/download <url>"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Just paste any supported URL.\n"
        "I'll fetch the media and give you quality options."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When user sends a URL directly."""
    url = update.message.text.strip()
    await ask_format(update.message.chat_id, context, url)

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /download <url>"""
    if not context.args:
        await update.message.reply_text("Please provide a URL: /download <url>")
        return
    url = context.args[0]
    await ask_format(update.message.chat_id, context, url)

async def ask_format(chat_id, context, url):
    """Send inline keyboard to choose video or audio."""
    keyboard = [
        [InlineKeyboardButton("🎥 Video (MP4)", callback_data=f"vid|{url}")],
        [InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"aud|{url}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Choose download format:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    format_type, url = data.split("|", 1)
    await query.edit_message_text(f"⏳ Downloading {format_type}... Please wait.")

    # Notify admin about the request
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,  # can be username or numeric ID
            text=f"📥 Request: {format_type} from {url} by {query.from_user.username}"
        )
    except Exception:
        pass  # ignore if admin ID not valid

    # Start download
    try:
        file_path, title = await download_media(url, format_type)
        await send_media(query.message.chat_id, context, file_path, title, format_type)
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")
    finally:
        # Clean up downloaded file
        if file_path and file_path.exists():
            file_path.unlink()

async def download_media(url, format_type):
    """Download using yt-dlp and return file path and title."""
    ydl_opts = get_ydl_opts(format_type)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # For audio, yt-dlp adds .mp3 after postprocessing, adjust
        if format_type == "audio":
            base = Path(filename).stem
            filename = str(DOWNLOAD_DIR / f"{base}.mp3")
        title = info.get("title", "media")
    return Path(filename), title

async def send_media(chat_id, context, file_path, title, format_type):
    """Send file to user, either as video or audio/document."""
    if not file_path.exists():
        await context.bot.send_message(chat_id, "File not found after download.")
        return

    # For files > 50MB, Telegram API limits – send as document
    size = file_path.stat().st_size / (1024 * 1024)  # MB
    caption = f"📁 {title}"

    try:
        if format_type == "video":
            if size > 50:
                with open(file_path, "rb") as f:
                    await context.bot.send_document(chat_id, document=f, caption=caption)
            else:
                with open(file_path, "rb") as f:
                    await context.bot.send_video(chat_id, video=f, caption=caption, supports_streaming=True)
        else:  # audio
            if size > 50:
                with open(file_path, "rb") as f:
                    await context.bot.send_document(chat_id, document=f, caption=caption)
            else:
                with open(file_path, "rb") as f:
                    await context.bot.send_audio(chat_id, audio=f, caption=caption, title=title)
    except Exception as e:
        # fallback: send as document
        with open(file_path, "rb") as f:
            await context.bot.send_document(chat_id, document=f, caption=f"{caption} (fallback)")

# ========== MAIN ==========
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(vid|aud)\|"))

    # Notify admin that bot is running (if admin ID is a numeric user ID)
    async def startup():
        try:
            await app.bot.send_message(chat_id=ADMIN_ID, text="🤖 Bot is online!")
        except:
            pass
    loop = asyncio.get_event_loop()
    loop.create_task(startup())

    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()