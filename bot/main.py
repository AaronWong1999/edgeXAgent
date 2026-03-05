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
        InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard"),
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


def _back_button(label: str = "\U0001f519 Back", cb: str = "back_to_dashboard") -> InlineKeyboardMarkup:
    """Single Back button — standard for all sub-screens."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


def _quick_actions_keyboard(has_edgex: bool = True) -> InlineKeyboardMarkup:
    """Shortcut buttons for command-based screens (e.g. /status, /pnl)."""
    return _back_button("\U0001f3e0 Main Menu")


def _dashboard_keyboard(has_edgex: bool, has_ai: bool = True) -> InlineKeyboardMarkup:
    """Main dashboard — hub for all actions."""
    rows = []
    if has_edgex:
        rows.append([
            InlineKeyboardButton("\U0001f4ca Status", callback_data="quick_status"),
            InlineKeyboardButton("\U0001f4c8 P&L", callback_data="quick_pnl"),
        ])
        rows.append([
            InlineKeyboardButton("\U0001f534 Close Position", callback_data="quick_close"),
            InlineKeyboardButton("\U0001f4cb Orders", callback_data="quick_orders"),
        ])
        rows.append([
            InlineKeyboardButton("\U0001f4dc History", callback_data="quick_history"),
            InlineKeyboardButton("\U0001f4f0 News", callback_data="news_settings"),
        ])
        rows.append([
            InlineKeyboardButton("\U0001f3ad Personality", callback_data="settings_persona"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="settings_menu"),
        ])
        rows.append([
            InlineKeyboardButton("\U0001f6aa Disconnect", callback_data="logout_confirm"),
        ])
    else:
        rows.append([InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")])
    if not has_ai:
        rows.append([InlineKeyboardButton("\u2728 Activate AI", callback_data="ai_activate_prompt")])
    return InlineKeyboardMarkup(rows)


def _dashboard_text(user, user_ai) -> str:
    """Build the dashboard message text (same as /start)."""
    has_edgex = _has_edgex(user)
    if has_edgex:
        acct = user["account_id"]
        edgex_line = f"\U0001f464 edgeX: `{acct[:4]}...{acct[-4:]}` \u2705"
    else:
        edgex_line = "\U0001f464 edgeX: not connected"
    ai_line = "\u2728 AI: active \u2705" if user_ai else "\u2728 AI: not activated"
    return (
        f"\U0001f916 *edgeX Agent \u2014 Your Own AI Trading Agent*\n\n"
        f"{edgex_line}\n{ai_line}\n\n"
        f"\U0001f447 Click a button below, or just type and talk to me:\n\n"
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
            f"\u274c **Order size too small**\n\n"
            f"Your {asset} order (size: {size}) is below the minimum.\n"
            f"Minimum order size for {asset}: **{min_size}**\n\n"
            f"_Just tell me what you want and I'll adjust the size automatically._"
        )
    if "contractid" in err or "contract" in err:
        return (
            f"\u274c **{asset} is temporarily unavailable**\n\n"
            f"This asset might be paused or delisted on edgeX. "
            f"Try another one \u2014 just tell me what you want to trade."
        )
    if "insufficient" in err or "balance" in err:
        return (
            f"\u274c **Not enough balance**\n\n"
            f"Your account doesn't have enough margin for this trade. "
            f"Try a smaller size or check your balance with /status."
        )
    if "whitelist" in err:
        return (
            f"\u274c **API access issue**\n\n"
            f"Your edgeX account may not have API trading enabled. "
            f"Go to edgex.exchange \u2192 API Management \u2192 enable API access, "
            f"then try again."
        )
    # Generic fallback — still explain, don't show raw error
    return (
        f"\u274c **Order couldn't be placed**\n\n"
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
                InlineKeyboardButton("\u2705 Yes, disconnect", callback_data="logout_yes"),
                InlineKeyboardButton("\u274c Cancel", callback_data="logout_no"),
            ]
        ])
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id,
            "\U0001f6aa **Disconnect**\n\nAre you sure?",
            parse_mode="Markdown", reply_markup=keyboard)
        return WAITING_LOGIN_CHOICE

    if query.data == "logout_yes":
        conn = db.get_conn()
        conn.execute("DELETE FROM users WHERE tg_user_id = ?", (update.effective_user.id,))
        conn.execute("DELETE FROM ai_usage WHERE tg_user_id = ?", (update.effective_user.id,))
        conn.commit()
        conn.close()
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id,
            "\u2705 Disconnected. Use /start to reconnect.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 Reconnect", callback_data="show_login")]]))
        return ConversationHandler.END

    if query.data == "logout_no":
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id, "\u2705 Cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
        return ConversationHandler.END

    if query.data == "back_to_start":
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id, "Use /start or tap below:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")]]))
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
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id,
            "\u2728 **Activate AI Agent**\n\nChoose how to power your Agent:",
            parse_mode="Markdown", reply_markup=_ai_activate_keyboard())
        return ConversationHandler.END

    if query.data == "show_login":
        rows = [
            [InlineKeyboardButton("\u26a1 One-Click Login (coming soon)", callback_data="login_oauth")],
            [InlineKeyboardButton("\U0001f511 Connect with API Key", callback_data="login_api")],
        ]
        if config.DEMO_ACCOUNT_ID and config.DEMO_STARK_KEY:
            rows.append([InlineKeyboardButton("\U0001f464 Use Aaron's edgeX Account (temp)", callback_data="login_demo")])
        rows.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_start")])
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id,
            "\U0001f517 **Connect edgeX Account**\n\nChoose how to connect:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        return WAITING_LOGIN_CHOICE

    if query.data == "login_oauth":
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id,
            "\u26a1 **One-Click Login** \u2014 Coming Soon!\n\n"
            "For now, use **Connect with API Key**.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_start")]]))
        return ConversationHandler.END

    if query.data == "login_demo":
        chat_id = update.effective_chat.id
        if not config.DEMO_ACCOUNT_ID or not config.DEMO_STARK_KEY:
            await safe_send(context, chat_id, "\u274c Demo account not available. Use /start.")
            return ConversationHandler.END
        await safe_send(context, chat_id, "\U0001f504 Connecting to Aaron's edgeX account...")
        result = await edgex_client.validate_credentials(config.DEMO_ACCOUNT_ID, config.DEMO_STARK_KEY)
        if not result["valid"]:
            await safe_send(context, chat_id, "\u274c Connection failed. Use /start.")
            return ConversationHandler.END
        db.save_user(update.effective_user.id, config.DEMO_ACCOUNT_ID, config.DEMO_STARK_KEY)
        masked = config.DEMO_ACCOUNT_ID[:4] + "..." + config.DEMO_ACCOUNT_ID[-4:]
        user_ai = ai_trader.get_user_ai_config(update.effective_user.id)
        if not user_ai:
            ai_trader.save_user_ai_config(update.effective_user.id, "__FREE__", "https://factory.ai", "claude-sonnet-4.5")
        keyboard = _dashboard_keyboard(True, has_ai=True)
        await safe_send(context, chat_id,
            f"\u2705 **edgeX Connected!**\n\n"
            f"\U0001f464 Account: `{masked}`\n"
            f"\u2728 AI: active \u2705\n\n"
            f"Just talk to me, or tap a button:",
            parse_mode="Markdown", reply_markup=keyboard)
        return ConversationHandler.END

    if query.data == "login_api":
        chat_id = update.effective_chat.id
        await safe_send(context, chat_id,
            "\U0001f511 **Connect with API Key**\n\n"
            "Go to edgex.exchange \u2192 **API Management**\n"
            "Copy your **Account ID** and send it to me:",
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
                "\u274c That doesn't look like a valid Account ID.\n"
                "It should be a number like `713029548781863066`.\n\n"
                "Please send your Account ID again:",
                parse_mode="Markdown",
            )
            return WAITING_ACCOUNT_ID

        if len(account_id) < 10:
            await update.message.reply_text(
                "\u274c That ID looks too short. edgeX Account IDs are typically 18 digits.\n\n"
                "Please check and send again:",
            )
            return WAITING_ACCOUNT_ID

        context.user_data["pending_account_id"] = account_id
        await update.message.reply_text(
            f"\u2705 Account ID received: `{account_id}`\n\n"
            "\U0001f449 **Step 3:** Click your Account \u2192 open **L2 Key** \u2192 copy the **privateKey**\n\n"
            "\U0001f6a8 **Your key will be deleted from chat immediately after I read it.**\n"
            "\u26a0\ufe0f Stored locally only, never shared with anyone.\n\n"
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
                "\u274c That doesn't look like a valid L2 privateKey.\n"
                "It should be a hex string like `04074f37e37ba90a5b845d8b...`\n\n"
                "Please send your L2 privateKey again:")
            return WAITING_PRIVATE_KEY

        if len(clean_key) < 30:
            await safe_send(context, chat_id,
                "\u274c That key looks too short. Please copy the full privateKey from L2 Key dialog.\n\n"
                "Send your L2 privateKey again:")
            return WAITING_PRIVATE_KEY

        await safe_send(context, chat_id, "\U0001f504 Validating your credentials with edgeX...")

        result = await edgex_client.validate_credentials(account_id, clean_key)

        if not result["valid"]:
            error_msg = result.get("error", "Unknown error")
            is_whitelist = "whitelist" in error_msg.lower()
            extra = ""
            if is_whitelist:
                extra = (
                    "\n\n\U0001f6e0 **How to enable API whitelist:**\n"
                    "1. Go to edgex.exchange \u2192 API Management\n"
                    "2. Find your Account ID\n"
                    "3. Click to enable API access / add to whitelist\n"
                    "4. Then try /start again"
                )
            await safe_send(context, chat_id,
                f"\u274c Connection failed:\n{error_msg}{extra}\n\n"
                "Send /start to try again.",
                parse_mode="Markdown")
            return ConversationHandler.END

        db.save_user(user_id, account_id, clean_key)
        context.user_data.pop("pending_account_id", None)

        masked = account_id[:4] + "..." + account_id[-4:]

        # Check if AI is already configured (user might have set it up before connecting edgeX)
        user_ai = ai_trader.get_user_ai_config(user_id)
        if user_ai:
            keyboard = _dashboard_keyboard(True, has_ai=True)
            await safe_send(context, chat_id,
                f"\u2705 **edgeX Connected!**\n\n"
                f"\U0001f464 Account: `{masked}`\n"
                f"\u2728 AI: active \u2705\n\n"
                f"\U0001f447 Click a button below, or just type and talk to me:\n\n"
                f"_\"BTC's looking juicy, should I ape in?\"_\n"
                f"_\"\u30bd\u30e9\u30ca\u3092\u30ed\u30f3\u30b0\u3057\u305f\u3044\u3001\u5c11\u3057\u3060\u3051\"_\n"
                f"_\"\uc9c0\uae08 SILVER \uc0c1\ud669 \uc5b4\ub54c?\"_\n"
                f"_\"CRCL\u6da8\u7684\u79bb\u8c31\uff0c\u600e\u4e48\u64cd\u4f5c\"_",
                parse_mode="Markdown",
                reply_markup=keyboard)
        else:
            await safe_send(context, chat_id,
                f"\u2705 **edgeX Connected!**\n\n"
                f"\U0001f464 Account: `{masked}`\n\n"
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
    """3-button AI activation menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4b3 Use edgeX Account Balance", callback_data="ai_edgex_credits")],
        [InlineKeyboardButton("\U0001f511 Use My Own API Key", callback_data="ai_own_key_setup")],
        [InlineKeyboardButton("\u26a1 Use Aaron's API (temp)", callback_data="ai_use_free")],
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
                    "\u2705 **Got it!** Your feedback has been recorded. Thanks!",
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
                "\u2728 **Activate AI Agent**\n\n"
                "Choose how to power your Agent:\n\n"
                "\U0001f4b3 **edgeX Account Balance** \u2014 deduct from your edgeX account (coming soon)\n\n"
                "\U0001f511 **Own API Key** \u2014 unlimited, use OpenAI / DeepSeek / Anthropic / Gemini\n\n"
                "\u26a1 **Aaron's API** \u2014 temporary for beta testing, may be removed anytime",
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
                "\u2728 **Activate AI Agent**\n\n"
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

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Confirm Execute", callback_data="confirm_trade"),
                InlineKeyboardButton("\u274c Cancel", callback_data="cancel_trade"),
            ]
        ])

        await update.message.reply_text(
            ai_trader.format_trade_plan(plan),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"handle_message error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error processing your message: {str(e)[:200]}")


WAITING_AI_KEY = 10
WAITING_AI_BASE_URL = 11
WAITING_AI_MODEL = 12


def _setai_provider_keyboard():
    """Provider selection for own API key."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("OpenAI / DeepSeek", callback_data="setai_openai")],
        [InlineKeyboardButton("Anthropic (Claude)", callback_data="setai_anthropic")],
        [InlineKeyboardButton("Google Gemini", callback_data="setai_gemini")],
    ])


async def cmd_setai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show AI source selection: edgeX balance / own key / Aaron's temp."""
    user_config = ai_trader.get_user_ai_config(update.effective_user.id)
    status = ""
    if user_config:
        status = (
            f"\n\u2705 **Current:**\n"
            f"\u251c Provider: `{user_config['base_url']}`\n"
            f"\u2514 Model: `{user_config['model']}`\n"
        )

    await update.message.reply_text(
        f"\u2699\ufe0f **AI Configuration**\n"
        f"{status}\n"
        f"Choose how to power your Agent:\n\n"
        f"\U0001f4b3 **edgeX Account Balance** \u2014 deduct from your edgeX account (coming soon)\n\n"
        f"\U0001f511 **Own API Key** \u2014 unlimited, use OpenAI / DeepSeek / Anthropic / Gemini\n\n"
        f"\u26a1 **Aaron's API** \u2014 temporary for beta testing, may be removed anytime",
        parse_mode="Markdown",
        reply_markup=_ai_activate_keyboard(),
    )
    return WAITING_AI_KEY


async def handle_setai_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle provider selection buttons in /setai flow."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    provider_map = {
        "setai_openai": {
            "name": "OpenAI / DeepSeek",
            "instructions": (
                "\U0001f511 **OpenAI-compatible API** (Step 1/3)\n\n"
                "Send me your **API Key**:\n\n"
                "Examples:\n"
                "\u2022 DeepSeek: `sk-xxxxxxxxxxxxxxxx`\n"
                "\u2022 OpenAI: `sk-proj-xxxxxxxx`\n"
                "\u2022 Groq: `gsk_xxxxxxxx`\n\n"
                "Send /cancel to abort."
            ),
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "step2_msg": (
                "\u2705 Key received! (Step 2/3)\n\n"
                "Choose your provider, or type a custom URL:"
            ),
            "step2_buttons": InlineKeyboardMarkup([
                [InlineKeyboardButton("DeepSeek (default)", callback_data="url_https://api.deepseek.com")],
                [InlineKeyboardButton("OpenAI", callback_data="url_https://api.openai.com")],
                [InlineKeyboardButton("Groq", callback_data="url_https://api.groq.com/openai")],
                [InlineKeyboardButton("NVIDIA", callback_data="url_https://integrate.api.nvidia.com/v1")],
            ]),
            "step3_msg": (
                "\u2705 URL set! (Step 3/3)\n\n"
                "Choose a model, or type a custom one:"
            ),
            "needs_base_url": True,
        },
        "setai_anthropic": {
            "name": "Anthropic (Claude)",
            "instructions": (
                "\U0001f511 **Anthropic API** (Step 1/2)\n\n"
                "Get your key at: console.anthropic.com\n\n"
                "Send me your **API Key**:\n\n"
                "Example: `sk-ant-api03-xxxxxxxx`\n\n"
                "Send /cancel to abort."
            ),
            "base_url": "https://api.anthropic.com",
            "model": "claude-sonnet-4-5-20250929",
            "step3_msg": (
                "\u2705 Key received! (Step 2/2)\n\n"
                "Choose a model, or type a custom one:"
            ),
            "step3_buttons": InlineKeyboardMarkup([
                [InlineKeyboardButton("Claude Sonnet 4.5 (default)", callback_data="model_claude-sonnet-4-5-20250929")],
                [InlineKeyboardButton("Claude Haiku 3.5", callback_data="model_claude-3-5-haiku-20241022")],
            ]),
            "needs_base_url": False,
        },
        "setai_gemini": {
            "name": "Google Gemini",
            "instructions": (
                "\U0001f511 **Google Gemini API** (Step 1/2)\n\n"
                "Get your key at: aistudio.google.com/apikey\n\n"
                "Send me your **API Key**:\n\n"
                "Example: `AIzaSy-xxxxxxxx`\n\n"
                "Send /cancel to abort."
            ),
            "base_url": "https://generativelanguage.googleapis.com",
            "model": "gemini-2.0-flash",
            "step3_msg": (
                "\u2705 Key received! (Step 2/2)\n\n"
                "Choose a model, or type a custom one:"
            ),
            "step3_buttons": InlineKeyboardMarkup([
                [InlineKeyboardButton("Gemini 2.0 Flash (default)", callback_data="model_gemini-2.0-flash")],
                [InlineKeyboardButton("Gemini 2.5 Pro", callback_data="model_gemini-2.5-pro")],
            ]),
            "needs_base_url": False,
        },
    }

    info = provider_map.get(query.data)
    if not info:
        return ConversationHandler.END

    context.user_data["setai_provider"] = info
    await query.edit_message_text(info["instructions"], parse_mode="Markdown")
    return WAITING_AI_KEY


async def receive_ai_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Receive API key."""
    chat_id = update.effective_chat.id
    try:
        text = update.message.text.strip()
        try:
            await update.message.delete()
        except Exception:
            pass

        if len(text) < 10:
            await safe_send(context, chat_id, "\u274c Key too short. Please send a valid API key.")
            return WAITING_AI_KEY

        provider_info = context.user_data.get("setai_provider", {})
        context.user_data["setai_api_key"] = text

        if provider_info.get("needs_base_url"):
            await safe_send(context, chat_id,
                provider_info.get("step2_msg", "Choose provider URL:"),
                parse_mode="Markdown",
                reply_markup=provider_info.get("step2_buttons"))
            return WAITING_AI_BASE_URL
        else:
            context.user_data["setai_base_url"] = provider_info.get("base_url", "")
            await safe_send(context, chat_id,
                provider_info.get("step3_msg", "Choose model:"),
                parse_mode="Markdown",
                reply_markup=provider_info.get("step3_buttons"))
            return WAITING_AI_MODEL

    except Exception as e:
        logger.error(f"receive_ai_key error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}\n\nTry again or /cancel.")
        return WAITING_AI_KEY


async def handle_url_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle base URL button click in step 2."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    url = query.data.replace("url_", "")
    context.user_data["setai_base_url"] = url
    provider_info = context.user_data.get("setai_provider", {})
    # Build model buttons based on selected URL
    model_buttons = _model_buttons_for_url(url)
    await query.edit_message_text(
        provider_info.get("step3_msg", "Choose model:"),
        parse_mode="Markdown",
        reply_markup=model_buttons,
    )
    return WAITING_AI_MODEL


def _model_buttons_for_url(url: str):
    """Return model selection buttons based on the base URL."""
    if "deepseek" in url:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("deepseek-chat (default)", callback_data="model_deepseek-chat")],
            [InlineKeyboardButton("deepseek-reasoner", callback_data="model_deepseek-reasoner")],
        ])
    elif "openai" in url:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("gpt-4o (default)", callback_data="model_gpt-4o")],
            [InlineKeyboardButton("gpt-4o-mini", callback_data="model_gpt-4o-mini")],
            [InlineKeyboardButton("o3-mini", callback_data="model_o3-mini")],
        ])
    elif "groq" in url:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("llama-3.3-70b (default)", callback_data="model_llama-3.3-70b-versatile")],
            [InlineKeyboardButton("mixtral-8x7b", callback_data="model_mixtral-8x7b-32768")],
        ])
    elif "nvidia" in url:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("qwen3.5-397b (default)", callback_data="model_qwen/qwen3.5-397b-a17b")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Use provider default", callback_data="model_default")],
    ])


async def handle_model_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle model button click in step 3."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    model = query.data.replace("model_", "")
    provider_info = context.user_data.get("setai_provider", {})
    if model == "default":
        model = provider_info.get("model", "deepseek-chat")

    api_key = context.user_data.get("setai_api_key", "")
    base_url = context.user_data.get("setai_base_url", "")
    chat_id = query.message.chat_id
    user_id = update.effective_user.id

    await query.edit_message_text("\U0001f504 Testing your API key...")

    test_ok = await ai_trader.test_ai_connection(api_key, base_url, model)
    if not test_ok:
        await safe_send(context, chat_id,
            f"\u274c Could not connect to {base_url} with model {model}.\n\n"
            f"Check your API key and try again with /setai.")
        return ConversationHandler.END

    ai_trader.save_user_ai_config(user_id, api_key, base_url, model)
    existing = db.get_user(user_id)
    if not existing:
        db.save_user(user_id, "", "")

    await safe_send(context, chat_id,
        f"\u2705 **AI Agent Activated!**\n\n"
        f"\u251c Provider: `{base_url}`\n"
        f"\u2514 Model: `{model}`\n\n"
        f"\U0001f3ad **Choose your Agent's personality:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(PERSONA_BUTTONS))
    return ConversationHandler.END


async def receive_ai_base_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Receive Base URL (text input fallback)."""
    chat_id = update.effective_chat.id
    try:
        text = update.message.text.strip()
        provider_info = context.user_data.get("setai_provider", {})

        if text.lower() == "default":
            text = provider_info.get("base_url", "https://api.deepseek.com")

        if not text.startswith("http"):
            await safe_send(context, chat_id, "\u274c URL must start with `http://` or `https://`. Try again:")
            return WAITING_AI_BASE_URL

        context.user_data["setai_base_url"] = text
        model_buttons = _model_buttons_for_url(text)
        await safe_send(context, chat_id,
            provider_info.get("step3_msg", "Choose model:"),
            parse_mode="Markdown",
            reply_markup=model_buttons)
        return WAITING_AI_MODEL

    except Exception as e:
        logger.error(f"receive_ai_base_url error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}\n\nTry again or /cancel.")
        return WAITING_AI_BASE_URL


async def receive_ai_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: Receive Model name, then test and activate."""
    chat_id = update.effective_chat.id
    try:
        text = update.message.text.strip()
        provider_info = context.user_data.get("setai_provider", {})

        if text.lower() == "default":
            text = provider_info.get("model", "deepseek-chat")

        api_key = context.user_data.get("setai_api_key", "")
        base_url = context.user_data.get("setai_base_url", "")
        model = text

        await safe_send(context, chat_id, "\U0001f504 Testing your API key...")

        test_result = await ai_trader.call_ai_api(api_key, base_url, model, [
            {"role": "system", "content": "You are a test bot."},
            {"role": "user", "content": "Reply with just the word OK"},
        ])

        if test_result.get("action") == "NEED_API_KEY":
            await safe_send(context, chat_id,
                f"\u274c API key test failed: {test_result.get('reply', 'Unknown error')}\n\n"
                "Please check your key/URL/model and try /setai again.")
            context.user_data.pop("setai_api_key", None)
            context.user_data.pop("setai_base_url", None)
            context.user_data.pop("setai_provider", None)
            return ConversationHandler.END

        ai_trader.save_user_ai_config(update.effective_user.id, api_key, base_url, model)
        context.user_data.pop("setai_api_key", None)
        context.user_data.pop("setai_base_url", None)
        context.user_data.pop("setai_provider", None)

        await safe_send(context, chat_id,
            f"\u2705 **AI Agent Activated!**\n\n"
            f"\u251c Provider: `{base_url}`\n"
            f"\u2514 Model: `{model}`\n\n"
            f"\U0001f3ad **Choose your Agent's personality:**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(PERSONA_BUTTONS))
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"receive_ai_model error: {e}", exc_info=True)
        await safe_send(context, chat_id, f"\u274c Error: {str(e)[:200]}\n\nTry /setai again.")
        return ConversationHandler.END


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

        # ── Dashboard quick actions ──
        if query.data == "quick_status":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
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

                msg = (
                    f"\U0001f4ca **Account Status**\n\n"
                    f"\u251c Equity: `${total_equity}`\n"
                    f"\u2514 Available: `${available}`\n"
                )
                if open_pos:
                    msg += f"\n**Open Positions ({len(open_pos)}):**\n"
                    for p in open_pos:
                        symbol = edgex_client.resolve_symbol(p.get("contractId", ""))
                        side = "LONG" if float(p.get("size", "0")) > 0 else "SHORT"
                        pnl_raw = p.get("unrealizedPnl", "0")
                        try:
                            upnl = float(pnl_raw)
                            pnl_str = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
                        except (ValueError, TypeError):
                            pnl_str = f"${pnl_raw}"
                        msg += f"\u2022 {symbol} {side} | PnL: `{pnl_str}`\n"
                else:
                    msg += "\nNo open positions."
                await safe_edit(query, msg, parse_mode="Markdown",
                    reply_markup=_back_button())
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}",
                    reply_markup=_back_button())
            return

        if query.data == "quick_pnl":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                assets = summary.get("assets", {})
                equity_raw = assets.get("totalEquityValue", "0")
                try:
                    equity_str = f"${float(equity_raw):.2f}"
                except (ValueError, TypeError):
                    equity_str = f"${equity_raw}"

                # Positions PnL
                positions = summary.get("positions", [])
                open_pos = [p for p in positions if isinstance(p, dict)]
                total_upnl = 0.0
                pos_lines = ""
                for p in open_pos:
                    sym = edgex_client.resolve_symbol(p.get("contractId", ""))
                    side = p.get("side", "?")
                    size = p.get("size", "0")
                    pnl_raw = p.get("unrealizedPnl", "0")
                    try:
                        upnl = float(pnl_raw)
                        total_upnl += upnl
                        pnl_str = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
                    except (ValueError, TypeError):
                        pnl_str = f"${pnl_raw}"
                    pnl_emoji = "\U0001f7e2" if upnl >= 0 else "\U0001f534"
                    pos_lines += f"{pnl_emoji} {sym} {side} `{size}` | PnL: `{pnl_str}`\n"

                total_emoji = "\U0001f7e2" if total_upnl >= 0 else "\U0001f534"
                total_str = f"+${total_upnl:.2f}" if total_upnl >= 0 else f"-${abs(total_upnl):.2f}"

                msg = f"\U0001f4c8 **P&L Report**\n\n"
                msg += f"Equity: `{equity_str}`\n"
                msg += f"Unrealized P&L: {total_emoji} `{total_str}`\n"

                if pos_lines:
                    msg += f"\n**Open Positions ({len(open_pos)}):**\n{pos_lines}"
                else:
                    msg += "\nNo open positions."

                await safe_edit(query, msg, parse_mode="Markdown",
                    reply_markup=_back_button())
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}",
                    reply_markup=_back_button())
            return

        if query.data == "quick_history":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                orders = await edgex_client.get_order_history(client, limit=5)
                if not orders:
                    await safe_edit(query, "\U0001f4dc No recent trades.",
                        reply_markup=_back_button())
                    return
                msg = "\U0001f4dc **Recent Trades**\n\n"
                for o in orders[:5]:
                    sym = edgex_client.resolve_symbol(o.get("contractId", ""))
                    side = o.get("orderSide", o.get("side", "?"))
                    fill_price = o.get("fillPrice", o.get("price", "?"))
                    fill_size = o.get("fillSize", o.get("size", "?"))
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
                    side_emoji = "\U0001f7e2" if side == "BUY" else "\U0001f534"
                    msg += f"{side_emoji} {sym} {side} {fill_size} @ {price_str}{pnl_str}{ts_str}\n"
                await safe_edit(query, msg, parse_mode="Markdown",
                    reply_markup=_back_button())
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}",
                    reply_markup=_back_button())
            return

        if query.data == "quick_close":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                summary = await edgex_client.get_account_summary(client)
                positions = summary.get("positions", [])
                open_positions = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]
                if not open_positions:
                    await safe_edit(query, "No open positions to close.",
                        reply_markup=_back_button())
                    return
                buttons = []
                msg = "\U0001f534 **Select position to close:**\n"
                for p in open_positions:
                    cid = p.get("contractId", "")
                    symbol = edgex_client.resolve_symbol(cid)
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
                buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
                await safe_edit(query, msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}",
                    reply_markup=_back_button())
            return

        # ── Quick Orders (inline) ──
        if query.data == "quick_orders":
            await query.answer()
            user = db.get_user(user_id)
            if not user:
                await safe_send(context, chat_id, "\u274c Session expired. Use /start.")
                return
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
                orders = await edgex_client.get_open_orders(client)
                if not orders:
                    await safe_edit(query, "\u2705 No open orders.",
                        reply_markup=_back_button())
                    return
                lines = [f"\U0001f4cb **Open Orders** ({len(orders)}):\n"]
                buttons = []
                for o in orders:
                    sym = o.get("symbol", edgex_client.resolve_symbol(o.get("contractId", "")))
                    o_side = o.get("side", "?")
                    o_price = o.get("price", "?")
                    o_size = o.get("size", "?")
                    o_type = o.get("type", "LIMIT")
                    o_id = o.get("id", o.get("orderId", ""))
                    lines.append(f"  \u2022 {sym} {o_side} {o_type} | Size: {o_size} | Price: ${o_price}")
                    if o_id:
                        buttons.append([InlineKeyboardButton(
                            f"\u274c Cancel {sym} {o_side} {o_size}@{o_price}",
                            callback_data=f"cancelone_{o_id}"
                        )])
                buttons.append([InlineKeyboardButton("\u274c Cancel All Orders", callback_data="cancelorders_all")])
                buttons.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
                await safe_edit(query, "\n".join(lines), parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                await safe_edit(query, f"\u274c Error: {str(e)[:200]}",
                    reply_markup=_back_button())
            return

        # ── Logout flow ──
        if query.data == "logout_confirm":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("\u2705 Yes, logout", callback_data="logout_yes"),
                    InlineKeyboardButton("\u274c Cancel", callback_data="logout_no"),
                ]
            ])
            await safe_edit(query,
                "\U0001f6aa **Disconnect**\n\nThis will remove your API key. Are you sure?",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data == "logout_yes":
            conn = db.get_conn()
            conn.execute("DELETE FROM users WHERE tg_user_id = ?", (user_id,))
            conn.execute("DELETE FROM ai_usage WHERE tg_user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            await safe_edit(query,
                "\u2705 Disconnected. Use /start to reconnect.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 Reconnect", callback_data="show_login")]]))
            return

        if query.data == "logout_no":
            user = db.get_user(user_id)
            user_ai = ai_trader.get_user_ai_config(user_id) if user else None
            has_edgex = _has_edgex(user)
            await safe_edit(query, _dashboard_text(user, user_ai),
                parse_mode="Markdown",
                reply_markup=_dashboard_keyboard(has_edgex, has_ai=bool(user_ai)))
            return

        if query.data == "show_login":
            rows = [
                [InlineKeyboardButton("\u26a1 One-Click Login (coming soon)", callback_data="login_oauth")],
                [InlineKeyboardButton("\U0001f511 Connect with API Key", callback_data="login_api")],
            ]
            if config.DEMO_ACCOUNT_ID and config.DEMO_STARK_KEY:
                rows.append([InlineKeyboardButton("\U0001f464 Use Aaron's Account (temp)", callback_data="login_demo")])
            rows.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
            await safe_edit(query,
                "\U0001f517 **Connect edgeX Account**\n\nChoose how to connect:",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
            return

        if query.data == "ai_edgex_credits":
            await safe_edit(query,
                "\U0001f4b3 **edgeX Account Balance** (Coming Soon)\n\n"
                "For now, use /setai to add your own API key.",
                parse_mode="Markdown",
                reply_markup=_back_button("\U0001f519 Back", "ai_activate_prompt"))
            return

        if query.data == "ai_own_key":
            await safe_edit(query,
                "\U0001f511 Use /setai to add your own API key.\n\n"
                "Supports: OpenAI, DeepSeek, Anthropic, Google Gemini, Groq",
                reply_markup=_back_button())
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
                f"\u23f1 *Push Frequency*\n\nHow many alerts per hour?\nCurrent: *{current}/hr*",
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
                "\u2795 *Add News Source*\n\nChoose a topic:",
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
            await safe_send(context, chat_id,
                "\U0001f515 News source muted.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f4f0 News", callback_data="news_settings"),
                     InlineKeyboardButton("\U0001f3e0 Menu", callback_data="back_to_dashboard")]]))
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
                if line and ("\U0001f7e2" in line or "\U0001f534" in line):
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
                    await safe_send(context, chat_id, f"\U0001f504 Generating trade plan: {action_word.upper()} {asset} (~${notional:.0f}, {leverage}x)...")

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
                        keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("\u2705 Confirm Execute", callback_data="confirm_trade"),
                                InlineKeyboardButton("\u274c Cancel", callback_data="cancel_trade"),
                            ]
                        ])
                        await safe_send(context, chat_id, ai_trader.format_trade_plan(plan), parse_mode="Markdown", reply_markup=keyboard)
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

        if query.data == "settings_menu":
            user = db.get_user(user_id)
            has_edgex = _has_edgex(user)
            rows = []
            rows.append([InlineKeyboardButton("\U0001f3ad Change Personality", callback_data="change_persona")])
            rows.append([InlineKeyboardButton("\U0001f511 Change AI Provider", callback_data="ai_activate_prompt")])
            rows.append([InlineKeyboardButton("\U0001f4dd Memory", callback_data="settings_memory")])
            rows.append([InlineKeyboardButton("\U0001f4f0 News Alerts", callback_data="news_settings")])
            if not has_edgex:
                rows.append([InlineKeyboardButton("\U0001f517 Connect edgeX", callback_data="show_login")])
            rows.append([InlineKeyboardButton("\U0001f6aa Disconnect", callback_data="logout_confirm")])
            rows.append([InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_dashboard")])
            await safe_edit(query,
                "\u2699\ufe0f **Settings**",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
            return

        if query.data == "settings_memory":
            user_memory = mem.get_user_memory(user_id)
            stats = user_memory.get_stats()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f5d1 Clear Memory", callback_data="memory_clear_confirm")],
                [InlineKeyboardButton("\U0001f519 Back", callback_data="settings_menu")],
            ])
            await safe_edit(query,
                f"\U0001f4dd **Memory**\n\n"
                f"\u251c Messages: `{stats['conversations']}`\n"
                f"\u251c Summaries: `{stats['summaries']}`\n"
                f"\u2514 Preferences: {'yes' if stats['has_preferences'] else 'not yet'}\n\n"
                f"Use /memory for full details.",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data in ("change_persona", "settings_persona"):
            await safe_edit(query,
                "\U0001f3ad **Choose Agent Personality:**",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(PERSONA_BUTTONS))
            return

        if query.data == "ai_activate_prompt":
            existing = db.get_user(user_id)
            if not existing:
                db.save_user(user_id, "", "")
            await safe_edit(query,
                "\u2728 **Activate AI Agent**\n\nChoose how to power your Agent:",
                parse_mode="Markdown", reply_markup=_ai_activate_keyboard())
            return

        if query.data == "ai_use_free":
            existing = db.get_user(user_id)
            if not existing:
                db.save_user(user_id, "", "")
            ai_trader.save_user_ai_config(user_id, "__FREE__", "https://factory.ai", "claude-sonnet-4.5")
            await safe_edit(query,
                "\u2705 **AI Activated!**\n\n\U0001f3ad **Choose your Agent's personality:**",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(PERSONA_BUTTONS))
            return

        if query.data == "ai_own_key_setup":
            await safe_edit(query,
                "\U0001f511 **Choose your AI provider:**",
                parse_mode="Markdown", reply_markup=_setai_provider_keyboard())
            return

        if query.data.startswith("persona_"):
            persona = query.data.replace("persona_", "")
            conn = db.get_conn()
            conn.execute("UPDATE users SET personality = ? WHERE tg_user_id = ?", (persona, user_id))
            conn.commit()
            conn.close()
            name = PERSONA_NAMES.get(persona, persona)
            await safe_edit(query,
                f"\U0001f525 Personality set: **{name}**\n\nJust talk to me!",
                parse_mode="Markdown",
                reply_markup=_back_button())
            return

        if query.data == "memory_clear_confirm":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("\u2705 Yes, clear all", callback_data="memory_clear_yes"),
                    InlineKeyboardButton("\u274c Keep", callback_data="memory_clear_no"),
                ]
            ])
            await safe_edit(query,
                "\u26a0\ufe0f **Clear Memory?**\n\nAll conversation history and preferences will be deleted.",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data == "memory_clear_yes":
            user_memory = mem.get_user_memory(user_id)
            user_memory.clear()
            await safe_edit(query, "\u2705 Memory cleared.",
                reply_markup=_back_button("\U0001f519 Back", "settings_menu"))
            return

        if query.data == "memory_clear_no":
            user_memory = mem.get_user_memory(user_id)
            stats = user_memory.get_stats()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f5d1 Clear Memory", callback_data="memory_clear_confirm")],
                [InlineKeyboardButton("\U0001f519 Back", callback_data="settings_menu")],
            ])
            await safe_edit(query,
                f"\U0001f4dd **Memory**\n\n"
                f"\u251c Messages: `{stats['conversations']}`\n"
                f"\u251c Summaries: `{stats['summaries']}`\n"
                f"\u2514 Preferences: {'yes' if stats['has_preferences'] else 'not yet'}",
                parse_mode="Markdown", reply_markup=keyboard)
            return

        if query.data == "cancel_trade":
            pending_plans.pop(user_id, None)
            await query.answer("\u274c Cancelled", show_alert=False)
            await safe_send(context, chat_id, "\u274c Trade cancelled.")
            return

        if query.data == "confirm_trade":
            plan = pending_plans.pop(user_id, None)
            if not plan:
                await query.answer()
                await safe_send(context, chat_id, "\u274c Trade plan expired. Send a new request.")
                return

            user = db.get_user(user_id)
            if not user:
                await query.answer()
                await safe_send(context, chat_id, "\u274c Account not connected. Use /start.")
                return

            await query.answer()
            await safe_send(context, chat_id, "\U0001f504 Executing trade on edgeX...")

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            contract_id = await edgex_client.resolve_contract_id(plan["asset"])

            if not contract_id:
                await safe_send(context, chat_id,
                    f"\u274c **Asset not found:** {plan.get('asset')}\n\n"
                    f"This asset might not be available on edgeX right now. "
                    f"Try a different one like BTC, ETH, or SOL.",
                    parse_mode="Markdown")
                return

            # Sanitize size/price: strip non-numeric chars, resolve "market" price
            import re
            raw_size = re.sub(r'[^\d.]', '', str(plan.get("size", "0")))
            raw_price = str(plan.get("entry_price", ""))
            if not raw_price or raw_price.lower() in ("market", "current", ""):
                raw_price = await edgex_client.get_market_price(plan["asset"])
                if not raw_price:
                    await safe_send(context, chat_id,
                        f"\u274c Couldn't fetch market price for {plan['asset']}. Try again.")
                    return
            raw_price = re.sub(r'[^\d.]', '', raw_price)

            # Pre-trade validation: check min order size + balance
            preflight = await edgex_client.pre_trade_check(client, contract_id, plan["side"], raw_size)
            if not preflight["ok"]:
                error = preflight["error"]
                suggestion = preflight.get("suggestion", "")
                # Build smart action buttons based on error type
                action_rows = []
                if "balance" in error.lower() or "not enough" in error.lower():
                    try:
                        summary = await edgex_client.get_account_summary(client)
                        assets = summary.get("assets", {})
                        avail = float(assets.get("availableBalance", "0"))
                        avail_str = f"${avail:.2f}"
                    except Exception:
                        avail_str = "unknown"
                    action_rows.append([
                        InlineKeyboardButton("\U0001f534 Close a Position", callback_data="quick_close"),
                        InlineKeyboardButton("\U0001f4cb Cancel Orders", callback_data="quick_orders"),
                    ])
                    action_rows.append([
                        InlineKeyboardButton("\U0001f4b0 Deposit USDT", url="https://pro.edgex.exchange/portfolio"),
                    ])
                    error = f"Insufficient balance (available: {avail_str})"
                elif "minimum" in error.lower() or "below" in error.lower():
                    action_rows.append([
                        InlineKeyboardButton("\U0001f4ac Try Different Size", callback_data="back_to_dashboard"),
                    ])
                action_rows.append([
                    InlineKeyboardButton("\U0001f4ca Status", callback_data="quick_status"),
                    InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard"),
                ])
                await safe_send(context, chat_id,
                    f"\u274c **Trade blocked**\n\n"
                    f"{error}\n\n"
                    f"{suggestion}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(action_rows))
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

                side_emoji = "\U0001f7e2" if plan["side"] == "BUY" else "\U0001f534"
                side_word = "LONG" if plan["side"] == "BUY" else "SHORT"
                leverage = plan.get("leverage", "1")
                tp = plan.get("take_profit", "")
                sl = plan.get("stop_loss", "")
                value = plan.get("position_value_usd", "")

                msg = (
                    f"{side_emoji} **{side_word} {plan['asset']} — Order Placed!**\n\n"
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

                # Post-trade action buttons
                post_trade_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"\U0001f4ca {plan['asset']} Position", callback_data="quick_status"),
                        InlineKeyboardButton("\U0001f4c8 Live P&L", callback_data="quick_pnl"),
                    ],
                    [
                        InlineKeyboardButton(f"\U0001f534 Close {plan['asset']}", callback_data=f"close_{contract_id}"),
                        InlineKeyboardButton("\U0001f4dc History", callback_data="quick_history"),
                    ],
                    [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ])
                await safe_send(context, chat_id, msg, parse_mode="Markdown", reply_markup=post_trade_kb)
            else:
                error_msg = result.get("msg") or result.get("error", "Unknown error")
                friendly = _friendly_order_error(error_msg, plan)
                error_rows = []
                err_lower = error_msg.lower()
                if "balance" in err_lower or "insufficient" in err_lower or "margin" in err_lower:
                    error_rows.append([
                        InlineKeyboardButton("\U0001f534 Close a Position", callback_data="quick_close"),
                        InlineKeyboardButton("\U0001f4cb Cancel Orders", callback_data="quick_orders"),
                    ])
                    error_rows.append([
                        InlineKeyboardButton("\U0001f4b0 Deposit USDT", url="https://pro.edgex.exchange/portfolio"),
                    ])
                error_rows.append([
                    InlineKeyboardButton("\U0001f4ca Status", callback_data="quick_status"),
                    InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard"),
                ])
                await safe_send(context, chat_id, friendly, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(error_rows))
            return

        if query.data.startswith("close_"):
            contract_id = query.data.replace("close_", "")
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Account not connected.", show_alert=True)
                return

            await query.answer()
            await safe_send(context, chat_id, "\U0001f504 Closing position...")

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            summary = await edgex_client.get_account_summary(client)
            positions = summary.get("positions", [])

            target = None
            for p in positions:
                if isinstance(p, dict) and p.get("contractId") == contract_id:
                    target = p
                    break

            if not target:
                await safe_send(context, chat_id,
                    "\u274c Position not found. It may have already been closed.",
                    reply_markup=_quick_actions_keyboard())
                return

            # Capture pre-close P&L info
            symbol = edgex_client.resolve_symbol(contract_id)
            side = target.get("side", "?")
            entry_price = target.get("entryPrice", "0")
            size = target.get("size", "0")
            pnl_raw = target.get("unrealizedPnl", "0")
            try:
                pnl_f = float(pnl_raw)
                pnl_str = f"+${pnl_f:.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):.2f}"
                pnl_emoji = "\U0001f7e2" if pnl_f >= 0 else "\U0001f534"
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
                    order_lines.append(f"  • {o_side} {o_type} | Size: {o_size} | Price: ${o_price}")
                order_detail = "\n".join(order_lines) if order_lines else ""

                msg = (
                    f"\u26a0\ufe0f **{symbol} {side} close failed — margin insufficient**\n\n"
                    f"You have **{order_count}** open order(s) for {symbol} occupying margin:\n"
                    f"{order_detail}\n\n"
                    f"Cancel these orders to free up margin, then retry close."
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"\u274c Cancel All {symbol} Orders", callback_data=f"cancelorders_{contract_id}")],
                    [InlineKeyboardButton(f"\U0001f504 Retry Close {symbol}", callback_data=f"close_{contract_id}")],
                    [InlineKeyboardButton("\U0001f4cb View Orders", callback_data=f"vieworders_{contract_id}"),
                     InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ])
                await safe_send(context, chat_id, msg, parse_mode="Markdown", reply_markup=kb)
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

                msg = (
                    f"{pnl_emoji} **{symbol} {side} — Closed**\n\n"
                    f"\u251c Entry: `${entry_price}`\n"
                    f"\u251c Size: `{size}`\n"
                    f"\u251c Realized P&L: `{pnl_str}`\n"
                )
                if balance_line:
                    msg += f"{balance_line}\n"
                order_id = result.get("data", {}).get("orderId", result.get("orderId", ""))
                if order_id:
                    msg += f"\u2514 Order ID: `{order_id}`"

                post_close_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("\U0001f4ca Status", callback_data="quick_status"),
                        InlineKeyboardButton("\U0001f4c8 P&L", callback_data="quick_pnl"),
                    ],
                    [
                        InlineKeyboardButton("\U0001f4dc History", callback_data="quick_history"),
                        InlineKeyboardButton("\U0001f4cb Orders", callback_data="quick_orders"),
                    ],
                    [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ])
                await safe_send(context, chat_id, msg, parse_mode="Markdown", reply_markup=post_close_kb)
            else:
                error_msg = result.get("msg", result.get("error", "Unknown"))
                await safe_send(context, chat_id,
                    f"\u274c Close failed: {error_msg}",
                    reply_markup=_quick_actions_keyboard())
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
                btns = []
                if target_id != "all":
                    btns.append([InlineKeyboardButton(f"\U0001f534 Close {symbol}", callback_data=f"close_{target_id}")])
                btns.append([
                    InlineKeyboardButton("\U0001f4ca Status", callback_data="quick_status"),
                    InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard"),
                ])
                await safe_send(context, chat_id,
                    f"\u2705 {label} orders cancelled! Margin freed.",
                    reply_markup=InlineKeyboardMarkup(btns))
            else:
                await safe_send(context, chat_id,
                    f"\u274c Failed to cancel orders: {result.get('error', 'Unknown')}",
                    reply_markup=_quick_actions_keyboard())
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

            lines = [f"\U0001f4cb **Open Orders for {symbol}** ({len(orders)}):\n"]
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
            buttons.append([InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")])

            await safe_send(context, chat_id,
                "\n".join(lines), parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons))
            return

        # ── Cancel a single order ──
        if query.data.startswith("cancelone_"):
            order_id = query.data.replace("cancelone_", "")
            user = db.get_user(user_id)
            if not user:
                await query.answer("\u274c Not connected.", show_alert=True)
                return
            await query.answer()

            client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
            result = await edgex_client.cancel_order(client, user["account_id"], order_id)

            if result.get("code") == "SUCCESS":
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("\U0001f4cb View Orders", callback_data="quick_orders"),
                        InlineKeyboardButton("\U0001f534 Close", callback_data="quick_close"),
                    ],
                    [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="back_to_dashboard")],
                ])
                await safe_send(context, chat_id,
                    f"\u2705 Order cancelled.",
                    reply_markup=kb)
            else:
                await safe_send(context, chat_id,
                    f"\u274c Failed: {result.get('error', 'Unknown')}",
                    reply_markup=_quick_actions_keyboard())
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
            "\U0001f4ca **Account Status**\n\n"
            f"\u251c Equity: `${equity_str}`\n"
            f"\u2514 Available: `${avail_str}`\n"
        )

        positions = summary.get("positions", [])

        if positions:
            msg += f"\n\U0001f4c8 **Open Positions ({len(positions)}):**\n"
            for p in positions:
                cid = p.get("contractId", "")
                symbol = edgex_client.resolve_symbol(cid)
                side = p.get("side", "?")
                size = p.get("size", "0")
                entry = p.get("entryPrice", "0")
                unrealized = p.get("unrealizedPnl", "0")
                liq = p.get("liquidatePrice", "0")
                try:
                    upnl = float(unrealized)
                    pnl_emoji = "\U0001f7e2" if upnl >= 0 else "\U0001f534"
                    pnl_str = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
                except (ValueError, TypeError):
                    pnl_emoji = "\u26aa"
                    pnl_str = unrealized
                try:
                    entry_str = f"${float(entry):.4f}"
                except (ValueError, TypeError):
                    entry_str = entry
                msg += (
                    f"\n{pnl_emoji} **{symbol}** {side} `{size}`\n"
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

        lines = [f"\U0001f4cb **Open Orders** ({len(orders)}):\n"]
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
        msg = "\U0001f534 **Select position to close:**\n"
        for p in open_positions:
            cid = p.get("contractId", "")
            symbol = edgex_client.resolve_symbol(cid)
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

            msg = "\U0001f4dc **Recent Trades (Local)**\n"
            for t in trades:
                symbol = edgex_client.resolve_symbol(t["contract_id"])
                ts = datetime.fromtimestamp(t["created_at"]).strftime("%m/%d %H:%M")
                side_emoji = "\U0001f7e2" if t["side"] == "BUY" else "\U0001f534"
                msg += f"\n{side_emoji} {symbol} {t['side']} | {t['size']} @ ${t['price']} | {t['status']} | {ts}"

            await update.message.reply_text(msg, parse_mode="Markdown",
                reply_markup=_quick_actions_keyboard())
            return

        msg = "\U0001f4dc **Recent Trades (edgeX)**\n"
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
            side_emoji = "\U0001f7e2" if side == "BUY" else "\U0001f534"
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
        pnl_emoji = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        pnl_sign = "+" if total_pnl >= 0 else ""

        card = (
            f"{'=' * 28}\n"
            f"\U0001f4ca  **edgeX Agent Daily Report**\n"
            f"{'=' * 28}\n\n"
            f"Total P&L:  {pnl_emoji} `{pnl_sign}${total_pnl:.2f}`\n"
            f"\u251c Realized: `${realized_pnl:.2f}`\n"
            f"\u2514 Unrealized: `${unrealized_pnl:.2f}`\n\n"
            f"Total Equity: `${equity}`\n\n"
            f"\u251c Trades today: `{total_trades}`\n"
            f"\u2514 Win Rate: `{win_rate:.0f}%`\n\n"
        )

        if positions:
            card += f"**Open Positions ({len(positions)}):**\n"
            for p in positions:
                sym = edgex_client.resolve_symbol(p.get("contractId", ""))
                side = p.get("side", "?")
                size = p.get("size", "0")
                entry = p.get("entryPrice", "0")
                upnl = p.get("unrealizedPnl", "0")
                liq = p.get("liquidatePrice", "0")
                try:
                    upnl_f = float(upnl)
                    pos_emoji = "\U0001f7e2" if upnl_f >= 0 else "\U0001f534"
                    upnl_s = f"+${upnl_f:.2f}" if upnl_f >= 0 else f"-${abs(upnl_f):.2f}"
                except (ValueError, TypeError):
                    pos_emoji = "\u26aa"
                    upnl_s = upnl
                try:
                    entry_f = f"${float(entry):.4f}"
                except (ValueError, TypeError):
                    entry_f = entry
                card += (
                    f"\n{pos_emoji} **{sym}** {side} `{size}`\n"
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
            "\U0001f6aa **Logout**\n\nThis will disconnect your edgeX account from the bot. Are you sure?",
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

    msg = "\U0001f4f0 **News Alerts**\n\nAI-analyzed news with one-tap trade buttons.\n\n"
    if not subs:
        msg += "_No news sources configured yet._\n"
    for s in subs:
        is_on = bool(s.get("subscribed"))
        status = "\u2705" if is_on else "\u274c"
        mph = s.get("user_max_per_hour", 2)
        freq = freq_labels.get(mph, f"{mph}/hr")
        msg += f"{status} **{s['name']}** \u2014 {freq}\n"

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
        "\U0001f916 **edgeX Agent** \u2014 talk to me like a degen, I'll trade like a pro\n\n"
        "_\"BTC\u2019s looking juicy, should I ape in?\"_\n"
        "_\"\u30bd\u30e9\u30ca\u3092\u30ed\u30f3\u30b0\u3057\u305f\u3044\u3001\u5c11\u3057\u3060\u3051\"_\n"
        "_\"\uc9c0\uae08 SILVER \uc0c1\ud669 \uc5b4\ub54c?\"_\n"
        "_\"CRCL\u6da8\u7684\u79bb\u8c31\uff0c\u600e\u4e48\u64cd\u4f5c\"_\n"
        "_\"\u041a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 NVDA \u043d\u0430 100$\"_\n\n"
        "**Commands:**\n"
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
        "\U0001f4ac **Feedback**\n\n"
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
            pref_text = "\n\n\U0001f4cb **What I Know About You:**\n" + "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f5d1 Clear Memory", callback_data="memory_clear_confirm"),
            InlineKeyboardButton("\U0001f519 Back", callback_data="back_to_start"),
        ]
    ])

    await update.message.reply_text(
        f"\U0001f4dd **Memory**\n\n"
        f"\u251c Messages: `{stats['conversations']}`\n"
        f"\u251c Summaries: `{stats['summaries']}`"
        f"{oldest_str}\n"
        f"\u2514 Preferences: {'yes' if stats['has_preferences'] else 'not yet'}"
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
                BotCommand("start", "Start / Dashboard"),
                BotCommand("status", "Balance & positions"),
                BotCommand("close", "Close a position"),
                BotCommand("orders", "View & cancel open orders"),
                BotCommand("history", "Recent trades"),
                BotCommand("pnl", "P&L report"),
                BotCommand("setai", "Configure AI"),
                BotCommand("memory", "View Agent's memory"),
                BotCommand("news", "Manage news alerts"),
                BotCommand("feedback", "Suggest features / report bugs"),
                BotCommand("logout", "Disconnect account"),
                BotCommand("help", "All commands"),
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
            WAITING_AI_KEY: [
                CallbackQueryHandler(handle_setai_provider, pattern="^setai_"),
                CallbackQueryHandler(handle_trade_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ai_key),
            ],
            WAITING_AI_BASE_URL: [
                CallbackQueryHandler(handle_url_button, pattern="^url_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ai_base_url),
            ],
            WAITING_AI_MODEL: [
                CallbackQueryHandler(handle_model_button, pattern="^model_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ai_model),
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
