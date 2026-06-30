from __future__ import annotations

import os

DASHBOARD_TO_DB_STATUS = {
    "baru": "pending",
    "diproses": "confirmed",
    "selesai": "completed",
    "dibatalkan": "cancelled",
}
DB_TO_DASHBOARD_STATUS = {v: k for k, v in DASHBOARD_TO_DB_STATUS.items()}

STATUS_WA_MESSAGE = {
    "confirmed": "Pesanan kakak lagi disiapkan ya 🙏",
    "completed": "Pesanan kakak sudah selesai! Terima kasih 😊",
    "cancelled": "Mohon maaf, pesanan kakak dibatalkan.",
}

BOOKING_STATUS_WA_MESSAGE = {
    "confirmed": "Booking kakak {when} sudah dikonfirmasi ✅.",
    "rejected": "Mohon maaf, jadwal yang diminta belum bisa. Boleh pilih waktu lain Kak?",
    "completed": "Terima kasih sudah datang ke {store}! Sampai jumpa lagi 😊",
    "cancelled": "Mohon maaf, booking kakak dibatalkan.",
}

DEFAULT_SETTINGS: dict = {
    "auto_reply_enabled": True,
    "greeting_message": "",
    "after_hours_message": "",
    "business_hours": {"open": "08:00", "close": "21:00"},
    "faq": [],
}

# UPLOAD_DIR resolves to backend/uploads/ from app/api/constants.py:
#   dirname(abspath(__file__)) = app/api/
#   dirname(...)               = app/
#   dirname(...)               = backend/
#   + "uploads"                = backend/uploads/
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
)
