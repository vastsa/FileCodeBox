# @Time    : 2025/09/05 02:57
# @Author  : Jules
# @File    : main.py
# @Software: PyCharm

import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from core.settings import settings
from core.logger import logger
from apps.base.services import create_file_code, get_file_data_by_code

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_html(
        rf"Hi {update.effective_user.mention_html()}! "
        "Welcome to the FileCodeBox Bot. I can help you upload and download files.\n\n"
        "To upload, simply send me a file.\n"
        "To download, use the /download <code> command.\n\n"
        "For more details, use /help."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    await update.message.reply_text(
        "How to use the bot:\n\n"
        "📤 *To Upload:*\n"
        "Simply send any file (document, photo, video, etc.) directly to me. "
        "I will process it and give you a unique pickup code.\n\n"
        "📥 *To Download:*\n"
        "Use the command `/download <code>`.\n"
        "Replace `<code>` with the pickup code you received during upload.\n\n"
        "Example: `/download 12345`"
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles file uploads from users."""
    message = update.message
    file_id = None
    file_name = None

    # Determine file type and get file_id and file_name
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id  # Get the highest resolution
        file_name = f"{file_id}.jpg"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or f"{file_id}.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or f"{file_id}.mp3"

    if not file_id or not file_name:
        await update.message.reply_text("I can't handle this type of message. Please send a file.")
        return

    await update.message.reply_text("Your file is being uploaded, please wait...")

    try:
        bot = context.bot
        tg_file = await bot.get_file(file_id)

        file_bytes = await tg_file.download_as_bytearray()

        code = await create_file_code(
            file_bytes=bytes(file_bytes),
            filename=file_name
        )

        await update.message.reply_text(
            f"✅ File uploaded successfully!\n\nYour pickup code is: `{code}`",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Error handling file upload from Telegram: {e}")
        await update.message.reply_text("Sorry, there was an error processing your file.")


async def download_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /download command to retrieve files."""
    if not context.args:
        await update.message.reply_text("Please provide a pickup code.\nUsage: `/download <code>`", parse_mode="MarkdownV2")
        return

    code = context.args[0]
    await update.message.reply_text(f"Searching for file with code: {code}...")

    try:
        file_data, file_name = await get_file_data_by_code(code)

        if not file_data:
            await update.message.reply_text("File not found or it has expired.")
            return

        await update.message.reply_document(document=file_data, filename=file_name)

    except Exception as e:
        logger.error(f"Error handling file download from Telegram: {e}")
        await update.message.reply_text("Sorry, there was an error retrieving your file.")


def setup_bot_handlers(application: Application):
    """Sets up the command and message handlers for the bot."""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("download", download_file))

    # Handles all file types
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
        handle_file
    ))


async def run_bot():
    """Initializes and runs the Telegram bot."""
    if not settings.telegram_bot_enable or not settings.telegram_bot_token:
        logger.info("Telegram bot is disabled or token is not set. Skipping bot startup.")
        return

    logger.info("Starting Telegram bot...")

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    setup_bot_handlers(application)

    try:
        async with application:
            await application.initialize()
            await application.start()
            logger.info("Telegram bot has started successfully.")
            await application.run_polling()
    except Exception as e:
        logger.error(f"Telegram bot encountered a fatal error: {e}")
    finally:
        if application.running:
            await application.stop()
        await application.shutdown()
        logger.info("Telegram bot has been shut down.")
