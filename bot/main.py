"""edgeX Agent — Telegram Bot MVP
Your AI trader. Tell it what you think. It trades for you.
"""
import asyncio
import logging
import os
import traceback
import time
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import config
import db
import edgex_client
import ai_trader
import memory as mem
import news_push

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

pending_plans = {}

PERSONA_BUTTONS = [
    [
        InlineKeyboardButton("\U0001f525 Degen", callback_data="persona_degen"),
        InlineKeyboardButton("\U0001f3af Sensei", callback_data="persona_sensei"),
    ],
    [
        InlineKeyboardButton("\U0001f916 Cold Blood", callback_data="persona_coldblood"),
        InlineKeyboardButton("\U0001f440 Shitposter", callback_data="persona_shitposter"),
    ],
    [
        InlineKeyboardButton("\U0001f4da Professor", callback_data="persona_professor"),
        InlineKeyboardButton("\U0001f43a Wolf", callback_data="persona_wolf"),
    ],
    [
        InlineKeyboardButton("\U0001f338 Moe", callback_data="persona_moe"),
    ],
    [
        InlineKeyboardButton("\U0001f519 Back", callback_data="ai_hub"),
    ],
]

PERSONA_NAMES = {
    "degen": "\U0001f525 Degen",
    "sensei": "\U0001f3af Sensei",
    "coldblood": "\U0001f916 Cold Blood",
    "shitposter": "\U0001f440 Shitposter",
    "professor": "\U0001f4da Professor",
    "wolf": "\U0001f43a Wolf",
    "moe": "\U0001f338 Moe",
}

PERSONA_GREETINGS = {
    "degen": "LFG! Aping into every trade with zero fear. NFA but we're gonna make it, fren.",
    "sensei": "The market rewards patience and discipline. I will guide you with clarity and wisdom.",
    "coldblood": "Emotions eliminated. All decisions based on data and probability. Ready to execute.",
    "shitposter": "lmaooo we're about to ratio the entire market. buckle up, this is gonna be hilarious.",
    "professor": "Excellent choice. I shall provide thorough analysis with proper methodology and citations.",
    "wolf": "The hunt begins. Every dip is prey, every pump is territory. Let's dominate this market.",
    "moe": "Yay~ I'll do my best to help you! Let's have fun trading together, okay? Ganbare!",
}


def _back_button(label: str = "\U0001f519 Back", cb: str = "back_to_dashboard") -> InlineKeyboardMarkup:
    """Single Back button — standard for all sub-screens."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])

_main_menu_kb = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]])


def _quick_actions_keyboard(has_edgex: bool = True) -> InlineKeyboardMarkup:
    """Shortcut buttons for command-based screens (e.g. /status, /pnl)."""
    return _back_button("\U0001f3e0 Main Menu")


def _dashboard_keyboard(has_edgex: bool, has_ai: bool = True) -> InlineKeyboardMarkup:
    """Main dashboard — always 3 buttons."""
    rows = []
    if has_edgex:
        rows.append([InlineKeyboardButton("\U0001f4c8 Trade on edgeX", callback_data="trade_hub")])
    else:
        rows.append([InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")])
    if has_ai:
        rows.append([InlineKeyboardButton("\U0001f916 AI Agent", callback_data="ai_hub")])
    else:
        rows.append([InlineKeyboardButton("\u2728 Activate AI", callback_data="ai_activate_prompt")])
    rows.append([InlineKeyboardButton("\U0001f4f0 Event Trading", callback_data="news_settings")])
    return InlineKeyboardMarkup(rows)


def _dashboard_text(user, user_ai) -> str:
    """Build the dashboard message text (same as /start)."""
    has_edgex = _has_edgex(user)
    if has_edgex:
        acct = user["account_id"]
        edgex_line = f"\U0001f464 edgeX: `{acct}` \u2705"
    else:
        edgex_line = "\U0001f464 edgeX: not connected"
    ai_line = "\u2728 AI: Active \u2705" if user_ai else "\u2728 AI: not activated"
    return (
        f"\U0001f916 *edgeX Agent \u2014 Your Own AI Trading Agent*\n\n"
        f"{edgex_line}\n{ai_line}\n\n"
        f"\U0001f447 Tap a button or just talk to me:\n\n"
        f"_\"BTC's looking juicy, should I ape in?\"_\n"
        f"_\"\u30bd\u30e9\u30ca\u3092\u30ed\u30f3\u30b0\u3057\u305f\u3044\u3001\u5c11\u3057\u3060\u3051\"_\n"
        f"_\"\uc9c0\uae08 SILVER \uc0c1\ud669 \uc5b4\ub54c?\"_\n"
        f"_\"CRCL\u6da8\u7684\u79bb\u8c31\uff0c\u600e\u4e48\u64cd\u4f5c\"_\n"
        f"_\"\u041a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 NVDA \u043d\u0430 100$\"_"
    )


def _friendly_order_error(raw_error: str, plan: dict) -> str:
    """Convert technical edgeX errors into user-friendly messages."""
    asset = plan.get("asset", "?")
    size = plan.get("size", "?")
    err = raw_error.lower()

    if "minordersize" in err or "stepsize" in err or ("size" in err and "step" in err):
        import re
        min_match = re.search(r"minordersize['\"]?\s*[:=]\s*['\"]?(\d+\.?\d*)", err)
        min_size = min_match.group(1) if min_match else "unknown"
        return (
            f"\u274c *Order size too small*\n\n"
            f"Your {asset} order (size: {size}) is below the minimum.\n"
            f"Minimum order size for {asset}: *{min_size}*\n\n"
            f"_Just tell me what you want and I'll adjust the size automatically._"
        )
    if "contractid" in err or "contract" in err:
        return (
            f"\u274c *{asset} is temporarily unavailable*\n\n"
            f"This asset might be paused or delisted on edgeX. "
            f"Try another one \u2014 just tell me what you want to trade."
        )
    if "insufficient" in err or "balance" in err:
        return (
            f"\u274c *Not enough balance*\n\n"
            f"Your account doesn't have enough margin for this trade. "
            f"Try a smaller size or check your balance with /status."
        )
    if "whitelist" in err:
        return (
            f"\u274c *API access issue*\n\n"
            f"Your edgeX account may not have API trading enabled. "
            f"Go to edgex.exchange \u2192 API Management \u2192 enable API access, "
            f"then try again."
        )
    # Generic fallback — still explain, don't show raw error
    return (
        f"\u274c *Order couldn't be placed*\n\n"
        f"edgeX returned an error for your {asset} trade. "
        f"This could be a temporary issue. Try again, or try a different asset.\n\n"
        f"_Technical detail: {raw_error[:150]}_"
    )


async def safe_send(context, chat_id: int, text: str, **kwargs):
    """Send a NEW message with error handling."""
    try:
        if text and text.lstrip().startswith("{") and '"action"' in text:
            text = ai_trader._strip_json_wrapper(text)
        return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")


async def safe_edit(query, text: str, **kwargs):
    """Edit the current message in-place. Falls back to answering if edit fails."""
    try:
        if text and text.lstrip().startswith("{") and '"action"' in text:
            text = ai_trader._strip_json_wrapper(text)
        await query.edit_message_text(text=text, **kwargs)
    except Exception as e:
        logger.warning(f"Edit failed ({e}), ignoring")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler — catch anything that falls through."""
    logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)
    if update and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"\u274c Something went wrong. Please try again.\n\nError: {str(context.error)[:200]}",
            )
        except Exception:
            pass


# ──────────────────────────────────────────
# /start — Welcome + Connect edgeX account
# ──────────────────────────────────────────

WAITING_LOGIN_CHOICE, WAITING_ACCOUNT_ID, WAITING_PRIVATE_KEY = range(3)


def _has_edgex(user) -> bool:
    return bool(user and user.get("account_id") and len(user.get("account_id", "")) > 5)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = db.get_user(update.effective_user.id)
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id) if user else None
        has_edgex = _has_edgex(user)
        await update.message.reply_text(
            _dashboard_text(user, user_ai),
            parse_mode="Markdown",
            reply_markup=_dashboard_keyboard(has_edgex, has_ai=bool(user_ai)),
        )
        return WAITING_LOGIN_CHOICE
    except Exception as e:
        logger.error(f"cmd_start error: {e}", exc_info=True)
        await safe_send(context, update.effective_chat.id, f"\u274c Error: {str(e)[:200]}")
        return ConversationHandler.END


async def handle_login_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the login method selection buttons."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    chat_id = update.effective_chat.id

    # Handle callbacks that can be triggered from any state
    if query.data == "logout_confirm":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Yes, logout", callback_data="logout_yes"),
                InlineKeyboardButton("\u274c Cancel", callback_data="logout_no"),
            ]
        ])
        await safe_send(context, update.effective_chat.id,
            "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\nThis will log out your edgeX account. Are you sure?",
            parse_mode="Markdown", reply_markup=keyboard)
        return ConversationHandler.END

    if query.data == "logout_yes":
        conn = db.get_conn()
        conn.execute("DELETE FROM users WHERE tg_user_id = ?", (update.effective_user.id,))
        conn.execute("DELETE FROM ai_usage WHERE tg_user_id = ?", (update.effective_user.id,))
        conn.commit()
        conn.close()
        await safe_edit(query,
            "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\n\u2705 Successfully logged out.",
            parse_mode="Markdown", reply_markup=_main_menu_kb)
        return ConversationHandler.END

    if query.data == "logout_no":
        user = db.get_user(update.effective_user.id)
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id) if user else None
        has_edgex = _has_edgex(user)
        await safe_edit(query, _dashboard_text(user, user_ai),
            parse_mode="Markdown",
            reply_markup=_dashboard_keyboard(has_edgex, has_ai=bool(user_ai)))
        return ConversationHandler.END

    if query.data == "back_to_start":
        user = db.get_user(update.effective_user.id)
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id) if user else None
        has_edgex = _has_edgex(user)
        await safe_edit(query, _dashboard_text(user, user_ai),
            parse_mode="Markdown",
            reply_markup=_dashboard_keyboard(has_edgex, has_ai=bool(user_ai)))
        return ConversationHandler.END

    if query.data == "back_to_dashboard":
        user = db.get_user(update.effective_user.id)
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id) if user else None
        has_edgex = _has_edgex(user)
        await safe_edit(query, _dashboard_text(user, user_ai),
            parse_mode="Markdown",
            reply_markup=_dashboard_keyboard(has_edgex, has_ai=bool(user_ai)))
        return

    if query.data == "ai_activate_prompt":
        existing = db.get_user(update.effective_user.id)
        if not existing:
            db.save_user(update.effective_user.id, "", "")
        await safe_edit(query,
            "\u2728 *Activate AI \u2014 AI Agent*\n\nChoose how to power your Agent:",
            parse_mode="Markdown", reply_markup=_ai_activate_keyboard())
        return ConversationHandler.END

    if query.data == "show_login":
        rows = [
            [InlineKeyboardButton("\u26a1 One-Click OAuth (soon)", callback_data="login_oauth")],
            [InlineKeyboardButton("\U0001f511 Connect with API Key", callback_data="login_api")],
        ]
        if config.DEMO_ACCOUNT_ID and config.DEMO_STARK_KEY:
            rows.append([InlineKeyboardButton("\U0001f464 Aaron's Account (temp)", callback_data="login_demo")])
        rows.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
        await safe_edit(query,
            "\U0001f517 *Connect edgeX \u2014 Trade on edgeX*\n\nChoose how to connect:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        return WAITING_LOGIN_CHOICE

    if query.data == "login_oauth":
        await safe_edit(query,
            "\u26a1 *One-Click Login \u2014 Trade on edgeX*\n\n"
            "Coming Soon! Waiting for edgeX team OAuth integration.\n\n"
            "*For edgeX Team:*\n"
            "OAuth endpoint ready at:\n"
            "`POST /api/v1/oauth/authorize`\n"
            "\u251c `client_id`: edgex-agent-tg-bot\n"
            "\u251c `redirect_uri`: https://t.me/edgeXAgentBot\n"
            "\u251c `scope`: trade,read\n"
            "\u2514 `response_type`: code\n\n"
            "After user authorizes, redirect to:\n"
            "`GET /api/v1/oauth/callback?code={code}&state={tg_user_id}`\n\n"
            "For now, use *Connect with API Key*.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="show_login")]]))
        return ConversationHandler.END

    if query.data == "login_demo":
        if not config.DEMO_ACCOUNT_ID or not config.DEMO_STARK_KEY:
            await query.answer("\u274c Demo account not available.", show_alert=True)
            return ConversationHandler.END
        await safe_edit(query, "\U0001f504 Connecting to Aaron's edgeX account...")
        result = await edgex_client.validate_credentials(config.DEMO_ACCOUNT_ID, config.DEMO_STARK_KEY)
        if not result["valid"]:
            await safe_edit(query, "\u274c Connection failed.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="show_login")]]))
            return ConversationHandler.END
        db.save_user(update.effective_user.id, config.DEMO_ACCOUNT_ID, config.DEMO_STARK_KEY)
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id)
        if not user_ai:
            ai_trader.save_user_ai_config(update.effective_user.id, "__FREE__", "https://factory.ai", "claude-sonnet-4.5")
        user = db.get_user(update.effective_user.id)
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id)
        await safe_edit(query, _dashboard_text(user, user_ai),
            parse_mode="Markdown",
            reply_markup=_dashboard_keyboard(True, has_ai=True))
        return ConversationHandler.END

    if query.data == "login_api":
        await safe_edit(query,
            "\U0001f511 *Connect with API Key \u2014 Trade on edgeX*\n\n"
            "\U0001f449 *Step 1:* Go to edgex.exchange \u2192 *API Management*\n"
            "Copy your *Account ID* and send it to me.\n\n"
            "\u2139\ufe0f Format: 18-digit number, e.g. `713029548781863066`",
            parse_mode="Markdown")
        return WAITING_ACCOUNT_ID

    # Delegate any other callbacks (dashboard buttons, etc.) to the main handler
    await handle_trade_callback(update, context)
    return ConversationHandler.END


async def receive_account_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        account_id = update.message.text.strip()

        if not account_id.isdigit():
            await update.message.reply_text(
                "\u274c *Invalid Account ID*\n\n"
                "Account ID must be digits only.\n"
                "\u2705 Correct: `713029548781863066`\n"
                "\u274c Wrong: `abc123`, `71302-xxx`\n\n"
                "Please send your Account ID again:",
                parse_mode="Markdown",
            )
            return WAITING_ACCOUNT_ID

        if len(account_id) < 10:
            await update.message.reply_text(
                "\u274c *Account ID too short*\n\n"
                "edgeX Account IDs are typically 18 digits.\n"
                "You sent: `" + account_id + "` (" + str(len(account_id)) + " digits)\n\n"
                "Please check and send again:",
                parse_mode="Markdown",
            )
            return WAITING_ACCOUNT_ID

        context.user_data["pending_account_id"] = account_id
        await update.message.reply_text(
            f"\u2705 Account ID received: `{account_id}`\n\n"
            "\U0001f449 *Step 2:* Click your Account \u2192 open *L2 Key* \u2192 copy the *privateKey*\n\n"
            "\U0001f6a8 *Your key will be deleted from chat immediately after I read it.*\n"
            "\u26a0\ufe0f Stored locally only, never shared with anyone.\n\n"
            "\u2139\ufe0f Format: hex string, e.g. `04074f37e37ba90a5b845d8b...`\n\n"
            "Send me your L2 privateKey:",
            parse_mode="Markdown",
        )
        return WAITING_PRIVATE_KEY
    except Exception as e:
        logger.error(f"receive_account_id error: {e}", exc_info=True)
        await safe_send(context, update.effective_chat.id, f"\u274c Error: {str(e)[:200]}. Send /start to retry.")
        return ConversationHandler.END


async def receive_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        private_key = update.message.text.strip()
        account_id = context.user_data.get("pending_account_id", "")

        if not account_id:
            await safe_send(context, chat_id, "\u274c Session expired. Please send /start to begin again.")
            return ConversationHandler.END

        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete private key message: {e}")

        clean_key = private_key.replace("0x", "").strip()
        if not all(c in "0123456789abcdefABCDEF" for c in clean_key):
            await safe_send(context, chat_id,
                "\u274c *Invalid L2 Private Key*\n\n"
                "Key must be hexadecimal characters (0-9, a-f) only.\n"
                "\u2705 Correct: `04074f37e37ba90a5b845d8b...`\n"
                "\u274c Wrong: contains spaces, special chars, or non-hex\n\n"
                "Please send your L2 privateKey again:",
                parse_mode="Markdown")
            return WAITING_PRIVATE_KEY

        if len(clean_key) < 30:
            await safe_send(context, chat_id,
                "\u274c *Key too short*\n\n"
                f"You sent {len(clean_key)} characters. The full privateKey should be 50+ chars.\n"
                "Please copy the *complete* privateKey from L2 Key dialog.\n\n"
                "Send your L2 privateKey again:",
                parse_mode="Markdown")
            return WAITING_PRIVATE_KEY

        await safe_send(context, chat_id, "\U0001f504 Validating your credentials with edgeX...")

        result = await edgex_client.validate_credentials(account_id, clean_key)

        if not result["valid"]:
            error_msg = result.get("error", "Unknown error")
            is_whitelist = "whitelist" in error_msg.lower()
            extra = ""
            if is_whitelist:
                extra = (
                    "\n\n\U0001f6e0 *How to enable API whitelist:*\n"
                    "1. Go to edgex.exchange \u2192 API Management\n"
                    "2. Find your Account ID\n"
                    "3. Click to enable API access / add to whitelist\n"
                    "4. Then try /start again"
                )
            await safe_send(context, chat_id,
                f"\u274c *Connection Failed \u2014 Trade on edgeX*\n\n"
                f"\u2514 `{error_msg}`{extra}\n\n"
                "Common causes:\n"
                "\u2022 Account ID doesn't match the private key\n"
                "\u2022 API access not enabled (whitelist)\n"
                "\u2022 Key copied incorrectly\n\n"
                "Send /start to try again.",
                parse_mode="Markdown")
            return ConversationHandler.END

        db.save_user(user_id, account_id, clean_key)
        context.user_data.pop("pending_account_id", None)

        # Check if AI is already configured (user might have set it up before connecting edgeX)
        user_ai = ai_trader.get_user_ai_config(user_id)
        if user_ai:
            keyboard = _dashboard_keyboard(True, has_ai=True)
            await safe_send(context, chat_id,
                f"\u2705 *edgeX Connected!*\n\n"
                f"\U0001f464 edgeX: `{account_id}` \u2705\n"
                f"\u2728 AI: Active \u2705\n\n"
                f"\U0001f447 Click a button below, or just type and talk to me:\n\n"
                f"_\"BTC's looking juicy, should I ape in?\"_\n"
                f"_\"\u30bd\u30e9\u30ca\u3092\u30ed\u30f3\u30b0\u3057\u305f\u3044\u3001\u5c11\u3057\u3060\u3051\"_\n"
                f"_\"\uc9c0\uae08 SILVER \uc0c1\ud669 \uc5b4\ub54c?\"_\n"
                f"_\"CRCL\u6da8\u7684\u79bb\u8c31\uff0c\u600e\u4e48\u64cd\u4f5c\"_",
                parse_mode="Markdown",
                reply_markup=keyboard)
        else:
            await safe_send(context, chat_id,
                f"\u2705 *edgeX Connected!*\n\n"
                f"\U0001f464 edgeX: `{account_id}` \u2705\n\n"
                f"Now activate your AI Agent to start trading:",
                parse_mode="Markdown",
                reply_markup=_ai_activate_keyboard())
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"receive_private_key error: {e}", exc_info=True)
        await safe_send(context, chat_id,
            f"\u274c Unexpected error: {str(e)[:200]}\n\nSend /start to try again.")
        return ConversationHandler.END


async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Setup cancelled. Use /start to try again.")
    return ConversationHandler.END


# ──────────────────────────────────────────
# Natural Language → Trade Plan (Core Loop)
# ──────────────────────────────────────────

async def _keep_typing(bot, chat_id: int, stop_event: asyncio.Event):
    """Keep sending 'typing' action every 3 seconds until stop_event is set."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3)
            break
        except asyncio.TimeoutError:
            continue


def _ai_activate_keyboard():
    """AI activation menu with Back."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4b3 Use edgeX Account Balance (soon)", callback_data="ai_edgex_credits")],
        [InlineKeyboardButton("\U0001f511 Use My Own API Key", callback_data="ai_own_key_setup")],
        [InlineKeyboardButton("\u26a1 Use Aaron's API (temp)", callback_data="ai_use_free")],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")],
    ])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process any text message as a potential trading thesis or AI chat."""
    chat_id = update.effective_chat.id
    try:
        # Check if user is in feedback mode
        if context.user_data.get("awaiting_feedback"):
            text = update.message.text.strip()
            if text.startswith("/"):
                context.user_data.pop("awaiting_feedback", None)
                # Fall through to normal handling
            elif len(text) < 3:
                await update.message.reply_text("\u274c Too short. Please describe your feedback in more detail:")
                return
            else:
                context.user_data.pop("awaiting_feedback", None)
                u = update.effective_user
                db.save_feedback(
                    tg_user_id=u.id,
                    tg_username=u.username or "",
                    tg_first_name=u.first_name or "",
                    message=text,
                )
                await update.message.reply_text(
                    "\u2705 *Got it!* Your feedback has been recorded. Thanks!",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                    ]),
                )
                return

        user = db.get_user(update.effective_user.id)
        if not user:
            # Silently create minimal user record so they can proceed
            db.save_user(update.effective_user.id, "", "")
            user = db.get_user(update.effective_user.id)

        # Check if AI is configured — if not, prompt the 3-button activation
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id)
        if not user_ai:
            await update.message.reply_text(
                "\u2728 *Activate AI \u2014 AI Agent*\n\n"
                "Choose how to power your Agent:\n\n"
                "\U0001f4b3 *edgeX Balance* \u2014 from your edgeX account (coming soon)\n\n"
                "\U0001f511 *Own API Key* \u2014 unlimited, OpenAI-compatible / Anthropic / Gemini\n\n"
                "\u26a1 *Aaron's API* \u2014 temporary for beta testing",
                parse_mode="Markdown",
                reply_markup=_ai_activate_keyboard(),
            )
            return

        # Start persistent typing indicator (keeps alive until AI responds)
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id, stop_typing))

        try:
            # AI generates plan with live edgex-cli data — no need for get_prices_for_all
            plan = await ai_trader.generate_trade_plan(
                update.message.text, market_prices=None, tg_user_id=update.effective_user.id
            )
        finally:
            stop_typing.set()
            typing_task.cancel()
            try:
                await typing_task
            except (asyncio.CancelledError, Exception):
                pass

        if plan.get("action") == "NEED_API_KEY":
            await update.message.reply_text(
                "\u2728 *Activate AI \u2014 AI Agent*\n\n"
                "Choose how to power your Agent:",
                parse_mode="Markdown",
                reply_markup=_ai_activate_keyboard(),
            )
            return

        if plan.get("action") == "RATE_LIMITED":
            remaining = plan.get("reply", "Daily limit reached.")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f511 Add my own API Key (unlimited)", callback_data="ai_own_key")],
            ])
            await update.message.reply_text(
                f"\u23f0 {remaining}",
                reply_markup=keyboard,
            )
            return

        if plan.get("action") == "CHAT":
            reply_text = plan.get("reply", "I'm not sure what you mean. Try telling me your market view!")
            # Safety: strip any leaked JSON wrapper from AI response
            if reply_text.lstrip().startswith("{") and '"action"' in reply_text:
                reply_text = ai_trader._strip_json_wrapper(reply_text)
            # Truncate if too long for Telegram (max 4096 chars)
            if len(reply_text) > 4000:
                reply_text = reply_text[:4000] + "..."
            has_edgex = _has_edgex(user)
            reply_lower = reply_text.lower()
            # Context-aware buttons: only show what's relevant
            if has_edgex and ("balance" in reply_lower or "margin" in reply_lower or "insufficient" in reply_lower):
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("\U0001f534 Close a Position", callback_data="quick_close"),
                        InlineKeyboardButton("\U0001f4cb Cancel Orders", callback_data="quick_orders"),
                    ],
                    [InlineKeyboardButton("\U0001f4b0 Deposit USDT", url="https://pro.edgex.exchange/portfolio")],
                ])
            else:
                # Regular chat: just Main Menu — keep it clean
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ])
            await update.message.reply_text(
                reply_text,
                reply_markup=kb,
            )
            return

        # TRADE action — validate and show confirmation
        error = ai_trader.validate_plan(plan)
        if error:
            reasoning = plan.get("reasoning", "")
            if reasoning:
                await update.message.reply_text(reasoning)
            else:
                await update.message.reply_text(f"\u26a0\ufe0f {error}\n\nPlease try rephrasing your request.")
            return

        # validate_plan may convert invalid trades to CHAT — re-check
        if plan.get("action") == "CHAT":
            reply_text = plan.get("reply", "I'm not sure what you mean. Try telling me your market view!")
            if reply_text.lstrip().startswith("{") and '"action"' in reply_text:
                reply_text = ai_trader._strip_json_wrapper(reply_text)
            if len(reply_text) > 4000:
                reply_text = reply_text[:4000] + "..."
            await update.message.reply_text(
                reply_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ]),
            )
            return

        # Check if user has edgeX account for trade execution
        has_edgex = user and user.get("account_id") and len(user.get("account_id", "")) > 5

        if not has_edgex:
            # Show the trade plan but explain they need to connect edgeX to execute
            plan_text = ai_trader.format_trade_plan(plan)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f517 Connect edgeX to Execute", callback_data="show_login")],
            ])
            await update.message.reply_text(
                f"{plan_text}\n\n"
                f"\U0001f512 To execute this trade, connect your edgeX account first.",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return

        pending_plans[update.effective_user.id] = plan

        side_word = "LONG" if plan.get("side") == "BUY" else "SHORT"
        side_emoji = "\u2b06\ufe0f" if plan.get("side") == "BUY" else "\u2b07\ufe0f"
        asset = plan.get("asset", "?")
        leverage = plan.get("leverage", "1")
        value = plan.get("position_value_usd", "?")
        tp = plan.get("take_profit", "")
        sl = plan.get("stop_loss", "")
        btn_label = f"{side_emoji} {side_word} {asset} ${value} {leverage}x"
        if tp:
            btn_label += f" TP:${tp}"
        if sl:
            btn_label += f" SL:${sl}"

        reasoning = plan.get("reasoning", "")
        reply_text = f"\u2728 {reasoning}" if reasoning else f"\u2728 {side_word} {asset} looks good."

        await update.message.reply_text(
            reply_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(btn_label, callback_data="show_trade_plan")],
                [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
            ]),
        )
    except Exception as e:
        logger.error(f"handle_message error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error processing your message: {str(e)[:200]}")


WAITING_AI_CONFIG = 10


def _setai_provider_keyboard():
    """Provider selection for own API key."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("OpenAI-compatible", callback_data="setai_openai")],
        [InlineKeyboardButton("Anthropic (Claude)", callback_data="setai_anthropic")],
        [InlineKeyboardButton("Google Gemini", callback_data="setai_gemini")],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="ai_activate_prompt")],
    ])


async def cmd_setai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show AI source selection: edgeX balance / own key / Aaron's temp."""
    user_config = ai_trader.get_user_ai_config(update.effective_user.id)
    status = ""
    if user_config:
        status = (
            f"\n\u2705 *Current:*\n"
            f"\u251c Provider: `{user_config['base_url']}`\n"
            f"\u2514 Model: `{user_config['model']}`\n"
        )

    await update.message.reply_text(
        f"\u2699\ufe0f *AI Configuration \u2014 AI Agent*\n"
        f"{status}\n"
        f"Choose how to power your Agent:\n\n"
        f"\U0001f4b3 *edgeX Account Balance* \u2014 deduct from your edgeX account (coming soon)\n\n"
        f"\U0001f511 *Own API Key* \u2014 unlimited, OpenAI-compatible / Anthropic / Gemini\n\n"
        f"\u26a1 *Aaron's API* \u2014 temporary for beta testing, may be removed anytime",
        parse_mode="Markdown",
        reply_markup=_ai_activate_keyboard(),
    )
    return WAITING_AI_CONFIG


async def handle_setai_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle provider format selection. Shows instructions for single-step config input."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    provider_prompts = {
        "setai_openai": (
            "\U0001f511 *OpenAI-compatible \u2014 AI Agent*\n\n"
            "Works with: OpenAI, DeepSeek, Groq, NVIDIA, etc.\n\n"
            "Send me *3 lines*:\n"
            "`api_key=your-key`\n"
            "`base_url=https://api.openai.com`\n"
            "`model=gpt-4o`\n\n"
            "\U0001f4cb Examples:\n"
            "\u2022 DeepSeek: `base_url=https://api.deepseek.com` + `model=deepseek-chat`\n"
            "\u2022 Groq: `base_url=https://api.groq.com/openai` + `model=llama-3.3-70b-versatile`\n\n"
            "\U0001f6a8 Key will be auto-deleted from chat.\n"
            "Send /cancel to abort."
        ),
        "setai_anthropic": (
            "\U0001f511 *Anthropic \u2014 AI Agent*\n\n"
            "\U0001f517 Get key at: console.anthropic.com\n\n"
            "Send me *3 lines*:\n"
            "`api_key=sk-ant-api03-xxxxx`\n"
            "`base_url=https://api.anthropic.com`\n"
            "`model=claude-sonnet-4-5-20250929`\n\n"
            "\U0001f6a8 Key will be auto-deleted from chat.\n"
            "Send /cancel to abort."
        ),
        "setai_gemini": (
            "\U0001f511 *Google Gemini \u2014 AI Agent*\n\n"
            "\U0001f517 Get key at: aistudio.google.com/apikey\n\n"
            "Send me *3 lines*:\n"
            "`api_key=AIzaSy-xxxxx`\n"
            "`base_url=https://generativelanguage.googleapis.com`\n"
            "`model=gemini-2.0-flash`\n\n"
            "\U0001f6a8 Key will be auto-deleted from chat.\n"
            "Send /cancel to abort."
        ),
    }

    prompt = provider_prompts.get(query.data)
    if not prompt:
        return ConversationHandler.END

    format_name = {"setai_openai": "openai", "setai_anthropic": "anthropic", "setai_gemini": "gemini"}
    context.user_data["setai_format"] = format_name.get(query.data, "openai")
    await query.edit_message_text(prompt, parse_mode="Markdown")
    return WAITING_AI_CONFIG


async def receive_ai_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive api_key + base_url + model in one message, test, activate."""
    chat_id = update.effective_chat.id
    try:
        text = update.message.text.strip()
        try:
            await update.message.delete()
        except Exception:
            pass

        # Parse key=value lines
        api_key = ""
        base_url = ""
        model = ""
        for line in text.splitlines():
            line = line.strip()
            if line.lower().startswith("api_key="):
                api_key = line.split("=", 1)[1].strip()
            elif line.lower().startswith("base_url="):
                base_url = line.split("=", 1)[1].strip()
            elif line.lower().startswith("model="):
                model = line.split("=", 1)[1].strip()

        # Validation
        errors = []
        if not api_key or len(api_key) < 10:
            errors.append("\u2022 `api_key` missing or too short (need 10+ chars)")
        if not base_url or not base_url.startswith("http"):
            errors.append("\u2022 `base_url` missing or invalid (must start with http)")
        if not model:
            errors.append("\u2022 `model` missing")

        if errors:
            await safe_send(context, chat_id,
                "\u274c *Invalid input \u2014 AI Agent*\n\n"
                + "\n".join(errors) + "\n\n"
                "Please send *3 lines*:\n"
                "`api_key=your-key`\n"
                "`base_url=https://...`\n"
                "`model=model-name`\n\n"
                "Send /cancel to abort.",
                parse_mode="Markdown")
            return WAITING_AI_CONFIG

        # Test connection
        await safe_send(context, chat_id, "\U0001f504 Testing API connection...")

        test_result = await ai_trader.call_ai_api(api_key, base_url, model, [
            {"role": "system", "content": "You are a test bot."},
            {"role": "user", "content": "Reply with just the word OK"},
        ])

        if test_result.get("action") == "NEED_API_KEY":
            await safe_send(context, chat_id,
                f"\u274c *API Test Failed \u2014 AI Agent*\n\n"
                f"\u251c Provider: `{base_url}`\n"
                f"\u251c Model: `{model}`\n"
                f"\u2514 Error: `{test_result.get('reply', 'Unknown error')[:100]}`\n\n"
                "Common causes:\n"
                "\u2022 Invalid or expired API key\n"
                "\u2022 Wrong base\\_url for your key\n"
                "\u2022 Model name doesn't exist\n"
                "\u2022 Insufficient API credits\n\n"
                "Fix and resend, or /cancel.",
                parse_mode="Markdown")
            return WAITING_AI_CONFIG

        # Success — save and activate
        user_id = update.effective_user.id
        ai_trader.save_user_ai_config(user_id, api_key, base_url, model)
        existing = db.get_user(user_id)
        if not existing:
            db.save_user(user_id, "", "")

        context.user_data.pop("setai_format", None)

        await safe_send(context, chat_id,
            f"\u2705 *AI Agent Activated!*\n\n"
            f"\u251c Provider: `{base_url}`\n"
            f"\u2514 Model: `{model}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f3ad Choose Personality", callback_data="change_persona")],
                [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
            ]))
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"receive_ai_config error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}\n\nTry again or /cancel.")
        return WAITING_AI_CONFIG


async def handle_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirm/cancel buttons for trade plans."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        # ── Cancel feedback ──
        if query.data == "cancel_feedback":
            context.user_data.pop("awaiting_feedback", None)
            await query.edit_message_text("\u274c Feedback cancelled.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
            return

        # ── Trade Hub (L2) — also handles quick_status redirect ──
        if query.data in ("trade_hub", "quick_status"):
            await query.answer()
            user = db.get_user(user_id)
            if not user or not _has_edgex(user):
                await safe_edit(query, "\u274c Not connected. Use /start.",
                    reply_markup=_back_button())
                return
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                assets = summary.get("assets", {})
                total_equity_raw = assets.get("totalEquityValue", "0")
                available_raw = assets.get("availableBalance", "0")
                try:
                    total_equity = f"{float(total_equity_raw):.2f}"
                except (ValueError, TypeError):
                    total_equity = total_equity_raw
                try:
                    available = f"{float(available_raw):.2f}"
                except (ValueError, TypeError):
                    available = available_raw
                positions = summary.get("positions", [])
                open_pos = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]

                total_upnl = 0.0
                msg = (
                    f"\U0001f4c8 *Trade on edgeX \u2014 Trade on edgeX*\n\n"
                    f"\u251c Equity: `${total_equity}`\n"
                    f"\u2514 Available: `${available}`\n"
                )
                if open_pos:
                    msg += f"\n*Open Positions ({len(open_pos)}):*\n"
                    for p in open_pos:
                        symbol = edgex_client.resolve_symbol(p.get("contractId", ""))
                        size_raw = p.get("size", "0")
                        try:
                            size_f = float(size_raw)
                            side = "LONG" if size_f > 0 else "SHORT"
                        except (ValueError, TypeError):
                            side = p.get("side", "?")
                        pos_val_raw = p.get("positionValue", "0")
                        try:
                            pos_val = f"${float(pos_val_raw):.2f}"
                        except (ValueError, TypeError):
                            pos_val = f"${pos_val_raw}"
                        leverage = p.get("maxLeverage", "")
                        lev_str = f" ({leverage}x)" if leverage else ""
                        entry_raw = p.get("entryPrice", "0")
                        try:
                            entry_str = f"${float(entry_raw):.2f}" if float(entry_raw) >= 1 else f"${float(entry_raw):.5f}"
                        except (ValueError, TypeError):
                            entry_str = f"${entry_raw}"
                        pnl_raw = p.get("unrealizedPnl", "0")
                        try:
                            upnl = float(pnl_raw)
                            total_upnl += upnl
                            pnl_str = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
                        except (ValueError, TypeError):
                            pnl_str = f"${pnl_raw}"
                        pnl_emoji = "\u2b06\ufe0f" if upnl >= 0 else "\u2b07\ufe0f"
                        msg += f"{pnl_emoji} {symbol} {side} `{pos_val}`{lev_str} @ `{entry_str}` | PnL: `{pnl_str}`\n"
                    total_emoji = "\u2b06\ufe0f" if total_upnl >= 0 else "\u2b07\ufe0f"
                    total_str = f"+${total_upnl:.2f}" if total_upnl >= 0 else f"-${abs(total_upnl):.2f}"
                    msg += f"\nUnrealized P&L: {total_emoji} `{total_str}`"
                else:
                    msg += "\nNo open positions."

                buttons = [
                    [InlineKeyboardButton("\U0001f4e4 Share PnL", callback_data="quick_pnl")],
                    [InlineKeyboardButton("\U0001f4b0 Position", callback_data="quick_close"),
                     InlineKeyboardButton("\U0001f4cb Orders", callback_data="quick_orders")],
                    [InlineKeyboardButton("\U0001f4dc History", callback_data="quick_history"),
                     InlineKeyboardButton("\U0001f6aa Disconnect", callback_data="logout_confirm")],
                    [InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")],
                ]
                await safe_edit(query, msg, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}",
                    reply_markup=_back_button())
            return

        # ── AI Agent Hub (L2) ──
        if query.data == "ai_hub":
            user_ai = ai_trader.get_user_ai_config(user_id) if ai_trader else None
            persona = (user_ai or {}).get("persona", "degen")
            persona_name = PERSONA_NAMES.get(persona, persona)
            ai_model = (user_ai or {}).get("model", "none")
            user_memory = mem.get_user_memory(user_id)
            stats = user_memory.get_stats()
            msg = (
                f"\U0001f916 *AI Agent \u2014 AI Agent*\n\n"
                f"\u251c \U0001f3ad Personality: `{persona_name}`\n"
                f"\u2514 \U0001f4dd Memory: `{stats['conversations']}` msgs, `{stats['summaries']}` summaries"
            )
            buttons = [
                [InlineKeyboardButton("\U0001f3ad Personality", callback_data="change_persona")],
                [InlineKeyboardButton("\U0001f511 Provider", callback_data="ai_activate_prompt"),
                 InlineKeyboardButton("\U0001f4dd Memory", callback_data="settings_memory")],
                [InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")],
            ]
            await safe_edit(query, msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons))
            return

        # ── Share PnL Screen ──
        if query.data == "quick_pnl" or query.data.startswith("quick_pnl_page_"):
            await query.answer()
            user = db.get_user(user_id)
            if not user or not _has_edgex(user):
                await safe_edit(query, "\u274c Not connected. Use /start.",
                    reply_markup=_back_button())
                return
            _tb = _back_button("\U0001f519 Back", "trade_hub")
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                positions = summary.get("positions", [])
                open_pos = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]

                history = await edgex_client.get_order_history(client, limit=20)

                page = 0
                if query.data.startswith("quick_pnl_page_"):
                    try:
                        page = int(query.data.replace("quick_pnl_page_", ""))
                    except ValueError:
                        page = 0
                per_page = 10

                msg = "\U0001f4e4 *Share PnL \u2014 Trade on edgeX*\n\n"
                total_upnl = 0.0
                buttons = []
                open_items = []
                closed_items = []

                # Build open position items
                for p in open_pos:
                    cid = p.get("contractId", "")
                    symbol = edgex_client.resolve_symbol(cid)
                    try:
                        side = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
                    except (ValueError, TypeError):
                        side = p.get("side", "?")
                    leverage = p.get("maxLeverage", "")
                    lev_str = f"({leverage}x)" if leverage else ""
                    pos_val_raw = p.get("positionValue", "0")
                    try:
                        pos_val_f = float(pos_val_raw)
                    except (ValueError, TypeError):
                        pos_val_f = 0
                    pnl_raw = p.get("unrealizedPnl", "0")
                    try:
                        upnl = float(pnl_raw)
                        total_upnl += upnl
                    except (ValueError, TypeError):
                        upnl = 0
                    # Calculate ROI %
                    margin = pos_val_f / float(leverage) if leverage else pos_val_f
                    roi = (upnl / margin * 100) if margin > 0 else 0
                    roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
                    pnl_usd = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
                    arrow = "\u2b06\ufe0f" if upnl >= 0 else "\u2b07\ufe0f"
                    entry_raw = p.get("entryPrice", "0")
                    try:
                        entry_str = f"${float(entry_raw):,.2f}" if float(entry_raw) >= 1 else f"${float(entry_raw):.5f}"
                    except (ValueError, TypeError):
                        entry_str = f"${entry_raw}"
                    open_items.append({
                        "symbol": symbol, "side": side, "lev": lev_str,
                        "roi_str": roi_str, "pnl_usd": pnl_usd, "arrow": arrow,
                        "entry": entry_str, "val": f"${pos_val_f:,.2f}", "cid": cid,
                    })

                # Build closed trade items
                for o in (history or []):
                    sym = edgex_client.resolve_symbol(o.get("contractId", ""))
                    raw_side = o.get("orderSide", o.get("side", "?"))
                    pnl_raw = o.get("realizePnl", o.get("cumRealizePnl", ""))
                    try:
                        pnl_f = float(pnl_raw) if pnl_raw else 0
                    except (ValueError, TypeError):
                        pnl_f = 0
                    pnl_usd = f"+${pnl_f:.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):.2f}"
                    arrow = "\u2b06\ufe0f" if pnl_f >= 0 else "\u2b07\ufe0f"
                    fill_price = o.get("fillPrice", o.get("price", "?"))
                    fill_size = o.get("fillSize", o.get("size", "?"))
                    fill_value_raw = o.get("fillValue", "0")
                    try:
                        fill_value_f = float(fill_value_raw) if fill_value_raw else 0
                    except (ValueError, TypeError):
                        fill_value_f = 0
                    # PnL % = realizePnl / fillValue * 100
                    if fill_value_f > 0:
                        pnl_pct = pnl_f / fill_value_f * 100
                        pnl_pct_str = f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"
                    else:
                        pnl_pct_str = ""
                    o_id = o.get("id", o.get("orderId", ""))
                    try:
                        ts = datetime.fromtimestamp(int(o.get("createdTime", "0")) / 1000).strftime("%m/%d %H:%M")
                    except (ValueError, TypeError, OSError):
                        ts = ""
                    closed_items.append({
                        "symbol": sym, "side": raw_side,
                        "pnl_usd": pnl_usd, "pnl_pct_str": pnl_pct_str, "arrow": arrow,
                        "price": fill_price, "size": fill_size,
                        "order_id": o_id, "ts": ts, "pnl_f": pnl_f,
                    })

                if not open_items and not closed_items:
                    msg += "_No positions or trades yet._\n"
                else:
                    # Total unrealized
                    if open_items:
                        t_arrow = "\u2b06\ufe0f" if total_upnl >= 0 else "\u2b07\ufe0f"
                        t_str = f"+${total_upnl:.2f}" if total_upnl >= 0 else f"-${abs(total_upnl):.2f}"
                        msg += f"*Unrealized P&L:* {t_arrow} `{t_str}`\n\n"

                    # Open positions section
                    if open_items:
                        msg += f"\U0001f4c8 *OPEN ({len(open_items)}):*\n"
                        for item in open_items:
                            msg += f"{item['arrow']} {item['symbol']} {item['side']} {item['lev']} | *{item['roi_str']}* ({item['pnl_usd']}) | Entry: `{item['entry']}`\n"
                            btn_label = f"\U0001f4e4 {item['symbol']} {item['side']} {item['roi_str']} ({item['pnl_usd']})"
                            buttons.append([InlineKeyboardButton(btn_label, callback_data=f"share_pnl_{item['cid']}")])
                        msg += "\n"

                    # Closed section with pagination
                    if closed_items:
                        start = page * per_page
                        page_closed = closed_items[start:start + per_page]
                        msg += f"\U0001f4dc *CLOSED ({len(closed_items)}):*\n"
                        for item in page_closed:
                            pct_part = f" *{item['pnl_pct_str']}*" if item['pnl_pct_str'] else ""
                            ts_str = f" | {item['ts']}" if item['ts'] else ""
                            msg += f"{item['arrow']} {item['symbol']} {item['side']} {item['size']} @ ${item['price']} |{pct_part} ({item['pnl_usd']}){ts_str}\n"
                            if item.get("order_id"):
                                cb = f"share_closed_{item['order_id']}"
                                if len(cb.encode('utf-8')) <= 64:
                                    pct_btn = f" {item['pnl_pct_str']}" if item['pnl_pct_str'] else ""
                                    btn_label = f"\U0001f4e4 {item['symbol']} {item['side']}{pct_btn} ({item['pnl_usd']})"
                                    buttons.append([InlineKeyboardButton(btn_label, callback_data=cb)])

                        # Pagination for closed trades
                        nav_row = []
                        if page > 0:
                            nav_row.append(InlineKeyboardButton("\u25c0 Prev", callback_data=f"quick_pnl_page_{page-1}"))
                        if start + per_page < len(closed_items):
                            nav_row.append(InlineKeyboardButton("Next \u25b6", callback_data=f"quick_pnl_page_{page+1}"))
                        if nav_row:
                            buttons.append(nav_row)

                buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="trade_hub")])
                await safe_edit(query, msg, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}", reply_markup=_tb)
            return

        # ── Share PnL (open position) ──
        if query.data.startswith("share_pnl_"):
            contract_id = query.data.replace("share_pnl_", "")
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                return
            tg_user = query.from_user
            display_name = tg_user.full_name or tg_user.username or "Trader"
            try:
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                positions = summary.get("positions", [])
                target = None
                for p in positions:
                    if isinstance(p, dict) and p.get("contractId") == contract_id:
                        target = p
                        break
                if not target:
                    await query.answer("\u274c Position not found.", show_alert=True)
                    return
                symbol = edgex_client.resolve_symbol(contract_id)
                try:
                    side = "LONG" if float(target.get("size", "0")) > 0 else "SHORT"
                except (ValueError, TypeError):
                    side = target.get("side", "?")
                leverage = target.get("maxLeverage", "")
                lev_str = f" ({leverage}x)" if leverage else ""
                entry_raw = target.get("entryPrice", "0")
                try:
                    entry_f = float(entry_raw)
                    entry_str = f"${entry_f:,.2f}" if entry_f >= 1 else f"${entry_f:.5f}"
                except (ValueError, TypeError):
                    entry_str = f"${entry_raw}"
                pos_val_raw = target.get("positionValue", "0")
                try:
                    pos_val_f = float(pos_val_raw)
                except (ValueError, TypeError):
                    pos_val_f = 0
                try:
                    cur_price = await edgex_client.get_market_price(symbol)
                    cur_f = float(cur_price) if cur_price else 0
                    cur_str = f"${cur_f:,.2f}" if cur_f >= 1 else f"${cur_f:.5f}"
                except Exception:
                    cur_str = "N/A"
                pnl_raw = target.get("unrealizedPnl", "0")
                try:
                    pnl_f = float(pnl_raw)
                    pnl_usd = f"+${pnl_f:,.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):,.2f}"
                    margin = pos_val_f / float(leverage) if leverage else pos_val_f
                    roi = (pnl_f / margin * 100) if margin > 0 else 0
                    roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
                except (ValueError, TypeError, ZeroDivisionError):
                    pnl_f = 0
                    pnl_usd = f"${pnl_raw}"
                    roi_str = "N/A"

                arrow = "\u2b06\ufe0f" if pnl_f >= 0 else "\u2b07\ufe0f"
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

                share_text = (
                    f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                    f"{arrow} *{symbol}/USDT* \u00b7 {side}{lev_str}\n"
                    f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
                    f"\U0001f4b0 PnL%:  *{roi_str}*\n\n"
                    f"\u251c Entry: `{entry_str}`\n"
                    f"\u251c Mark:  `{cur_str}`\n"
                    f"\u2514 {now_str}\n\n"
                    f"\U0001f464 {display_name}\n"
                    f"\u26a1 Traded on *edgeX* via @edgeXAgentBot"
                )
                share_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f4e4 Forward to Chat", switch_inline_query=f"{arrow} {symbol} {side}{lev_str} *{roi_str}* ({pnl_usd}) on edgeX")],
                ])
                await safe_send(context, chat_id, share_text, parse_mode="Markdown", reply_markup=share_kb)
            except Exception as e:
                await query.answer(f"\u274c Error: {str(e)[:60]}", show_alert=True)
            return

        # ── Share PnL (closed trade) ──
        if query.data.startswith("share_closed_"):
            order_id = query.data.replace("share_closed_", "")
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                return
            tg_user = query.from_user
            display_name = tg_user.full_name or tg_user.username or "Trader"
            try:
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                history = await edgex_client.get_order_history(client, limit=20)
                target = None
                for o in (history or []):
                    if o.get("id", o.get("orderId", "")) == order_id:
                        target = o
                        break
                if not target:
                    await query.answer("\u274c Trade not found.", show_alert=True)
                    return
                sym = edgex_client.resolve_symbol(target.get("contractId", ""))
                raw_side = target.get("orderSide", target.get("side", "?"))
                fill_price = target.get("fillPrice", target.get("price", "?"))
                fill_size = target.get("fillSize", target.get("size", "?"))
                fill_value_raw = target.get("fillValue", "0")
                pnl_raw = target.get("realizePnl", target.get("cumRealizePnl", ""))
                try:
                    pnl_f = float(pnl_raw) if pnl_raw else 0
                    pnl_usd = f"+${pnl_f:,.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):,.2f}"
                except (ValueError, TypeError):
                    pnl_f = 0
                    pnl_usd = "N/A"
                try:
                    fill_value_f = float(fill_value_raw) if fill_value_raw else 0
                except (ValueError, TypeError):
                    fill_value_f = 0
                if fill_value_f > 0:
                    pnl_pct = pnl_f / fill_value_f * 100
                    pnl_pct_str = f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"
                else:
                    pnl_pct_str = ""
                try:
                    fp = float(fill_price)
                    price_str = f"${fp:,.2f}" if fp >= 1 else f"${fp:.5f}"
                except (ValueError, TypeError):
                    price_str = f"${fill_price}"
                try:
                    ts = datetime.fromtimestamp(int(target.get("createdTime", "0")) / 1000).strftime("%Y-%m-%d %H:%M UTC")
                except (ValueError, TypeError, OSError):
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

                arrow = "\u2b06\ufe0f" if pnl_f >= 0 else "\u2b07\ufe0f"
                pnl_pct_line = f"\U0001f4b0 PnL%:  *{pnl_pct_str}*\n\n" if pnl_pct_str else ""

                share_text = (
                    f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                    f"{arrow} *{sym}/USDT* \u00b7 {raw_side}\n"
                    f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
                    f"{pnl_pct_line}"
                    f"\u251c Price: `{price_str}`\n"
                    f"\u251c Size:  `{fill_size}`\n"
                    f"\u2514 {ts}\n\n"
                    f"\U0001f464 {display_name}\n"
                    f"\u26a1 Traded on *edgeX* via @edgeXAgentBot"
                )
                pct_fwd = f" {pnl_pct_str}" if pnl_pct_str else ""
                share_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f4e4 Forward to Chat", switch_inline_query=f"{arrow} {sym} {raw_side}{pct_fwd} ({pnl_usd}) on edgeX")],
                ])
                await safe_send(context, chat_id, share_text, parse_mode="Markdown", reply_markup=share_kb)
            except Exception as e:
                await query.answer(f"\u274c Error: {str(e)[:60]}", show_alert=True)
            return

        if query.data == "quick_history":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            _tb = _back_button("\U0001f519 Back", "trade_hub")
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                orders = await edgex_client.get_order_history(client, limit=10)
                if not orders:
                    await safe_edit(query, "\U0001f4dc *Recent Trades \u2014 Trade on edgeX*\n\nNo recent trades.",
                        parse_mode="Markdown", reply_markup=_tb)
                    return
                msg = "\U0001f4dc *Recent Trades \u2014 Trade on edgeX*\n\n"
                for o in orders[:10]:
                    sym = edgex_client.resolve_symbol(o.get("contractId", ""))
                    side = o.get("orderSide", o.get("side", "?"))
                    fill_price = o.get("fillPrice", o.get("price", "?"))
                    fill_size = o.get("fillSize", o.get("size", "?"))
                    o_type = o.get("type", o.get("orderType", ""))
                    leverage = o.get("leverage", "")
                    lev_str = f" ({leverage}x)" if leverage else ""
                    pnl_raw = o.get("realizePnl", o.get("cumRealizePnl", ""))
                    try:
                        fp = float(fill_price)
                        price_str = f"${fp:.5f}" if fp < 1 else f"${fp:.2f}"
                    except (ValueError, TypeError):
                        price_str = f"${fill_price}"
                    pnl_str = ""
                    if pnl_raw:
                        try:
                            pnl_f = float(pnl_raw)
                            pnl_str = f" | PnL: +${pnl_f:.4f}" if pnl_f >= 0 else f" | PnL: -${abs(pnl_f):.4f}"
                        except (ValueError, TypeError):
                            pass
                    try:
                        ts = datetime.fromtimestamp(int(o.get("createdTime", "0")) / 1000).strftime("%m/%d %H:%M")
                        ts_str = f" | {ts}"
                    except (ValueError, TypeError, OSError):
                        ts_str = ""
                    type_str = f" {o_type}" if o_type else ""
                    side_emoji = "\u2b06\ufe0f" if side == "BUY" else "\u2b07\ufe0f"
                    msg += f"{side_emoji} {sym} {side}{type_str}{lev_str} {fill_size} @ {price_str}{pnl_str}{ts_str}\n"
                await safe_edit(query, msg, parse_mode="Markdown", reply_markup=_tb)
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}", reply_markup=_tb)
            return

        if query.data == "quick_close":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            _tb = _back_button("\U0001f519 Back", "trade_hub")
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                positions = summary.get("positions", [])
                open_positions = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]
                if not open_positions:
                    await safe_edit(query, "\U0001f4b0 *Position \u2014 Trade on edgeX*\n\nNo open positions.",
                        parse_mode="Markdown", reply_markup=_tb)
                    return
                buttons = []
                msg = "\U0001f4b0 *Position \u2014 Trade on edgeX*\n\n"
                for p in open_positions:
                    cid = p.get("contractId", "")
                    symbol = edgex_client.resolve_symbol(cid)
                    try:
                        side = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
                    except (ValueError, TypeError):
                        side = p.get("side", "?")
                    pos_val_raw = p.get("positionValue", "0")
                    try:
                        pos_val = f"${float(pos_val_raw):.2f}"
                    except (ValueError, TypeError):
                        pos_val = f"${pos_val_raw}"
                    leverage = p.get("maxLeverage", "")
                    lev_str = f" ({leverage}x)" if leverage else ""
                    entry_raw = p.get("entryPrice", "0")
                    try:
                        entry_f = float(entry_raw)
                        entry_str = f"${entry_f:.2f}" if entry_f >= 1 else f"${entry_f:.5f}"
                    except (ValueError, TypeError):
                        entry_str = f"${entry_raw}"
                    pnl_raw = p.get("unrealizedPnl", "0")
                    try:
                        pnl_f = float(pnl_raw)
                        pnl_str = f"+${pnl_f:.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):.2f}"
                    except (ValueError, TypeError):
                        pnl_str = f"${pnl_raw}"
                    pnl_emoji = "\u2b06\ufe0f" if pnl_f >= 0 else "\u2b07\ufe0f"
                    msg += f"{pnl_emoji} *{symbol} {side}*{lev_str}\n"
                    msg += f"  \u251c Value: `{pos_val}` | Entry: `{entry_str}`\n"
                    msg += f"  \u2514 PnL: `{pnl_str}`\n\n"
                    buttons.append([InlineKeyboardButton(f"\U0001f534 Market Close {symbol} {side}", callback_data=f"close_confirm_{cid}")])
                buttons.append([InlineKeyboardButton("\U0001f534 Market Close All", callback_data="close_confirm_all")])
                buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="trade_hub")])
                await safe_edit(query, msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}", reply_markup=_tb)
            return

        # ── Quick Orders (inline) ──
        if query.data == "quick_orders":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            _tb = _back_button("\U0001f519 Back", "trade_hub")
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                orders = await edgex_client.get_open_orders(client)
                if not orders:
                    await safe_edit(query, "\U0001f4cb *Open Orders \u2014 Trade on edgeX*\n\nNo open orders.",
                        parse_mode="Markdown", reply_markup=_tb)
                    return
                lines = [f"\U0001f4cb *Open Orders \u2014 Trade on edgeX*\n\n{len(orders)} order(s):\n"]
                buttons = []
                for o in orders:
                    sym = o.get("symbol", edgex_client.resolve_symbol(o.get("contractId", "")))
                    o_side = o.get("side", "?")
                    o_price = o.get("price", "?")
                    o_size = o.get("size", "?")
                    o_type = o.get("type", "LIMIT")
                    o_leverage = o.get("leverage", "")
                    o_id = o.get("id", o.get("orderId", ""))
                    lev_str = f" ({o_leverage}x)" if o_leverage else ""
                    # Try to get current price for distance calc
                    try:
                        current = await edgex_client.get_market_price(sym)
                        cur_f = float(current) if current else 0
                        ord_f = float(o_price) if o_price else 0
                        if cur_f > 0 and ord_f > 0:
                            dist_pct = abs(cur_f - ord_f) / cur_f * 100
                            dist_str = f" | Now: ${cur_f:.2f} ({dist_pct:.1f}% away)"
                        else:
                            dist_str = ""
                    except Exception:
                        dist_str = ""
                    lines.append(f"  \u2022 {sym} {o_side} {o_type}{lev_str} | Size: {o_size} | Price: ${o_price}{dist_str}")
                    if o_id:
                        buttons.append([InlineKeyboardButton(
                            f"\u274c Cancel {sym} {o_side} {o_size}@{o_price}",
                            callback_data=f"cancelone_confirm_{o_id}"
                        )])
                buttons.append([InlineKeyboardButton("\u274c Cancel All Orders", callback_data="cancelorders_confirm_all")])
                buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="trade_hub")])
                await safe_edit(query, "\n".join(lines), parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}", reply_markup=_tb)
            return

        # ── Logout flow ──
        if query.data == "logout_confirm":
            await query.answer()
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("\u2705 Yes, logout", callback_data="logout_yes"),
                    InlineKeyboardButton("\u274c Cancel", callback_data="logout_no"),
                ]
            ])
            await safe_send(context, chat_id,
                "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\nThis will log out your edgeX account. Are you sure?",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data == "logout_yes":
            conn = db.get_conn()
            conn.execute("DELETE FROM users WHERE tg_user_id = ?", (user_id,))
            conn.execute("DELETE FROM ai_usage WHERE tg_user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            await safe_edit(query,
                "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\n\u2705 Successfully logged out.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        if query.data == "logout_no":
            await safe_edit(query,
                "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\n\u274c Logout cancelled. Your account is still connected.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        if query.data == "show_login":
            rows = [
                [InlineKeyboardButton("\u26a1 One-Click OAuth (soon)", callback_data="login_oauth")],
                [InlineKeyboardButton("\U0001f511 Connect with API Key", callback_data="login_api")],
            ]
            if config.DEMO_ACCOUNT_ID and config.DEMO_STARK_KEY:
                rows.append([InlineKeyboardButton("\U0001f464 Aaron's Account (temp)", callback_data="login_demo")])
            rows.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
            await safe_edit(query,
                "\U0001f517 *Connect edgeX \u2014 Trade on edgeX*\n\nChoose how to connect:",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
            return

        # ── Login callbacks (also handled here for when ConversationHandler is not active) ──
        if query.data == "login_oauth":
            await safe_edit(query,
                "\u26a1 *One-Click Login \u2014 Trade on edgeX*\n\n"
                "Coming Soon! Waiting for edgeX team OAuth integration.\n\n"
                "*For edgeX Team:*\n"
                "OAuth endpoint ready at:\n"
                "`POST /api/v1/oauth/authorize`\n"
                "\u251c `client_id`: edgex-agent-tg-bot\n"
                "\u251c `redirect_uri`: https://t.me/edgeXAgentBot\n"
                "\u251c `scope`: trade,read\n"
                "\u2514 `response_type`: code\n\n"
                "After user authorizes, redirect to:\n"
                "`GET /api/v1/oauth/callback?code={code}&state={tg_user_id}`\n\n"
                "For now, use *Connect with API Key*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="show_login")]]))
            return

        if query.data == "login_demo":
            if not config.DEMO_ACCOUNT_ID or not config.DEMO_STARK_KEY:
                await query.answer("\u274c Demo account not available.", show_alert=True)
                return
            await safe_edit(query, "\U0001f504 Connecting to Aaron's edgeX account...")
            result = await edgex_client.validate_credentials(config.DEMO_ACCOUNT_ID, config.DEMO_STARK_KEY)
            if not result["valid"]:
                await safe_edit(query, "\u274c Connection failed.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="show_login")]]))
                return
            db.save_user(user_id, config.DEMO_ACCOUNT_ID, config.DEMO_STARK_KEY)
            user_ai = ai_trader.get_user_ai_config(user_id)
            if not user_ai:
                ai_trader.save_user_ai_config(user_id, "__FREE__", "https://factory.ai", "claude-sonnet-4.5")
            user = db.get_user(user_id)
            user_ai = ai_trader.get_user_ai_config(user_id)
            await safe_edit(query, _dashboard_text(user, user_ai),
                parse_mode="Markdown",
                reply_markup=_dashboard_keyboard(True, has_ai=True))
            return

        if query.data == "login_api":
            await safe_edit(query,
                "\U0001f511 *Connect with API Key \u2014 Trade on edgeX*\n\n"
                "Please use the /start command, then choose *Connect with API Key*.\n"
                "The API key setup requires a conversation flow.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="show_login")]]))
            return

        if query.data == "ai_edgex_credits":
            await safe_edit(query,
                "\U0001f4b3 *edgeX Balance \u2014 AI Agent*\n\n"
                "Coming Soon! Waiting for edgeX team billing integration.\n\n"
                "*For edgeX Team:*\n"
                "AI billing endpoint ready at:\n"
                "`POST /api/v1/ai/billing/deduct`\n"
                "\u251c `account_id`: user's edgeX account\n"
                "\u251c `model`: requested AI model\n"
                "\u251c `tokens`: input + output token count\n"
                "\u2514 `session_id`: conversation ID\n\n"
                "Balance query:\n"
                "`GET /api/v1/ai/billing/balance?account_id={id}`\n"
                "\u2514 Returns `{\"balance\": 12.50, \"currency\": \"USDT\"}`\n\n"
                "For now, use *Own API Key*.",
                parse_mode="Markdown",
                reply_markup=_back_button("\U0001f519 Back", "ai_activate_prompt"))
            return

        if query.data == "ai_own_key":
            # Redirect to provider selection (same as ai_own_key_setup)
            await safe_edit(query,
                "\U0001f511 *AI Provider \u2014 AI Agent*\n\nChoose your provider:",
                parse_mode="Markdown", reply_markup=_setai_provider_keyboard())
            return

        if query.data in ("back_to_start", "back_to_dashboard"):
            user = db.get_user(user_id)
            user_ai = ai_trader.get_user_ai_config(user_id) if user else None
            has_edgex = _has_edgex(user)
            await safe_edit(query, _dashboard_text(user, user_ai),
                parse_mode="Markdown",
                reply_markup=_dashboard_keyboard(has_edgex, has_ai=bool(user_ai)))
            return

        # ── News alert callbacks ──
        if query.data == "news_settings":
            msg, keyboard = _news_main_menu(user_id)
            await safe_edit(query, msg, parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data.startswith("news_toggle_"):
            remainder = query.data[len("news_toggle_"):]
            last_underscore = remainder.rfind("_")
            source_id = remainder[:last_underscore]
            enable = remainder[last_underscore + 1:] == "on"
            db.set_user_subscription(user_id, source_id, enable)
            msg, keyboard = _news_main_menu(user_id)
            await safe_edit(query, msg, parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data.startswith("news_freq_"):
            source_id = query.data[len("news_freq_"):]
            current = db.get_user_news_frequency(user_id, source_id)
            options = [1, 2, 3, 5, 10]
            buttons = []
            row = []
            for n in options:
                label = f"{'> ' if n == current else ''}{n}/hr"
                row.append(InlineKeyboardButton(label, callback_data=f"news_setfreq_{source_id}_{n}"))
                if len(row) == 3:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="news_settings")])
            await safe_edit(query,
                f"\u23f1 *Push Frequency \u2014 Event Trading*\n\nHow many alerts per hour?\nCurrent: *{current}/hr*",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            return

        if query.data.startswith("news_setfreq_"):
            remainder = query.data[len("news_setfreq_"):]
            last_underscore = remainder.rfind("_")
            source_id = remainder[:last_underscore]
            max_per_hour = int(remainder[last_underscore + 1:])
            db.set_user_news_frequency(user_id, source_id, max_per_hour)
            msg, keyboard = _news_main_menu(user_id)
            await safe_edit(query, msg, parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data.startswith("news_remove_"):
            source_id = query.data[len("news_remove_"):]
            sources = db.get_news_sources(enabled_only=False)
            src = next((s for s in sources if s["id"] == source_id), None)
            if src and src.get("is_default"):
                db.set_user_subscription(user_id, source_id, False)
            else:
                db.remove_news_source(source_id)
            msg, keyboard = _news_main_menu(user_id)
            await safe_edit(query, msg, parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data == "news_add":
            buttons = [
                [InlineKeyboardButton("\U0001f4b0 Bitcoin News", callback_data="news_addsrc_btc")],
                [InlineKeyboardButton("\U0001f4a0 Ethereum News", callback_data="news_addsrc_eth")],
                [InlineKeyboardButton("\U0001f30d DeFi News", callback_data="news_addsrc_defi")],
                [InlineKeyboardButton("\U0001f519 Back", callback_data="news_settings")],
            ]
            await safe_edit(query,
                "\u2795 *Add News Source \u2014 Event Trading*\n\nChoose a topic:",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            return

        if query.data.startswith("news_addsrc_"):
            topic = query.data[len("news_addsrc_"):]
            topic_map = {
                "btc": ("bitcoin_news", "Bitcoin News", "get_bitcoin_news"),
                "eth": ("ethereum_news", "Ethereum News", "get_ethereum_news"),
                "defi": ("defi_news", "DeFi News", "get_defi_news"),
            }
            if topic in topic_map:
                sid, name, tool = topic_map[topic]
                added = db.add_news_source(
                    source_id=sid, name=name,
                    mcp_url="https://modelcontextprotocol.name/mcp/free-crypto-news",
                    mcp_tool=tool, category="crypto",
                )
                if added:
                    db.set_user_subscription(user_id, sid, True)
            msg, keyboard = _news_main_menu(user_id)
            await safe_edit(query, msg, parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data.startswith("news_mute_"):
            source_id = query.data[len("news_mute_"):]
            db.set_user_subscription(user_id, source_id, False)
            await query.answer("\U0001f515 Source muted", show_alert=False)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        if query.data == "news_dismiss":
            try:
                await query.delete_message()
            except Exception:
                await query.edit_message_text("\u2714\ufe0f Dismissed")
            return

        # ── Inline translation — full news card ──
        if query.data.startswith("tl_"):
            lang_code = query.data[3:]
            LANG_NAMES = {
                "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ru": "Russian",
            }
            SENTIMENT_TL = {
                "zh": {"BULLISH": "\u770b\u6da8", "BEARISH": "\u770b\u8dcc", "HIGH": "\u9ad8", "MEDIUM": "\u4e2d", "LOW": "\u4f4e"},
                "ja": {"BULLISH": "\u5f37\u6c17", "BEARISH": "\u5f31\u6c17", "HIGH": "\u9ad8", "MEDIUM": "\u4e2d", "LOW": "\u4f4e"},
                "ko": {"BULLISH": "\uac15\uc138", "BEARISH": "\uc57d\uc138", "HIGH": "\ub192\uc74c", "MEDIUM": "\uc911\uac04", "LOW": "\ub0ae\uc74c"},
                "ru": {"BULLISH": "\u0411\u044b\u0447\u0438\u0439", "BEARISH": "\u041c\u0435\u0434\u0432\u0435\u0436\u0438\u0439", "HIGH": "\u0412\u044b\u0441.", "MEDIUM": "\u0421\u0440\u0435\u0434.", "LOW": "\u041d\u0438\u0437."},
            }
            target_lang = LANG_NAMES.get(lang_code, lang_code)
            msg_text = query.message.text or ""
            lines = msg_text.split("\n")
            # Parse original card: line 0 = "Source: headline", find timestamp, find sentiment
            first_line = lines[0].strip()
            source_prefix = "BWEnews"
            headline = first_line
            if ": " in first_line:
                source_prefix, headline = first_line.split(": ", 1)
            # Find timestamp line and sentiment line
            ts_line = ""
            sentiment_line = ""
            for line in lines:
                line = line.strip()
                if line and line[0].isdigit() and "UTC" in line:
                    ts_line = line
                if line and ("\u2b06\ufe0f" in line or "\u2b07\ufe0f" in line):
                    sentiment_line = line
            if not headline or len(headline) < 5:
                await safe_send(context, chat_id, "\u274c No headline to translate.")
                return
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                factory_key = os.environ.get("FACTORY_API_KEY", "")
                proc = await asyncio.create_subprocess_exec(
                    "/home/ubuntu/.local/bin/droid", "exec",
                    "-m", "claude-sonnet-4-5-20250929",
                    f"Translate the following news headline to {target_lang}. Return ONLY the translation, nothing else:\n\n{headline}",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    env={"PATH": "/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin",
                         "HOME": "/home/ubuntu", "FACTORY_API_KEY": factory_key},
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                translation = stdout.decode().strip().lstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08')
                try:
                    import json as _json
                    wrapper = _json.loads(translation)
                    translation = wrapper.get("result", translation)
                except (ValueError, TypeError):
                    pass
                translation = str(translation).strip().strip('"').strip("'")
                if not translation:
                    await safe_send(context, chat_id, "\u274c Translation failed.")
                    return
                # Build translated news card
                card = f"*{source_prefix}: {translation}*"
                if ts_line:
                    card += f"\n\n{'─' * 16}\n{ts_line}"
                if sentiment_line:
                    # Translate sentiment labels
                    tl_map = SENTIMENT_TL.get(lang_code, {})
                    tl_sent = sentiment_line
                    for en, loc in tl_map.items():
                        tl_sent = tl_sent.replace(en, loc)
                    card += f"\n\n{tl_sent}"
                # Same buttons as original
                await safe_send(context, chat_id, card, parse_mode="Markdown",
                    reply_markup=query.message.reply_markup)
            except asyncio.TimeoutError:
                logger.warning("Translation timed out")
                await safe_send(context, chat_id, "\u274c Translation timed out. Try again.")
            except Exception as e:
                logger.warning(f"Translation error: {type(e).__name__}: {e}")
                await safe_send(context, chat_id, "\u274c Translation service unavailable.")
            return

        if query.data.startswith("news_trade_"):
            # Format: news_trade_{asset}_{side}_{leverage}_{notional}
            parts = query.data.split("_")
            if len(parts) >= 6:
                asset = parts[2]
                side = parts[3]  # BUY or SELL
                leverage = parts[4]
                notional_str = parts[5]  # dollar amount or legacy "small"/"medium"

                user = db.get_user(user_id)
                if not user or not _has_edgex(user):
                    await query.answer("\u274c Connect your edgeX account first. Use /start", show_alert=True)
                    return

                user_ai = ai_trader.get_user_ai_config(user_id)
                if not user_ai:
                    await query.answer("\u274c Activate AI first. Use /setai", show_alert=True)
                    return

                try:
                    # Handle legacy "small"/"medium" labels from old alerts
                    if notional_str == "small":
                        notional = 50.0
                    elif notional_str == "medium":
                        notional = 150.0
                    else:
                        notional = float(notional_str)
                    action_word = "long" if side == "BUY" else "short"
                    prompt = f"{action_word} {asset} with ${notional:.0f} at {leverage}x leverage, execute immediately"

                    # Don't replace news — send new message below
                    await query.answer()
                    await safe_send(context, chat_id,
                        f"\U0001f504 *{action_word.upper()} {asset} \u2014 Trade on edgeX*\n\nGenerating trade plan (~${notional:.0f}, {leverage}x)...",
                        parse_mode="Markdown")

                    # Keep typing indicator alive while AI generates the plan
                    stop_typing = asyncio.Event()
                    typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id, stop_typing))
                    try:
                        plan = await ai_trader.generate_trade_plan(
                            prompt, market_prices=None, tg_user_id=user_id
                        )
                    finally:
                        stop_typing.set()
                        typing_task.cancel()
                        try:
                            await typing_task
                        except (asyncio.CancelledError, Exception):
                            pass

                    if plan.get("action") == "TRADE":
                        error = ai_trader.validate_plan(plan)
                        if error:
                            await safe_send(context, chat_id, f"\u26a0\ufe0f {error}", reply_markup=_quick_actions_keyboard())
                            return
                        pending_plans[user_id] = plan
                        await safe_send(context, chat_id,
                            ai_trader.format_trade_plan(plan),
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("\u2705 Confirm Execute", callback_data="confirm_trade"),
                                 InlineKeyboardButton("\u274c Cancel", callback_data="cancel_trade")],
                            ]))
                    else:
                        reply = plan.get("reply", "Could not generate trade plan. Try asking directly.")
                        if reply.lstrip().startswith("{") and '"action"' in reply:
                            reply = ai_trader._strip_json_wrapper(reply)
                        # Smart buttons: if AI mentions balance/margin issues, add deposit + close
                        reply_lower = reply.lower()
                        if "balance" in reply_lower or "margin" in reply_lower or "insufficient" in reply_lower:
                            kb = InlineKeyboardMarkup([
                                [
                                    InlineKeyboardButton("\U0001f534 Close a Position", callback_data="quick_close"),
                                    InlineKeyboardButton("\U0001f4b0 Deposit USDT", url="https://pro.edgex.exchange/portfolio"),
                                ],
                                [
                                    InlineKeyboardButton("\U0001f4ca Status", callback_data="quick_status"),
                                    InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard"),
                                ],
                            ])
                        else:
                            kb = _quick_actions_keyboard()
                        await safe_send(context, chat_id, reply, parse_mode="Markdown", reply_markup=kb)
                except Exception as e:
                    logger.error(f"News trade error: {e}", exc_info=True)
                    await safe_send(context, chat_id, f"\u274c Trade failed: {str(e)[:200]}", reply_markup=_quick_actions_keyboard())
            return

        # settings_menu redirects to ai_hub (Settings removed)
        if query.data == "settings_menu":
            query.data = "ai_hub"
            # fall through handled above — re-trigger
            user_ai_cfg = ai_trader.get_user_ai_config(user_id) if ai_trader else None
            persona = (user_ai_cfg or {}).get("persona", "degen")
            persona_name = PERSONA_NAMES.get(persona, persona)
            ai_model = (user_ai_cfg or {}).get("model", "none")
            user_memory = mem.get_user_memory(user_id)
            stats = user_memory.get_stats()
            msg = (
                f"\U0001f916 *AI Agent \u2014 AI Agent*\n\n"
                f"\u251c \U0001f3ad Personality: `{persona_name}`\n"
                f"\u2514 \U0001f4dd Memory: `{stats['conversations']}` msgs, `{stats['summaries']}` summaries"
            )
            buttons = [
                [InlineKeyboardButton("\U0001f3ad Personality", callback_data="change_persona")],
                [InlineKeyboardButton("\U0001f511 Provider", callback_data="ai_activate_prompt"),
                 InlineKeyboardButton("\U0001f4dd Memory", callback_data="settings_memory")],
                [InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")],
            ]
            await safe_edit(query, msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons))
            return

        if query.data == "settings_memory":
            user_memory = mem.get_user_memory(user_id)
            stats = user_memory.get_stats()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f5d1 Clear Memory", callback_data="memory_clear_confirm")],
                [InlineKeyboardButton("\U0001f519 Back", callback_data="ai_hub")],
            ])
            await safe_edit(query,
                f"\U0001f4dd *Memory \u2014 AI Agent*\n\n"
                f"\u251c Messages: `{stats['conversations']}`\n"
                f"\u2514 Summaries: `{stats['summaries']}`",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data in ("change_persona", "settings_persona"):
            await safe_edit(query,
                "\U0001f3ad *Personality \u2014 AI Agent*\n\nChoose your Agent's vibe:",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(PERSONA_BUTTONS))
            return

        if query.data == "ai_activate_prompt":
            existing = db.get_user(user_id)
            if not existing:
                db.save_user(user_id, "", "")
            await safe_edit(query,
                "\u2728 *Activate AI \u2014 AI Agent*\n\nChoose how to power your Agent:",
                parse_mode="Markdown", reply_markup=_ai_activate_keyboard())
            return

        if query.data == "ai_use_free":
            existing = db.get_user(user_id)
            if not existing:
                db.save_user(user_id, "", "")
            ai_trader.save_user_ai_config(user_id, "__FREE__", "https://factory.ai", "claude-sonnet-4.5")
            await safe_edit(query,
                "\u2705 *AI Activated \u2014 AI Agent*\n\n"
                "\u251c Provider: `Aaron's API`\n"
                "\u2514 Model: `claude-sonnet-4.5`",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f3ad Choose Personality", callback_data="change_persona")],
                    [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ]))
            return

        if query.data == "ai_own_key_setup":
            await safe_edit(query,
                "\U0001f511 *AI Provider \u2014 AI Agent*\n\nChoose your provider:",
                parse_mode="Markdown", reply_markup=_setai_provider_keyboard())
            return

        # ── setai_* from ai_own_key_setup (outside ConversationHandler) ──
        if query.data.startswith("setai_"):
            await safe_edit(query,
                "\U0001f511 *AI Provider \u2014 AI Agent*\n\n"
                "Use /setai to configure your AI provider.\n"
                "It will walk you through entering your key, URL, and model.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f519 Back", callback_data="ai_hub")],
                ]))
            return

        if query.data.startswith("persona_"):
            persona = query.data.replace("persona_", "")
            conn = db.get_conn()
            conn.execute("UPDATE users SET personality = ? WHERE tg_user_id = ?", (persona, user_id))
            conn.commit()
            conn.close()
            name = PERSONA_NAMES.get(persona, persona)
            greeting = PERSONA_GREETINGS.get(persona, "Personality set! Ready to trade.")
            await query.answer(f"\u2705 {name}", show_alert=False)
            await safe_edit(query,
                f"\U0001f3ad *Personality Set \u2014 AI Agent*\n\n"
                f"\u2705 Active: *{name}*\n\n"
                f"_{greeting}_",
                parse_mode="Markdown",
                reply_markup=_main_menu_kb)
            return

        if query.data == "memory_clear_confirm":
            await query.answer()
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("\u2705 Yes, clear all", callback_data="memory_clear_yes"),
                    InlineKeyboardButton("\u274c Keep", callback_data="memory_clear_no"),
                ]
            ])
            await safe_send(context, chat_id,
                "\U0001f5d1 *Clear Memory \u2014 AI Agent*\n\nAll conversation history and preferences will be deleted.\nThis cannot be undone.",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data == "memory_clear_yes":
            user_memory = mem.get_user_memory(user_id)
            stats = user_memory.get_stats()
            count = stats.get('conversations', 0)
            summaries = stats.get('summaries', 0)
            user_memory.clear()
            await safe_edit(query,
                f"\U0001f5d1 *Clear Memory \u2014 AI Agent*\n\n"
                f"\u2705 Memory cleared.\n\n"
                f"\u251c Deleted: `{count}` messages\n"
                f"\u2514 Deleted: `{summaries}` summaries\n\n"
                f"Your Agent starts fresh. Chat to build new memory.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        if query.data == "memory_clear_no":
            await safe_edit(query,
                "\U0001f5d1 *Clear Memory \u2014 AI Agent*\n\n"
                "\u274c Cancelled. Your memory is safe.\n\n"
                "All conversations and preferences kept intact.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        if query.data == "cancel_trade":
            pending_plans.pop(user_id, None)
            await query.answer("\u274c Cancelled", show_alert=False)
            await safe_edit(query,
                "\u274c *Trade Cancelled \u2014 Trade on edgeX*\n\nNo order was placed.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        if query.data == "show_trade_plan":
            plan = pending_plans.get(user_id)
            if not plan:
                await query.answer()
                await safe_edit(query,
                    "\u274c *Trade Expired \u2014 Trade on edgeX*\n\nSend a new request.",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
                return
            await query.answer()
            await safe_edit(query,
                ai_trader.format_trade_plan(plan),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u2705 Confirm Execute", callback_data="confirm_trade"),
                     InlineKeyboardButton("\u274c Cancel", callback_data="cancel_trade")],
                ]))
            return

        if query.data == "confirm_trade":
            plan = pending_plans.pop(user_id, None)
            if not plan:
                await query.answer()
                await safe_edit(query,
                    "\u274c *Trade Expired \u2014 Trade on edgeX*\n\nSend a new request.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
                return

            user = db.get_user(user_id)
            if not user:
                await query.answer()
                await safe_edit(query,
                    "\u274c *Not Connected \u2014 Trade on edgeX*\n\nUse /start to connect.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
                return

            await query.answer()
            side_word = "LONG" if plan.get("side") == "BUY" else "SHORT"
            await safe_edit(query,
                f"\U0001f504 *Executing {side_word} {plan.get('asset', '')} \u2014 Trade on edgeX*\n\nPlacing order on edgeX...",
                parse_mode="Markdown", reply_markup=None)
            _exec_msg_id = query.message.message_id

            async def _edit_exec(text, *kw):
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=_exec_msg_id, text=text, *kw)
                except Exception:
                    await safe_send(context, chat_id, text, *kw)

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            contract_id = await edgex_client.resolve_contract_id(plan["asset"])

            if not contract_id:
                await _edit_exec(
                    f"\u274c *Asset Not Found \u2014 Trade on edgeX*\n\n"
                    f"`{plan.get('asset')}` is not available on edgeX.\n"
                    f"Try BTC, ETH, or SOL.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
                return

            # Sanitize size/price: strip non-numeric chars, resolve "market" price
            import re
            raw_size = re.sub(r'[^\d.]', '', str(plan.get("size", "0")))
            raw_price = str(plan.get("entry_price", ""))
            if not raw_price or raw_price.lower() in ("market", "current", ""):
                raw_price = await edgex_client.get_market_price(plan["asset"])
                if not raw_price:
                    await _edit_exec(
                        f"\u274c *Price Unavailable \u2014 Trade on edgeX*\n\nCouldn't fetch price for {plan['asset']}.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
                    return
            raw_price = re.sub(r'[^\d.]', '', raw_price)

            # Pre-trade validation: check min order size + balance
            preflight = await edgex_client.pre_trade_check(client, contract_id, plan["side"], raw_size)
            if not preflight["ok"]:
                error = preflight["error"]
                suggestion = preflight.get("suggestion", "")
                await _edit_exec(
                    f"\u274c *Trade Failed \u2014 Trade on edgeX*\n\n{error}\n{suggestion}",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
                return

            result = await edgex_client.place_order(
                client,
                contract_id=contract_id,
                side=plan["side"],
                size=raw_size,
                price=raw_price,
            )

            if result.get("code") == "SUCCESS":
                order_id = result.get("data", {}).get("orderId", "unknown")
                db.save_trade(
                    tg_user_id=user_id,
                    order_id=order_id,
                    contract_id=contract_id,
                    side=plan["side"],
                    size=raw_size,
                    price=raw_price,
                    thesis=plan.get("reasoning", ""),
                )

                side_emoji = "\u2b06\ufe0f" if plan["side"] == "BUY" else "\u2b07\ufe0f"
                side_word = "LONG" if plan["side"] == "BUY" else "SHORT"
                leverage = plan.get("leverage", "1")
                tp = plan.get("take_profit", "")
                sl = plan.get("stop_loss", "")
                value = plan.get("position_value_usd", "")

                msg = (
                    f"{side_emoji} *{side_word} {plan['asset']} \u2014 Trade on edgeX*\n\n"
                    f"\u2705 Order Placed!\n\n"
                    f"\u251c Entry: `${plan['entry_price']}`\n"
                    f"\u251c Size: `{plan['size']}` ({leverage}x)\n"
                )
                if value:
                    msg += f"\u251c Value: `~${value}`\n"
                if tp:
                    msg += f"\u251c TP: `${tp}`\n"
                if sl:
                    msg += f"\u251c SL: `${sl}`\n"
                msg += f"\u2514 Order ID: `{order_id}`"

                await _edit_exec(msg, parse_mode="Markdown", reply_markup=_main_menu_kb)
            else:
                error_msg = result.get("msg") or result.get("error", "Unknown error")
                friendly = _friendly_order_error(error_msg, plan)
                await _edit_exec(friendly, parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        # ── Close confirmation (second step) ──
        if query.data.startswith("close_confirm_"):
            target = query.data.replace("close_confirm_", "")
            await query.answer()
            user = db.get_user(user_id)
            if target == "all":
                # Fetch positions for detail
                detail = ""
                if user:
                    try:
                        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                        summary = await edgex_client.get_account_summary(client)
                        positions = summary.get("positions", [])
                        open_pos = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]
                        if open_pos:
                            detail = f"\n\n{len(open_pos)} position(s):\n"
                            for p in open_pos:
                                sym = edgex_client.resolve_symbol(p.get("contractId", ""))
                                try:
                                    sd = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
                                except (ValueError, TypeError):
                                    sd = "?"
                                pv = p.get("positionValue", "0")
                                try:
                                    pv_str = f"${float(pv):.2f}"
                                except (ValueError, TypeError):
                                    pv_str = f"${pv}"
                                detail += f"\u2022 {sym} {sd} {pv_str}\n"
                    except Exception:
                        pass
                await safe_send(context, chat_id,
                    f"\U0001f534 *Market Close All \u2014 Trade on edgeX*\n\n"
                    f"\u26a0\ufe0f This will market-close ALL open positions.{detail}\n"
                    f"Are you sure?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\u2705 Yes, close all", callback_data="close_all_yes")],
                        [InlineKeyboardButton("\u274c Cancel", callback_data="close_cancel")],
                    ]))
            else:
                symbol = edgex_client.resolve_symbol(target)
                # Fetch position details
                detail = ""
                sd = ""
                if user:
                    try:
                        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                        summary = await edgex_client.get_account_summary(client)
                        for p in summary.get("positions", []):
                            if isinstance(p, dict) and p.get("contractId") == target:
                                try:
                                    sd = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
                                except (ValueError, TypeError):
                                    sd = "?"
                                pv = p.get("positionValue", "0")
                                try:
                                    pv_str = f"${float(pv):.2f}"
                                except (ValueError, TypeError):
                                    pv_str = f"${pv}"
                                upnl = p.get("unrealizedPnl", "0")
                                try:
                                    upnl_f = float(upnl)
                                    upnl_str = f"+${upnl_f:.2f}" if upnl_f >= 0 else f"-${abs(upnl_f):.2f}"
                                except (ValueError, TypeError):
                                    upnl_str = f"${upnl}"
                                entry = p.get("entryPrice", "0")
                                detail = f"\n\n\u251c {sd} | Value: `{pv_str}` | Entry: `${entry}`\n\u2514 PnL: `{upnl_str}`"
                                break
                    except Exception:
                        pass
                await safe_send(context, chat_id,
                    f"\U0001f534 *Market Close {symbol}{' ' + sd if sd else ''} \u2014 Trade on edgeX*\n\n"
                    f"\u26a0\ufe0f This will market-close your {symbol} position.{detail}\n\n"
                    f"Are you sure?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"\u2705 Yes, close {symbol}", callback_data=f"close_{target}")],
                        [InlineKeyboardButton("\u274c Cancel", callback_data="close_cancel")],
                    ]))
            return

        # ── Close cancelled (modal dismiss) ──
        if query.data == "close_cancel":
            await safe_edit(query,
                "\U0001f4b0 *Position \u2014 Trade on edgeX*\n\n\u274c Close cancelled. No positions were closed.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        # ── Close all positions ──
        if query.data == "close_all_yes":
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Not connected.", show_alert=True)
                return
            await query.answer()
            await safe_edit(query, "\U0001f504 Closing all positions...")
            try:
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                positions = summary.get("positions", [])
                open_pos = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]
                results = []
                for p in open_pos:
                    cid = p.get("contractId", "")
                    sym = edgex_client.resolve_symbol(cid)
                    try:
                        sd = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
                    except (ValueError, TypeError):
                        sd = "?"
                    r = await edgex_client.close_position(client, cid, p)
                    results.append((sym, sd, r))
                msg = "\U0001f534 *Close All \u2014 Trade on edgeX*\n\n"
                for sym, sd, r in results:
                    if r.get("code") == "SUCCESS":
                        msg += f"\u2705 {sym} {sd} closed\n"
                    else:
                        msg += f"\u274c {sym} {sd}: {r.get('error', r.get('msg', 'failed'))[:60]}\n"
                await safe_edit(query, msg, parse_mode="Markdown", reply_markup=_main_menu_kb)
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}", reply_markup=_main_menu_kb)
            return

        if query.data.startswith("close_"):
            contract_id = query.data.replace("close_", "")
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Account not connected.", show_alert=True)
                return

            await query.answer()
            await safe_edit(query, "\U0001f504 Closing position...")

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            summary = await edgex_client.get_account_summary(client)
            positions = summary.get("positions", [])

            target = None
            for p in positions:
                if isinstance(p, dict) and p.get("contractId") == contract_id:
                    target = p
                    break

            if not target:
                await safe_edit(query,
                    "\u274c Position not found. It may have already been closed.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f4b0 Position", callback_data="quick_close"),
                         InlineKeyboardButton("\U0001f4c8 Trade Hub", callback_data="trade_hub")],
                    ]))
                return

            symbol = edgex_client.resolve_symbol(contract_id)
            try:
                side = "LONG" if float(target.get("size", "0")) > 0 else "SHORT"
            except (ValueError, TypeError):
                side = target.get("side", "?")
            entry_price = target.get("entryPrice", "0")
            size = target.get("size", "0")
            pnl_raw = target.get("unrealizedPnl", "0")
            try:
                pnl_f = float(pnl_raw)
                pnl_str = f"+${pnl_f:.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):.2f}"
                pnl_emoji = "\u2b06\ufe0f" if pnl_f >= 0 else "\u2b07\ufe0f"
            except (ValueError, TypeError):
                pnl_str = f"${pnl_raw}"
                pnl_emoji = "\u2753"

            result = await edgex_client.close_position(client, contract_id, target)

            if result.get("code") == "MARGIN_BLOCKED_BY_ORDERS":
                orders = result.get("open_orders", [])
                order_count = len(orders)
                order_lines = []
                for o in orders[:5]:
                    o_side = o.get("side", "?")
                    o_price = o.get("price", "?")
                    o_size = o.get("size", "?")
                    o_type = o.get("type", "LIMIT")
                    order_lines.append(f"  \u2022 {o_side} {o_type} | Size: {o_size} | Price: ${o_price}")
                order_detail = "\n".join(order_lines) if order_lines else ""

                msg = (
                    f"\u26a0\ufe0f *Close {symbol} \u2014 Trade on edgeX*\n\n"
                    f"Margin insufficient \u2014 {order_count} open order(s) blocking:\n"
                    f"{order_detail}\n\n"
                    f"Cancel orders to free margin, then retry."
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"\u274c Cancel All {symbol} Orders", callback_data=f"cancelorders_{contract_id}")],
                    [InlineKeyboardButton(f"\U0001f504 Retry Close {symbol}", callback_data=f"close_{contract_id}")],
                    [InlineKeyboardButton("\U0001f4cb View Orders", callback_data=f"vieworders_{contract_id}"),
                     InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ])
                await safe_edit(query, msg, parse_mode="Markdown", reply_markup=kb)
                return

            if result.get("code") == "SUCCESS":
                import asyncio as _aio
                await _aio.sleep(1.5)
                try:
                    new_summary = await edgex_client.get_account_summary(client)
                    new_assets = new_summary.get("assets", {})
                    new_equity = float(new_assets.get("totalEquityValue", "0"))
                    new_avail = float(new_assets.get("availableBalance", "0"))
                    balance_line = f"\u251c Balance: `${new_equity:.2f}` (Available: `${new_avail:.2f}`)"
                except Exception:
                    balance_line = ""

                pos_val_raw = target.get("positionValue", "0")
                try:
                    pos_val = f"${float(pos_val_raw):.2f}"
                except (ValueError, TypeError):
                    pos_val = f"${pos_val_raw}"

                msg = (
                    f"{pnl_emoji} *Close {symbol} {side} \u2014 Trade on edgeX*\n\n"
                    f"\u2705 {side} position closed\n\n"
                    f"\u251c Entry: `${entry_price}`\n"
                    f"\u251c Size: `{size}` | Value: `{pos_val}`\n"
                    f"\u251c Realized P&L: `{pnl_str}`\n"
                )
                if balance_line:
                    msg += f"{balance_line}\n"
                order_id = result.get("data", {}).get("orderId", result.get("orderId", ""))
                if order_id:
                    msg += f"\u2514 Order ID: `{order_id}`"

                await safe_edit(query, msg, parse_mode="Markdown", reply_markup=_main_menu_kb)
            else:
                error_msg = result.get("msg", result.get("error", "Unknown"))
                await safe_edit(query,
                    f"\u274c *Close Failed \u2014 Trade on edgeX*\n\n{error_msg}",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        # ── Cancel orders for a contract ──
        if query.data.startswith("cancelorders_"):
            target_id = query.data.replace("cancelorders_", "")
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Not connected.", show_alert=True)
                return
            await query.answer()

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            if target_id == "all":
                await safe_send(context, chat_id, "\U0001f504 Cancelling all orders...")
                result = await edgex_client.cancel_all_orders(client)
                label = "all"
            else:
                symbol = edgex_client.resolve_symbol(target_id)
                await safe_send(context, chat_id, f"\U0001f504 Cancelling all {symbol} orders...")
                result = await edgex_client.cancel_all_orders(client, target_id)
                label = symbol

            if result.get("code") == "SUCCESS":
                await safe_send(context, chat_id,
                    f"\u2705 *Orders Cancelled \u2014 Trade on edgeX*\n\n\u2705 {label} orders cancelled.",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
            else:
                await safe_send(context, chat_id,
                    f"\u274c *Cancel Failed \u2014 Trade on edgeX*\n\n{result.get('error', 'Unknown')}",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        # ── View open orders for a contract ──
        if query.data.startswith("vieworders_"):
            contract_id = query.data.replace("vieworders_", "")
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Not connected.", show_alert=True)
                return
            await query.answer()
            symbol = edgex_client.resolve_symbol(contract_id)

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            orders = await edgex_client.get_open_orders(client, contract_id)

            if not orders:
                await safe_send(context, chat_id,
                    f"\u2705 No open orders for {symbol}.",
                    reply_markup=_quick_actions_keyboard())
                return

            lines = [f"\U0001f4cb *Open Orders for {symbol}* ({len(orders)}):\n"]
            buttons = []
            for o in orders:
                o_side = o.get("side", "?")
                o_price = o.get("price", "?")
                o_size = o.get("size", "?")
                o_type = o.get("type", "LIMIT")
                o_id = o.get("id", o.get("orderId", ""))
                lines.append(f"  • {o_side} {o_type} | Size: {o_size} | Price: ${o_price}")
                if o_id:
                    buttons.append([InlineKeyboardButton(
                        f"\u274c Cancel {o_side} {o_size}@{o_price}",
                        callback_data=f"cancelone_{o_id}"
                    )])

            buttons.append([InlineKeyboardButton(
                f"\u274c Cancel All {symbol} Orders",
                callback_data=f"cancelorders_{contract_id}"
            )])
            buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="trade_hub"),
                           InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")])

            await safe_edit(query,
                "\n".join(lines), parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons))
            return

        # ── Cancel order confirmation (modal — new message) ──
        if query.data.startswith("cancelone_confirm_"):
            order_id = query.data.replace("cancelone_confirm_", "")
            await query.answer()
            # Fetch order details
            detail = ""
            user = db.get_user(user_id)
            if user:
                try:
                    client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                    orders = await edgex_client.get_open_orders(client)
                    for o in (orders or []):
                        if o.get("id", o.get("orderId", "")) == order_id:
                            o_side = o.get("side", "?")
                            o_price = o.get("price", "?")
                            o_size = o.get("size", "?")
                            o_type = o.get("type", "LIMIT")
                            sym = edgex_client.resolve_symbol(o.get("contractId", ""))
                            detail = f"\n\n\u251c {sym} {o_side} {o_type}\n\u251c Size: `{o_size}` | Price: `${o_price}`\n\u2514 Order ID: `{order_id}`"
                            break
                except Exception:
                    pass
            await safe_send(context, chat_id,
                f"\u274c *Cancel Order \u2014 Trade on edgeX*\n\n"
                f"\u26a0\ufe0f Cancel this order?{detail}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u2705 Yes, cancel", callback_data=f"cancelone_{order_id}")],
                    [InlineKeyboardButton("\u274c Keep order", callback_data="cancel_dismiss")],
                ]))
            return

        if query.data == "cancelorders_confirm_all":
            await query.answer()
            # Fetch order count
            detail = ""
            user = db.get_user(user_id)
            if user:
                try:
                    client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                    orders = await edgex_client.get_open_orders(client)
                    if orders:
                        detail = f"\n\n{len(orders)} order(s):\n"
                        for o in orders[:5]:
                            sym = edgex_client.resolve_symbol(o.get("contractId", ""))
                            o_side = o.get("side", "?")
                            o_price = o.get("price", "?")
                            o_size = o.get("size", "?")
                            detail += f"\u2022 {sym} {o_side} {o_size} @ ${o_price}\n"
                        if len(orders) > 5:
                            detail += f"... and {len(orders) - 5} more\n"
                except Exception:
                    pass
            await safe_send(context, chat_id,
                f"\u274c *Cancel All Orders \u2014 Trade on edgeX*\n\n"
                f"\u26a0\ufe0f Cancel ALL open orders?{detail}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u2705 Yes, cancel all", callback_data="cancelorders_all")],
                    [InlineKeyboardButton("\u274c Keep orders", callback_data="cancel_dismiss")],
                ]))
            return

        # ── Cancel dismissed (modal dismiss) ──
        if query.data == "cancel_dismiss":
            await safe_edit(query,
                "\U0001f4cb *Orders \u2014 Trade on edgeX*\n\n\u274c Cancelled. Orders kept.",
                parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

        # ── Cancel a single order (edits modal) ──
        if query.data.startswith("cancelone_"):
            order_id = query.data.replace("cancelone_", "")
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Not connected.", show_alert=True)
                return
            await query.answer()
            await safe_edit(query, "\U0001f504 Cancelling order...")

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            result = await edgex_client.cancel_order(client, user["account_id"], order_id)

            if result.get("code") == "SUCCESS":
                await safe_edit(query,
                    f"\u2705 *Order Cancelled \u2014 Trade on edgeX*\n\nOrder `{order_id}` cancelled successfully.",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
            else:
                await safe_edit(query,
                    f"\u274c *Cancel Failed \u2014 Trade on edgeX*\n\n{result.get('error', 'Unknown')}",
                    parse_mode="Markdown", reply_markup=_main_menu_kb)
            return

    except Exception as e:
        logger.error(f"handle_trade_callback error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}")


# ──────────────────────────────────────────
# /status — Check balance + open positions
# ──────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        user = db.get_user(update.effective_user.id)
        if not user or not user.get("account_id") or len(user.get("account_id", "")) < 5:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f517 Connect edgeX Account", callback_data="show_login")],
            ])
            await update.message.reply_text(
                "\U0001f517 Connect your edgeX account to check balances and positions.\n\nUse /start to connect.",
                reply_markup=keyboard,
            )
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
        summary = await edgex_client.get_account_summary(client)

        if "error" in summary:
            await update.message.reply_text(f"\u274c Error fetching account: {summary['error']}")
            return

        assets = summary.get("assets", {})
        equity_raw = assets.get("totalEquityValue", "0")
        avail_raw = assets.get("availableBalance", "0")
        try:
            equity_str = f"{float(equity_raw):.2f}"
        except (ValueError, TypeError):
            equity_str = equity_raw
        try:
            avail_str = f"{float(avail_raw):.2f}"
        except (ValueError, TypeError):
            avail_str = avail_raw

        msg = (
            "\U0001f4ca *Account Status*\n\n"
            f"\u251c Equity: `${equity_str}`\n"
            f"\u2514 Available: `${avail_str}`\n"
        )

        positions = summary.get("positions", [])

        if positions:
            msg += f"\n\U0001f4c8 *Open Positions ({len(positions)}):*\n"
            for p in positions:
                cid = p.get("contractId", "")
                symbol = edgex_client.resolve_symbol(cid)
                size = p.get("size", "0")
                try:
                    side = "LONG" if float(size) > 0 else "SHORT"
                except (ValueError, TypeError):
                    side = p.get("side", "?")
                entry = p.get("entryPrice", "0")
                unrealized = p.get("unrealizedPnl", "0")
                liq = p.get("liquidatePrice", "0")
                try:
                    upnl = float(unrealized)
                    pnl_emoji = "\u2b06\ufe0f" if upnl >= 0 else "\u2b07\ufe0f"
                    pnl_str = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
                except (ValueError, TypeError):
                    pnl_emoji = "\u26aa"
                    pnl_str = unrealized
                try:
                    entry_str = f"${float(entry):.4f}"
                except (ValueError, TypeError):
                    entry_str = entry
                msg += (
                    f"\n{pnl_emoji} *{symbol}* {side} `{size}`\n"
                    f"  Entry: `{entry_str}` | PnL: `{pnl_str}`\n"
                    f"  Liq: `${liq}`\n"
                )
        else:
            msg += "\nNo open positions."

        await update.message.reply_text(msg, parse_mode="Markdown",
            reply_markup=_quick_actions_keyboard())

    except Exception as e:
        logger.error(f"cmd_status error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}",
            reply_markup=_quick_actions_keyboard())


# ──────────────────────────────────────────
# /close — Close a position
# ──────────────────────────────────────────
# /orders — View and manage open orders
# ──────────────────────────────────────────

async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        user = db.get_user(update.effective_user.id)
        if not user or not user.get("account_id") or len(user.get("account_id", "")) < 5:
            await update.message.reply_text("\U0001f517 Connect your edgeX account first.\nUse /start to connect.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")]]))
            return

        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
        orders = await edgex_client.get_open_orders(client)

        if not orders:
            await safe_send(context, chat_id,
                "\u2705 No open orders.",
                reply_markup=_quick_actions_keyboard())
            return

        lines = [f"\U0001f4cb *Open Orders* ({len(orders)}):\n"]
        buttons = []
        for o in orders:
            symbol = o.get("symbol", edgex_client.resolve_symbol(o.get("contractId", "")))
            o_side = o.get("side", "?")
            o_price = o.get("price", "?")
            o_size = o.get("size", "?")
            o_type = o.get("type", "LIMIT")
            o_id = o.get("id", o.get("orderId", ""))
            lines.append(f"  \u2022 {symbol} {o_side} {o_type} | Size: {o_size} | Price: ${o_price}")
            if o_id:
                buttons.append([InlineKeyboardButton(
                    f"\u274c Cancel {symbol} {o_side} {o_size}@{o_price}",
                    callback_data=f"cancelone_{o_id}"
                )])

        buttons.append([InlineKeyboardButton("\u274c Cancel All Orders", callback_data="cancelorders_all")])
        buttons.append([
            InlineKeyboardButton("\U0001f534 Close", callback_data="quick_close"),
            InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard"),
        ])

        await safe_send(context, chat_id,
            "\n".join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"cmd_orders error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}")


# ──────────────────────────────────────────

async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        user = db.get_user(update.effective_user.id)
        if not user or not user.get("account_id") or len(user.get("account_id", "")) < 5:
            await update.message.reply_text("\U0001f517 Connect your edgeX account first to manage positions.\nUse /start to connect.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")]]))
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
        summary = await edgex_client.get_account_summary(client)

        if "error" in summary:
            await update.message.reply_text(f"\u274c Error: {summary['error']}")
            return

        positions = summary.get("positions", [])
        open_positions = []
        for p in positions:
            if isinstance(p, dict):
                try:
                    if float(p.get("size", "0")) != 0:
                        open_positions.append(p)
                except (ValueError, TypeError):
                    pass

        if not open_positions:
            await update.message.reply_text("No open positions to close.",
                reply_markup=_quick_actions_keyboard())
            return

        buttons = []
        msg = "\U0001f534 *Select position to close:*\n"
        for p in open_positions:
            cid = p.get("contractId", "")
            symbol = edgex_client.resolve_symbol(cid)
            try:
                side = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
            except (ValueError, TypeError):
                side = p.get("side", "?")
            size = p.get("size", "0")
            pnl_raw = p.get("unrealizedPnl", "0")
            try:
                pnl_f = float(pnl_raw)
                pnl_str = f"+${pnl_f:.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):.2f}"
            except (ValueError, TypeError):
                pnl_str = f"${pnl_raw}"
            msg += f"\n\u2022 {symbol} {side} | Size: {size} | PnL: {pnl_str}"
            buttons.append([InlineKeyboardButton(f"Close {symbol} {side}", callback_data=f"close_{cid}")])

        buttons.append([InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")])
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logger.error(f"cmd_close error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}",
            reply_markup=_quick_actions_keyboard())


# ──────────────────────────────────────────
# /history — Recent trade history
# ──────────────────────────────────────────

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        user = db.get_user(update.effective_user.id)
        if not user or not user.get("account_id") or len(user.get("account_id", "")) < 5:
            await update.message.reply_text("\U0001f517 Connect your edgeX account first to see trade history.\nUse /start to connect.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")]]))
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
        orders = await edgex_client.get_order_history(client, limit=10)

        if not orders:
            trades = db.get_user_trades(update.effective_user.id, limit=10)
            if not trades:
                await update.message.reply_text("No trade history yet. Tell me your market view to start!",
                    reply_markup=_quick_actions_keyboard())
                return

            msg = "\U0001f4dc *Recent Trades (Local)*\n"
            for t in trades:
                symbol = edgex_client.resolve_symbol(t["contract_id"])
                ts = datetime.fromtimestamp(t["created_at"]).strftime("%m/%d %H:%M")
                side_emoji = "\u2b06\ufe0f" if t["side"] == "BUY" else "\u2b07\ufe0f"
                msg += f"\n{side_emoji} {symbol} {t['side']} | {t['size']} @ ${t['price']} | {t['status']} | {ts}"

            await update.message.reply_text(msg, parse_mode="Markdown",
                reply_markup=_quick_actions_keyboard())
            return

        msg = "\U0001f4dc *Recent Trades (edgeX)*\n"
        for o in orders[:10]:
            cid = o.get("contractId", "")
            symbol = edgex_client.resolve_symbol(cid)
            side = o.get("orderSide", o.get("side", "?"))
            size = o.get("fillSize", o.get("size", "0"))
            price = o.get("fillPrice", o.get("price", "0"))
            pnl_raw = o.get("realizePnl", o.get("cumRealizePnl", "0"))
            try:
                pnl_f = float(pnl_raw)
                pnl_str = f"+${pnl_f:.4f}" if pnl_f >= 0 else f"-${abs(pnl_f):.4f}"
            except (ValueError, TypeError):
                pnl_str = f"${pnl_raw}"
            try:
                price_f = f"${float(price):.5f}" if float(price) < 1 else f"${float(price):.2f}"
            except (ValueError, TypeError):
                price_f = f"${price}"
            try:
                ts = datetime.fromtimestamp(int(o.get("createdTime", "0")) / 1000).strftime("%m/%d %H:%M")
            except (ValueError, TypeError, OSError):
                ts = "?"
            side_emoji = "\u2b06\ufe0f" if side == "BUY" else "\u2b07\ufe0f"
            msg += f"\n{side_emoji} {symbol} {side} | {size} @ {price_f} | PnL: {pnl_str} | {ts}"

        await update.message.reply_text(msg, parse_mode="Markdown",
            reply_markup=_quick_actions_keyboard())

    except Exception as e:
        logger.error(f"cmd_history error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}",
            reply_markup=_quick_actions_keyboard())


# ──────────────────────────────────────────
# /pnl — Daily P&L Report Card
# ──────────────────────────────────────────

async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        user = db.get_user(update.effective_user.id)
        if not user or not user.get("account_id") or len(user.get("account_id", "")) < 5:
            await update.message.reply_text("\U0001f517 Connect your edgeX account first to see P&L.\nUse /start to connect.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")]]))
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
        summary = await edgex_client.get_account_summary(client)
        orders = await edgex_client.get_order_history(client, limit=50)

        equity_raw = summary.get("assets", {}).get("totalEquityValue", "0")
        try:
            equity = f"{float(equity_raw):.2f}"
        except (ValueError, TypeError):
            equity = equity_raw

        # Realized PnL from today's fills
        now_ms = int(time.time() * 1000)
        day_ago = now_ms - 86400000
        today_fills = []
        for o in orders:
            try:
                ct = int(o.get("createdTime", "0"))
                if ct > day_ago:
                    today_fills.append(o)
            except (ValueError, TypeError):
                pass

        realized_pnl = sum(float(o.get("realizePnl", o.get("cumRealizePnl", "0"))) for o in today_fills)
        total_trades = len(today_fills)
        winning = len([o for o in today_fills if float(o.get("realizePnl", o.get("cumRealizePnl", "0"))) > 0])
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

        # Unrealized PnL from open positions
        positions = summary.get("positions", [])
        unrealized_pnl = 0
        for p in positions:
            try:
                unrealized_pnl += float(p.get("unrealizedPnl", "0"))
            except (ValueError, TypeError):
                pass

        total_pnl = realized_pnl + unrealized_pnl
        pnl_emoji = "\u2b06\ufe0f" if total_pnl >= 0 else "\u2b07\ufe0f"
        pnl_sign = "+" if total_pnl >= 0 else ""

        card = (
            f"{'=' * 28}\n"
            f"\U0001f4ca  *edgeX Agent Daily Report*\n"
            f"{'=' * 28}\n\n"
            f"Total P&L:  {pnl_emoji} `{pnl_sign}${total_pnl:.2f}`\n"
            f"\u251c Realized: `${realized_pnl:.2f}`\n"
            f"\u2514 Unrealized: `${unrealized_pnl:.2f}`\n\n"
            f"Total Equity: `${equity}`\n\n"
            f"\u251c Trades today: `{total_trades}`\n"
            f"\u2514 Win Rate: `{win_rate:.0f}%`\n\n"
        )

        if positions:
            card += f"*Open Positions ({len(positions)}):*\n"
            for p in positions:
                sym = edgex_client.resolve_symbol(p.get("contractId", ""))
                size = p.get("size", "0")
                try:
                    side = "LONG" if float(size) > 0 else "SHORT"
                except (ValueError, TypeError):
                    side = p.get("side", "?")
                entry = p.get("entryPrice", "0")
                upnl = p.get("unrealizedPnl", "0")
                liq = p.get("liquidatePrice", "0")
                try:
                    upnl_f = float(upnl)
                    pos_emoji = "\u2b06\ufe0f" if upnl_f >= 0 else "\u2b07\ufe0f"
                    upnl_s = f"+${upnl_f:.2f}" if upnl_f >= 0 else f"-${abs(upnl_f):.2f}"
                except (ValueError, TypeError):
                    pos_emoji = "\u26aa"
                    upnl_s = upnl
                try:
                    entry_f = f"${float(entry):.4f}"
                except (ValueError, TypeError):
                    entry_f = entry
                card += (
                    f"\n{pos_emoji} *{sym}* {side} `{size}`\n"
                    f"  Entry: `{entry_f}` | PnL: `{upnl_s}`\n"
                    f"  Liq: `${liq}`\n"
                )
        else:
            card += "No open positions.\n"

        card += (
            f"\n{'=' * 28}\n"
            f"\u26a1 Powered by edgeX Agent\n"
            f"t.me/edgeXAgentBot"
        )

        await update.message.reply_text(card, parse_mode="Markdown",
            reply_markup=_quick_actions_keyboard())

    except Exception as e:
        logger.error(f"cmd_pnl error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error generating report: {str(e)[:200]}",
            reply_markup=_quick_actions_keyboard())


# ──────────────────────────────────────────
# /logout — Disconnect edgeX account (with confirmation)
# ──────────────────────────────────────────

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = db.get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text("You're not logged in. Use /start to connect.")
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Yes, logout", callback_data="logout_yes"),
                InlineKeyboardButton("\u274c Cancel", callback_data="logout_no"),
            ]
        ])
        await update.message.reply_text(
            "\U0001f6aa *Logout*\n\nThis will disconnect your edgeX account from the bot. Are you sure?",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"cmd_logout error: {e}", exc_info=True)
        await safe_send(context, update.effective_chat.id, f"\u274c Error: {str(e)[:200]}")


# ──────────────────────────────────────────
# /news — News alerts subscription management
# ──────────────────────────────────────────

def _news_main_menu(user_id: int) -> tuple:
    """Build the news management main menu message + keyboard."""
    subs = db.get_user_subscriptions(user_id)
    freq_labels = {1: "1/hr", 2: "2/hr", 3: "3/hr", 5: "5/hr", 10: "10/hr", 99: "unlimited"}

    msg = "\U0001f4f0 *Event Trading \u2014 Event Trading*\n\nAI-analyzed news with one-tap trade buttons.\n\n"
    if not subs:
        msg += "_No news sources configured yet._\n"
    for s in subs:
        is_on = bool(s.get("subscribed"))
        status = "\u2705" if is_on else "\u274c"
        mph = s.get("user_max_per_hour", 2)
        freq = freq_labels.get(mph, f"{mph}/hr")
        msg += f"{status} *{s['name']}* \u2014 {freq}\n"

    buttons = []
    for s in subs:
        is_on = bool(s.get("subscribed"))
        sid = s["id"]
        row = []
        if is_on:
            row.append(InlineKeyboardButton(f"\u274c {s['name'][:12]}", callback_data=f"news_toggle_{sid}_off"))
        else:
            row.append(InlineKeyboardButton(f"\u2705 {s['name'][:12]}", callback_data=f"news_toggle_{sid}_on"))
        row.append(InlineKeyboardButton("\u23f1 Frequency", callback_data=f"news_freq_{sid}"))
        row.append(InlineKeyboardButton("\U0001f5d1", callback_data=f"news_remove_{sid}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("\u2795 Add News Source", callback_data="news_add")])
    buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
    return msg, InlineKeyboardMarkup(buttons)


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg, keyboard = _news_main_menu(user_id)
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


# ──────────────────────────────────────────
# /help
# ──────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f916 *edgeX Agent* \u2014 talk to me like a degen, I'll trade like a pro\n\n"
        "_\"BTC\u2019s looking juicy, should I ape in?\"_\n"
        "_\"\u30bd\u30e9\u30ca\u3092\u30ed\u30f3\u30b0\u3057\u305f\u3044\u3001\u5c11\u3057\u3060\u3051\"_\n"
        "_\"\uc9c0\uae08 SILVER \uc0c1\ud669 \uc5b4\ub54c?\"_\n"
        "_\"CRCL\u6da8\u7684\u79bb\u8c31\uff0c\u600e\u4e48\u64cd\u4f5c\"_\n"
        "_\"\u041a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 NVDA \u043d\u0430 100$\"_\n\n"
        "*Commands:*\n"
        "/start \u2014 dashboard\n"
        "/status \u2014 check your bags\n"
        "/close \u2014 close a position\n"
        "/orders \u2014 view & cancel open orders\n"
        "/history \u2014 recent trades\n"
        "/pnl \u2014 today's damage report\n"
        "/setai \u2014 switch AI provider\n"
        "/memory \u2014 view your Agent's memory\n"
        "/news \u2014 manage news alerts\n"
        "/feedback \u2014 suggest features or report bugs\n"
        "/logout \u2014 disconnect",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
        ]),
    )


async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_feedback"] = True
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u274c Cancel", callback_data="cancel_feedback")],
    ])
    await update.message.reply_text(
        "\U0001f4ac *Feedback*\n\n"
        "Tell us what you'd like to see, or what's not working well.\n"
        "Type your feedback below:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ──────────────────────────────────────────
# /memory — View and manage conversation memory
# ──────────────────────────────────────────

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_memory = mem.get_user_memory(user_id)
    stats = user_memory.get_stats()

    oldest_str = ""
    if stats["oldest_ts"]:
        oldest_str = f"\n\u251c Since: `{datetime.fromtimestamp(stats['oldest_ts']).strftime('%Y-%m-%d %H:%M')}`"

    prefs = db.get_user_preferences(user_id)
    pref_text = ""
    if prefs:
        lines = []
        if prefs.get("trading_style"):
            lines.append(f"  \u2022 Style: {prefs['trading_style']}")
        if prefs.get("favorite_assets"):
            lines.append(f"  \u2022 Favorites: {', '.join(prefs['favorite_assets'])}")
        if prefs.get("risk_tolerance"):
            lines.append(f"  \u2022 Risk: {prefs['risk_tolerance']}")
        if prefs.get("language"):
            lines.append(f"  \u2022 Language: {prefs['language']}")
        if prefs.get("notes"):
            for note in prefs["notes"][-3:]:
                lines.append(f"  \u2022 {note}")
        if lines:
            pref_text = "\n\n\U0001f4cb *What I Know About You:*\n" + "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f5d1 Clear Memory", callback_data="memory_clear_confirm"),
            InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard"),
        ]
    ])

    await update.message.reply_text(
        f"\U0001f4dd *Memory*\n\n"
        f"\u251c Messages: `{stats['conversations']}`\n"
        f"\u2514 Summaries: `{stats['summaries']}`"
        f"{oldest_str}"
        f"{pref_text}\n\n"
        f"Your Agent remembers past conversations and learns your preferences over time. "
        f"The more you chat, the more personalized your experience becomes.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

async def post_init(application: Application):
    for attempt in range(3):
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "Start"),
            ])
            # Start news push loop (polls all MCP sources including BWEnews)
            news_push.start_news_loop(application.bot)
            await application.bot.set_my_description(
                "Your personal AI trading agent on edgeX.\n\n"
                "Tell it your market view in any language — it analyzes, plans, and executes.\n\n"
                "\"BTC's pumping, should I ape in?\"\n"
                "\"帮我做空0.01个ETH\"\n"
                "\"SOL 지금 사도 될까?\"\n\n"
                "290+ assets: Crypto, US stocks, Gold, Silver\n"
                "One-tap trading. Real-time data. Remembers your style."
            )
            await application.bot.set_my_short_description(
                "Your personal AI trading agent — talk to it, it trades on edgeX for you."
            )
            logger.info("Bot commands and description set successfully")
            return
        except Exception as e:
            logger.warning(f"post_init attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(3)
    logger.error("Failed to set bot info after 3 attempts, continuing anyway")


def main():
    db.init_db()

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .build()
    )

    setup_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            WAITING_LOGIN_CHOICE: [CallbackQueryHandler(handle_login_choice)],
            WAITING_ACCOUNT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_account_id)],
            WAITING_PRIVATE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_private_key)],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CommandHandler("setai", cmd_setai),
            CommandHandler("status", cmd_status),
            CommandHandler("close", cmd_close),
            CommandHandler("history", cmd_history),
            CommandHandler("pnl", cmd_pnl),
            CommandHandler("memory", cmd_memory),
            CommandHandler("logout", cmd_logout),
            CommandHandler("help", cmd_help),
            CommandHandler("cancel", cancel_setup),
        ],
        per_message=False,
    )

    ai_setup_handler = ConversationHandler(
        entry_points=[CommandHandler("setai", cmd_setai)],
        states={
            WAITING_AI_CONFIG: [
                CallbackQueryHandler(handle_setai_provider, pattern="^setai_"),
                CallbackQueryHandler(handle_trade_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ai_config),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)],
        per_message=False,
    )

    app.add_handler(setup_handler)
    app.add_handler(ai_setup_handler)
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("pnl", cmd_pnl))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_trade_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    logger.info("edgeX Agent Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
