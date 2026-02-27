"""Briefing ConversationHandler — collects all trip details from the user.

State machine:
    ORIGIN -> PARTY_SIZE -> COUNTRY -> DAYS -> MONTH ->
    BUDGET -> PACE -> FOCUS -> CROWDS -> HOTEL -> RESTRICTIONS -> CONFIRM

All validation is inline; invalid inputs re-prompt without cancelling the
conversation.  On confirmation the handler calls the internal API to create
the trip and payment session, then stores trip_id in user_data and ends.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Final

import httpx
import structlog
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.lib.config import settings

log = structlog.get_logger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
(
    ORIGIN,
    PARTY_SIZE,
    COUNTRY,
    DAYS,
    MONTH,
    BUDGET,
    PACE,
    FOCUS,
    CROWDS,
    HOTEL,
    RESTRICTIONS,
    CONFIRM,
) = range(12)

# ── Validation allowlists ─────────────────────────────────────────────────────

EUROPEAN_COUNTRIES: Final[frozenset[str]] = frozenset(
    {
        "italy",
        "france",
        "spain",
        "portugal",
        "germany",
        "austria",
        "switzerland",
        "netherlands",
        "belgium",
        "greece",
        "croatia",
        "czech republic",
        "czechia",
        "hungary",
        "poland",
        "norway",
        "sweden",
        "denmark",
        "finland",
        "iceland",
        "ireland",
        "scotland",
        "uk",
        "united kingdom",
        "england",
        "romania",
        "bulgaria",
        "slovakia",
        "slovenia",
        "estonia",
        "latvia",
        "lithuania",
    }
)

VALID_PARTY_SIZES: Final[frozenset[str]] = frozenset({"solo", "couple"})
VALID_PACES: Final[frozenset[str]] = frozenset({"light", "medium", "intense"})
VALID_FOCUS_ITEMS: Final[frozenset[str]] = frozenset({"food", "culture", "nature"})
VALID_CROWDS: Final[frozenset[str]] = frozenset({"low", "medium", "high"})
VALID_HOTELS: Final[frozenset[str]] = frozenset({"5star", "boutique", "mixed"})

_MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])/(\d{4})$")

# ── Keyboard helpers ──────────────────────────────────────────────────────────


def _kb(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(list(rows), resize_keyboard=True, one_time_keyboard=True)


_KB_PARTY = _kb(["solo", "couple"])
_KB_PACE = _kb(["light", "medium", "intense"])
_KB_CROWDS = _kb(["low", "medium", "high"])
_KB_HOTEL = _kb(["5star", "boutique", "mixed"])
_KB_CONFIRM = _kb(["YES", "NO"])
_RM = ReplyKeyboardRemove()

# ── API client ────────────────────────────────────────────────────────────────

_API_HEADERS: dict[str, str] = {"X-API-Key": settings.internal_api_key}


async def _post(path: str, payload: dict) -> dict:
    """POST to the internal API; raises httpx.HTTPStatusError on 4xx/5xx."""
    async with httpx.AsyncClient(
        base_url=settings.api_base_url,
        headers=_API_HEADERS,
        timeout=30.0,
    ) as client:
        response = await client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


# ── State handlers ────────────────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point — /start command."""
    context.user_data.clear()
    await update.message.reply_text(
        "Welcome to the *Luxury Europe Trip Planner*! ✈️\n\n"
        "I'll help you build a personalised itinerary for your European adventure.\n\n"
        "Let's start: *What is your departure city or airport?*\n"
        "_Example: São Paulo / GRU_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return ORIGIN


async def receive_origin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    origin = update.message.text.strip()
    if not origin:
        await update.message.reply_text("Please enter your departure city or airport.")
        return ORIGIN
    context.user_data["origin"] = origin
    await update.message.reply_text(
        "Are you travelling *solo* or as a *couple*?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_KB_PARTY,
    )
    return PARTY_SIZE


async def receive_party_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in VALID_PARTY_SIZES:
        await update.message.reply_text(
            "Please reply *solo* or *couple*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_KB_PARTY,
        )
        return PARTY_SIZE
    context.user_data["party_size"] = text
    await update.message.reply_text(
        "Which *European country* would you like to visit?\n"
        "_Examples: Italy, France, Spain, Portugal, Greece…_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return COUNTRY


async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() not in EUROPEAN_COUNTRIES:
        await update.message.reply_text(
            "I only plan trips within Europe. Please enter a European country "
            "(e.g. Italy, France, Spain, Portugal, Germany, Greece…)."
        )
        return COUNTRY
    context.user_data["country"] = text.title()
    await update.message.reply_text(
        "How many *days* is your trip? _(between 3 and 30)_\n"
        "_Example: 10_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return DAYS


async def receive_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        days = int(text)
    except ValueError:
        await update.message.reply_text("Please enter a number of days (e.g. 10).")
        return DAYS
    if not (3 <= days <= 30):
        await update.message.reply_text("Please enter a number between 3 and 30.")
        return DAYS
    context.user_data["days"] = days
    await update.message.reply_text(
        "Which *month and year* are you planning to travel?\n"
        "_Format: MM/YYYY — Example: 09/2026_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return MONTH


async def receive_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    match = _MONTH_RE.match(text)
    if not match:
        await update.message.reply_text(
            "Please use the format MM/YYYY (e.g. 09/2026)."
        )
        return MONTH
    month = int(match.group(1))
    year = int(match.group(2))
    today = date.today()
    if (year, month) < (today.year, today.month):
        await update.message.reply_text(
            "That month is already in the past. Please enter a future month/year."
        )
        return MONTH
    context.user_data["dates_or_month"] = text
    await update.message.reply_text(
        "What is your *budget per person* in BRL?\n"
        "_Example: 30000_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return BUDGET


async def receive_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(".", "").replace(",", "")
    try:
        budget = int(text)
    except ValueError:
        await update.message.reply_text(
            "Please enter a number (e.g. 30000)."
        )
        return BUDGET
    if budget <= 0:
        await update.message.reply_text("Budget must be a positive number.")
        return BUDGET
    context.user_data["budget_per_person_brl"] = budget
    await update.message.reply_text(
        "What *pace* do you prefer for your trip?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_KB_PACE,
    )
    return PACE


async def receive_pace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in VALID_PACES:
        await update.message.reply_text(
            "Please choose: *light*, *medium*, or *intense*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_KB_PACE,
        )
        return PACE
    context.user_data["pace"] = text
    await update.message.reply_text(
        "What are your *focus priorities*? List up to 3 in order, comma-separated.\n"
        "_Options: food, culture, nature_\n"
        "_Example: culture, food, nature_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return FOCUS


async def receive_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip().lower()
    items = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [i for i in items if i not in VALID_FOCUS_ITEMS]
    if not items or invalid:
        await update.message.reply_text(
            "Please enter a comma-separated list from: food, culture, nature\n"
            "_Example: culture, food, nature_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return FOCUS
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_items: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            unique_items.append(i)
    context.user_data["focus"] = unique_items[:3]
    await update.message.reply_text(
        "How do you feel about *crowds*?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_KB_CROWDS,
    )
    return CROWDS


async def receive_crowds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in VALID_CROWDS:
        await update.message.reply_text(
            "Please choose: *low*, *medium*, or *high*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_KB_CROWDS,
        )
        return CROWDS
    context.user_data["crowds"] = text
    await update.message.reply_text(
        "What is your *hotel preference*?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_KB_HOTEL,
    )
    return HOTEL


async def receive_hotel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text not in VALID_HOTELS:
        await update.message.reply_text(
            "Please choose: *5star*, *boutique*, or *mixed*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_KB_HOTEL,
        )
        return HOTEL
    context.user_data["hotel"] = text
    await update.message.reply_text(
        "Do you have any *special restrictions*?\n"
        "_Examples: mobility:wheelchair, diet:vegan, diet:gluten-free_\n"
        "_Type *none* to skip._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )
    return RESTRICTIONS


async def receive_restrictions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() == "none":
        context.user_data["restrictions"] = []
    else:
        context.user_data["restrictions"] = [r.strip() for r in text.split(",") if r.strip()]

    # Build and show summary
    ud = context.user_data
    focus_display = ", ".join(ud.get("focus", []))
    restrictions_display = (
        ", ".join(ud.get("restrictions", [])) or "none"
    )

    summary = (
        "Please review your trip details:\n\n"
        f"🛫 *Departure:* {ud.get('origin')}\n"
        f"👥 *Party:* {ud.get('party_size')}\n"
        f"🌍 *Country:* {ud.get('country')}\n"
        f"📅 *When:* {ud.get('dates_or_month')}\n"
        f"🗓 *Days:* {ud.get('days')}\n"
        f"💰 *Budget/person:* R${ud.get('budget_per_person_brl'):,}\n"
        f"⚡ *Pace:* {ud.get('pace')}\n"
        f"🎯 *Focus:* {focus_display}\n"
        f"👤 *Crowds:* {ud.get('crowds')}\n"
        f"🏨 *Hotel:* {ud.get('hotel')}\n"
        f"⚠️ *Restrictions:* {restrictions_display}\n\n"
        "Is this correct? Reply *YES* to confirm or *NO* to start over."
    )

    await update.message.reply_text(
        summary,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_KB_CONFIRM,
    )
    return CONFIRM


async def receive_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()

    if text == "NO":
        await update.message.reply_text(
            "No problem! Let's start over. Type /start when you're ready.",
            reply_markup=_RM,
        )
        context.user_data.clear()
        return ConversationHandler.END

    if text != "YES":
        await update.message.reply_text(
            "Please reply *YES* to confirm or *NO* to start over.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_KB_CONFIRM,
        )
        return CONFIRM

    # User confirmed — call API
    user = update.effective_user
    ud = context.user_data

    trip_payload = {
        "telegram_user_id": user.id,
        "telegram_name": user.full_name or user.username or str(user.id),
        "origin": ud["origin"],
        "country": ud["country"],
        "dates_or_month": ud["dates_or_month"],
        "days": ud["days"],
        "party_size": ud["party_size"],
        "budget_per_person_brl": ud["budget_per_person_brl"],
        "preferences": {
            "pace": ud["pace"],
            "focus": ud["focus"],
            "crowds": ud["crowds"],
            "hotel": ud["hotel"],
            "restrictions": ud.get("restrictions", []),
        },
    }

    await update.message.reply_text(
        "Got it! Creating your trip…",
        reply_markup=_RM,
    )

    try:
        trip_response = await _post("/api/trips", trip_payload)
        trip_id: str = trip_response["trip_id"]
    except Exception as exc:
        log.error("create_trip_failed", user_id=user.id, error=str(exc))
        await update.message.reply_text(
            "Something went wrong creating your trip. Please try again or type /start to restart."
        )
        return ConversationHandler.END

    # Persist trip_id for /check command
    context.user_data["trip_id"] = trip_id

    # Demo mode — skip payment and trigger generation directly
    try:
        await _post(f"/api/trips/{trip_id}/generate", {})
    except Exception:
        pass  # Generation is async via Celery; failure here is non-fatal

    await update.message.reply_text(
        f"✅ *Briefing received!*\n\n"
        f"Your personalised itinerary is being generated. This usually takes a few minutes.\n\n"
        f"Trip ID: `{trip_id}`\n\n"
        f"Type /check anytime to see when your plan is ready.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_RM,
    )

    log.info("briefing_complete", user_id=user.id, trip_id=trip_id)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel — exits the conversation from any state."""
    await update.message.reply_text(
        "Conversation cancelled. Type /start to begin again.",
        reply_markup=_RM,
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── ConversationHandler assembly ──────────────────────────────────────────────

briefing_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_origin)],
        PARTY_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_party_size)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country)],
        DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_days)],
        MONTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_month)],
        BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_budget)],
        PACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pace)],
        FOCUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_focus)],
        CROWDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_crowds)],
        HOTEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_hotel)],
        RESTRICTIONS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_restrictions)
        ],
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confirm)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    # Persist user_data across separate messages in the same conversation
    allow_reentry=True,
)
