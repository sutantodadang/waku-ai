"""Bahasa Indonesia NLU — Intent classification & entity extraction using regex/keyword matching.

Zero external NLP dependency. Handles Indonesian slang commonly used in WhatsApp chats.
"""

import re
from typing import Optional

# ──────────────────────────────────────────────
#  Intent patterns — regex rules for Indonesian
# ──────────────────────────────────────────────

INTENT_PATTERNS: dict[str, list[str]] = {
    "GREETING": [
        r"\bhalo\b",
        r"\bhai\b",
        r"\bhei\b",
        r"\bhi\b",
        r"\bhelo\b",
        r"\bassalamualaikum\b",
        r"\bassalamu'alaikum\b",
        r"\bassalam\b",
        r"\bselamat (pagi|siang|sore|malam)\b",
        r"\bpagi\b",
        r"\bsiang\b",
        r"\bsore\b",
        r"\bmalam\b",
        r"\bada (yang|yg) bisa (dibantu|bantu)\b",
        r"\bpermisi\b",
        r"\btes\b",
        r"\btesting\b",
    ],
    "ORDER": [
        r"\bp(e|a)sen\b",
        r"\b(?:mau|ingin|minta|saya|sy|aku|gue|gw) (pesan|beli|order|mesen|membeli|mengorder)\b",
        r"\bpesan(?:kan|in|)?\b",
        r"\b(?:mau|ingin|minta|saya|sy|aku|gue|gw) (?:m|n)asi\b",
        r"\b(?:mau|ingin|minta|saya|sy|aku|gue|gw) (?:m|n)inum\b",
        r"\b(?:mau|ingin|minta|saya|sy|aku|gue|gw) bel(i|iin)\b",
        r"\bcatalog?\b",
        r"\bmenu\b",
        r"\bdaftar (menu|harga|produk)\b",
        r"\b(?:mau|ingin|minta|saya|sy|aku|gue|gw) lihat\b",
        r"\bsaya mau\b",
        r"\baku mau\b",
        r"\bsy mw\b",
        r"\baku mw\b",
        r"\bgw mw\b",
        r"\bgue mau\b",
        r"\btambah (?:lagi|satu|order|pesanan)\b",
        r"\bapa (?:lagi|aja|saja)\b",
        r"\bitu (?:aja|saja|doang|dongs?)\b",
        r"\bsaya (?:mau|ingin) (?:order|pesan|beli)\b",
        r"\bsy (?:mau|mo|mw) (?:order|pesan|beli)\b",
        r"\baku (?:mau|mo|mw) (?:order|pesan|beli)\b",
    ],
    "BOOKING": [
        r"\bbooking\b", r"\bbuking\b", r"\bbuk in\b",
        r"\bjanji\b", r"\bjanjian\b", r"\breservasi\b", r"\breserve\b",
        r"\bjadwal\b", r"\bjadwalin\b",
        r"\b(?:kapan|jam berapa) (?:bisa|kosong|available)\b",
        r"\bmau (?:booking|janji|reservasi|jadwal)\b",
    ],
    "INQUIRY_PRICE": [
        r"\bharga\b",
        r"\bberapa\b",
        r"\bpricen?a\b",
        r"\bbandrol\b",
        r"\btarif\b",
        r"\bbayar(?:nya|in)?\b",
        r"\bbrapa\b",
        r"\b(?:mau|ingin|tanya) (?:harga|price)\b",
        r"\b(?:berapa|brapa) (?:harga|harganya|price)\b",
        r"\bmahal\b",
        r"\bmurah\b",
        r"\bdiskon\b",
        r"\bpromo\b",
    ],
    "INQUIRY_STOCK": [
        r"\bstok\b",
        r"\bstock\b",
        r"\btersedia\b",
        r"\bada (?:gak|gk|nggak|ngg?|tidak|ga)?\b",
        r"\bkosong\b",
        r"\bhabis\b",
        r"\bready\b",
        r"\bavailable\b",
        r"\bmasih (?:ada|tersedia)\b",
        r"\bapakah (?:ada|tersedia)\b",
        r"\bketersediaan\b",
    ],
    "COMPLAINT": [
        r"\bkomplen\b",
        r"\bkeluhan\b",
        r"\bkecewa\b",
        r"\bkecewa\b",
        r"\bsalah\b",
        r"\berror\b",
        r"\b(?:gk|ga|gak|nggak|tidak|tdk|belum) (?:sesuai|sampai|datang|nyampe|terima)\b",
        r"\b(?:pesanan|order) (?:belum|gk|ga|gak|nggak) (?:datang|sampai|nyampe)\b",
        r"\b(?:rusak|cacat|bocor|tumpah|robek)\b",
        r"\b(?:kurang|nggak?|gk|ga) (?:lengkap|enak|pantes|muant?[a-z]*)\b",
        r"\b(?:gak|gk|ga|nggak|ngg) (?:enak|puas|sreg)\b",
        r"\b(?:minta|mohon) (?:refund|return|ganti|kompensasi)\b",
        r"\b(?:maaf|sorry|sori|mohon maaf|maapkan)\b(?!.*(?:gak|gk|ga|nggak) (?:apa|masalah))\b",
        r"\b(?:belum|gk|ga|gak|nggak) (?:datang|sampai|nyampe|terima|dapet)\b",
    ],
    "PAYMENT": [
        r"\bbayar\b",
        r"\bbayar\b",
        r"\btransfer\b",
        r"\bcod\b",
        r"\bbayar di tempat\b",
        r"\b(?:via|lewat|pakai|pake) (?:transfer|tf|gopay|ovo|dana|shopeepay|qris|bca|mandiri|bri|bni)\b",
        r"\brekening\b",
        r"\bnomer rekening\b",
        r"\bnomor rekening\b",
        r"\bnorek\b",
        r"\bpembayaran\b",
        r"\bpembayaran\b",
        r"\b(?:sudah|udah|sdh|udh|saya|sy|aku|gw|gue) (?:bayar|transfer|tf)\b",
        r"\b(?:konfirmasi|confirm|konfir) (?:pembayaran|bayar)\b",
        r"\b(?:minta|mohon|tolong) (?:bayar|transfer|tf)\b",
    ],
    "CLOSING": [
        r"\bterima kasih\b",
        r"\bmakasih\b",
        r"\bmksh\b",
        r"\bthanks\b",
        r"\bthx\b",
        r"\btenkyu\b",
        r"\bthank you\b",
        r"\bmaturnuwun\b",
        r"\bsuwun\b",
        r"\bda(?:h|dah|dah)\b",
        r"\bsampai jumpa\b",
        r"\bsampai ketemu\b",
        r"\bbye\b",
        r"\bbye-bye\b",
        r"\bgoodbye\b",
        r"\bsip(?: sip)?\b",
        r"\bok(?: ok)?\b",
        r"\bsiap(?: siap)?\b",
        r"\bsudah dulu\b",
        r"\bitu aja\b",
        r"\bitu saja\b",
        r"\bbegitu aja\b",
        r"\bgitu aja\b",
        r"\bcukup\b",
        r"\bselesai\b",
        r"\bgitu doang\b",
        r"\bgitu dongs\b",
    ],
}


def classify_intent(text: str) -> str:
    """
    Classify the intent of a user message using regex pattern matching.

    Returns one of: GREETING, ORDER, INQUIRY_PRICE, INQUIRY_STOCK,
                    COMPLAINT, PAYMENT, CLOSING, UNKNOWN
    """
    text_lower = text.lower().strip()

    if not text_lower:
        return "UNKNOWN"

    scores: dict[str, int] = {}

    for intent, patterns in INTENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            score += len(matches)
        if score > 0:
            scores[intent] = score

    if not scores:
        return "UNKNOWN"

    # Return the intent with the highest score
    return max(scores, key=scores.get)


# ──────────────────────────────────────────────
#  Entity extraction
# ──────────────────────────────────────────────

# Regex patterns for entity extraction
PHONE_PATTERN = re.compile(r"(?:\+62|62|0)(?:[ -]?\d{2,3}[ -]?\d{4,8})")
QUANTITY_PATTERN = re.compile(r"(\d+)\s*(porsi|buah|pack|botol|gelas|kardus|pcs|biji?|kg|gram|liter|ml|pasang|lusin|kodi|rim|ikat)")
PRICE_PATTERN = re.compile(r"(?:Rp|rp|RP|\.)?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*(?:rb|ribu|jt|juta)?")
QTY_BEFORE_PATTERN = re.compile(r"(\d+)\s*")
QTY_AFTER_PATTERN = re.compile(r"\s*(\d+)\s*")

# Common product name patterns (can be extended via catalog)
# Product names are usually nouns that follow quantity words


def extract_entities(text: str, catalog_items: Optional[list[str]] = None) -> dict:
    """
    Extract structured entities from Indonesian text.

    Returns a dict with:
        - phone_numbers: list of phone numbers found
        - quantities: list of (qty, unit) tuples
        - prices: list of price values (in IDR, as int)
        - product_names: list of product names found (if catalog provided)
        - raw_numbers: list of raw numbers found
    """
    text_lower = text.lower()
    result = {
        "phone_numbers": [],
        "quantities": [],
        "prices": [],
        "product_names": [],
        "raw_numbers": [],
    }

    # Phone numbers
    phone_matches = PHONE_PATTERN.findall(text)
    result["phone_numbers"] = [p.strip() for p in phone_matches]

    # Quantities with units
    qty_matches = QUANTITY_PATTERN.findall(text_lower)
    result["quantities"] = [(int(q), u) for q, u in qty_matches]

    # Prices (IDR)
    price_matches = PRICE_PATTERN.findall(text)
    for price_str in price_matches:
        try:
            # Remove dots (thousand separators) and commas
            clean = price_str.replace(".", "").replace(",", ".")
            if "." in clean:
                value = int(float(clean))
            else:
                value = int(clean)
            if value > 0:
                result["prices"].append(value)
        except ValueError:
            pass

    # Product names from catalog (simple substring matching)
    if catalog_items:
        for item in catalog_items:
            if item.lower() in text_lower:
                result["product_names"].append(item)

    # Per-product quantity, aligned to product_names. QUANTITY_PATTERN requires a
    # unit ("2 porsi"), so bare numbers like "nasi goreng 2" are missed — resolve
    # here by scanning the number adjacent to each product name (matches the
    # backend's catalog extractor, so the WA reply and the dashboard order agree).
    NUMBER_WORDS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
                    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10}
    product_quantities = []
    for name in result["product_names"]:
        nlow = name.lower()
        idx = text_lower.find(nlow)
        qty = 1
        if idx != -1:
            before = text_lower[:idx]
            after = text_lower[idx + len(nlow):]
            m_before = re.search(r"(\d+)\s*x?\s*$", before)
            m_after = re.match(r"\s*x?\s*(\d+)", after)
            if m_before:
                qty = int(m_before.group(1))
            elif m_after:
                qty = int(m_after.group(1))
            else:
                window = before[-20:] + " " + after[:20]
                for word, num in NUMBER_WORDS.items():
                    if re.search(r"\b" + word + r"\b", window):
                        qty = num
                        break
        product_quantities.append(qty)
    result["product_quantities"] = product_quantities

    # Raw numbers (all digits found)
    all_numbers = re.findall(r"\b(\d+)\b", text)
    result["raw_numbers"] = [int(n) for n in all_numbers if int(n) < 1000000]

    return result


# ──────────────────────────────────────────────
#  Quick helper
# ──────────────────────────────────────────────

def analyze_message(text: str, catalog_items: Optional[list[str]] = None) -> dict:
    """
    One-shot NLU analysis: intent + entities.

    Returns:
        {
            "intent": str,
            "entities": dict,
            "original_text": str,
            "normalized_text": str
        }
    """
    # Normalize common slang
    normalized = text.lower()
    slang_map = {
        r"\b(sy|gue|gw|aq|akuh)\b": "saya",
        r"\b(gk|ga|gak|nggak|ngg|ngga|kagak|ndak)\b": "tidak",
        r"\b(dongs|dong|dung)\b": "dong",
        r"\b(gan|bro|sis|boss|bos)\b": "kak",
        r"\b(mbak|mas|kak)\b": "kak",
        r"\b(mo|mw)\b": "mau",
        r"\b(aja|aj|doang|doank)\b": "saja",
        r"\b(udh|udah|sdh|sdah)\b": "sudah",
        r"\b(gpp)\b": "gak apa apa",
        r"\b(wk|wkwk|wkwkwk|haha|hehe|xixi)\b": "",
        r"\b(bgt|banget)\b": "sekali",
        r"\b(mkasih|mksh|maci|makasih)\b": "terima kasih",
        r"\b(pake|pkae)\b": "pakai",
        r"\b(klo|klw|kalo|kalau)\b": "kalau",
    }
    for pattern, repl in slang_map.items():
        normalized = re.sub(pattern, repl, normalized, flags=re.IGNORECASE)

    intent = classify_intent(normalized)
    entities = extract_entities(text, catalog_items)

    return {
        "intent": intent,
        "entities": entities,
        "original_text": text,
        "normalized_text": normalized.strip(),
    }
