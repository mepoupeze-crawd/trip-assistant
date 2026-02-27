"""Delivery handler — /check command.

The user types /check (or it is called programmatically) to poll the API and,
when the trip is ready, send the PDF and DOCX presigned URLs.

Flow:
  1. Read trip_id from user_data (set by briefing handler after confirmation).
  2. GET /api/trips/{trip_id}/status
  3. status == "done"    → GET /api/trips/{trip_id}/output → send links
  4. status in queued/running → tell user to check back later
  5. status == "failed"  → ask user to contact support
  6. No trip_id in user_data → ask user to start a new trip

All API calls use X-API-Key from settings (C7 contract).
"""

from __future__ import annotations

import structlog
import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from src.lib.config import settings

log = structlog.get_logger(__name__)

_API_HEADERS: dict[str, str] = {"X-API-Key": settings.internal_api_key}


async def _get(path: str) -> dict:
    """GET from the internal API; raises httpx.HTTPStatusError on 4xx/5xx."""
    async with httpx.AsyncClient(
        base_url=settings.api_base_url,
        headers=_API_HEADERS,
        timeout=30.0,
    ) as client:
        response = await client.get(path)
        response.raise_for_status()
        return response.json()


async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/check command handler — polls trip status and delivers documents when ready."""
    user = update.effective_user
    trip_id: str | None = context.user_data.get("trip_id")

    if not trip_id:
        await update.message.reply_text(
            "I don't have an active trip for you yet.\n"
            "Type /start to plan your Luxury Europe Trip!"
        )
        return

    # ── Poll status ───────────────────────────────────────────────────────────
    try:
        status_data = await _get(f"/api/trips/{trip_id}/status")
    except httpx.HTTPStatusError as exc:
        log.error(
            "check_status_http_error",
            user_id=user.id,
            trip_id=trip_id,
            status_code=exc.response.status_code,
        )
        if exc.response.status_code == 404:
            await update.message.reply_text(
                "Your trip is still being queued for generation.\n\n"
                "Please type /check again in a moment."
            )
        else:
            await update.message.reply_text(
                "Something went wrong checking your trip status. Please try again later."
            )
        return
    except Exception as exc:
        log.error("check_status_error", user_id=user.id, trip_id=trip_id, error=str(exc))
        await update.message.reply_text(
            "Something went wrong. Please try again or type /start to restart."
        )
        return

    status: str = status_data.get("status", "unknown")

    # ── Status: still in progress ─────────────────────────────────────────────
    if status in ("queued", "running"):
        await update.message.reply_text(
            "⏳ Your trip plan is still being prepared — it usually takes a few minutes.\n\n"
            "Please type /check again in a moment."
        )
        return

    # ── Status: failed ────────────────────────────────────────────────────────
    if status == "failed":
        error_message = status_data.get("error_message") or "Unknown error."
        log.warning(
            "trip_generation_failed_reported_to_user",
            user_id=user.id,
            trip_id=trip_id,
            error_message=error_message,
        )
        await update.message.reply_text(
            "There was an error generating your trip plan. "
            "Please contact support and mention your trip ID:\n"
            f"`{trip_id}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Status: done — fetch output URLs ─────────────────────────────────────
    if status == "done":
        try:
            output_data = await _get(f"/api/trips/{trip_id}/output")
        except httpx.HTTPStatusError as exc:
            log.error(
                "check_output_http_error",
                user_id=user.id,
                trip_id=trip_id,
                status_code=exc.response.status_code,
            )
            await update.message.reply_text(
                "Your trip is marked as ready but I couldn't retrieve the files. "
                "Please try /check again in a moment."
            )
            return
        except Exception as exc:
            log.error("check_output_error", user_id=user.id, trip_id=trip_id, error=str(exc))
            await update.message.reply_text(
                "Something went wrong fetching your trip documents. Please try again."
            )
            return

        pdf_url: str = output_data.get("pdf_url", "")
        docx_url: str = output_data.get("docx_url", "")

        log.info("trip_delivered", user_id=user.id, trip_id=trip_id)

        await update.message.reply_text(
            "🎉 *Your trip plan is ready!*\n\n"
            f"📄 [Download PDF]({pdf_url})\n"
            f"📝 [Download DOCX]({docx_url})\n\n"
            "Links are valid for 7 days. Enjoy your trip! ✈️",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    # ── Unknown status (defensive) ────────────────────────────────────────────
    log.warning("unknown_trip_status", user_id=user.id, trip_id=trip_id, status=status)
    await update.message.reply_text(
        f"Unexpected trip status: `{status}`. Please type /check again or contact support.",
        parse_mode=ParseMode.MARKDOWN,
    )
