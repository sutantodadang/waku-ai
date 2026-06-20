"""
app.py — Waku Dashboard
Web UI untuk pemilik UMKM Indonesia.
Streamlit multi-page app — mobile-first, Bahasa Indonesia, warna hangat.
"""

import os
import io
import base64
from datetime import datetime

import streamlit as st
from PIL import Image

from api_client import WakuAPIClient, WakuAPIError

# ---------------------------------------------------------------------------
# KONFIGURASI HALAMAN
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Waku — Dashboard UMKM",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# WARNA & TEMA
# ---------------------------------------------------------------------------
TEAL = "#008080"
TEAL_LIGHT = "#E0F2F1"
TEAL_DARK = "#004D40"
ORANGE = "#FF6D00"
ORANGE_LIGHT = "#FFF3E0"
ORANGE_BG = "#FF9800"
WHITE = "#FFFFFF"
GRAY_BG = "#F5F5F5"
GRAY_TEXT = "#616161"
GREEN = "#2E7D32"
RED = "#C62828"
YELLOW = "#F9A825"

def local_css():
    """Suntik CSS kustom untuk tampilan mobile-first yang bersih."""
    st.markdown(
        f"""
        <style>
        /* ── #2 Font: Plus Jakarta Sans — warm, geometric, friendly; fits UMKM product ── */
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

        /* ── #7 Spacing system ── */
        :root {{
            --space-xs: 0.5rem;
            --space-sm: 0.75rem;
            --space-md: 1rem;
            --space-lg: 1.5rem;
            --space-xl: 2rem;
            --radius: 16px;
            --radius-sm: 12px;
            --radius-pill: 50px;
            --font-display: 'Plus Jakarta Sans', sans-serif;
            --font-body: 'Plus Jakarta Sans', sans-serif;
            --color-teal: {TEAL};
            --color-teal-light: {TEAL_LIGHT};
            --color-teal-dark: {TEAL_DARK};
            --color-orange: {ORANGE};
            --color-orange-light: {ORANGE_LIGHT};
            --color-orange-bg: {ORANGE_BG};
            --color-white: {WHITE};
            --color-gray-bg: {GRAY_BG};
            --color-gray-text: {GRAY_TEXT};
            --color-green: {GREEN};
            --color-red: {RED};
        }}

        /* ── #2 Apply fonts ── */
        h1, h2, h3 {{
            font-family: var(--font-display) !important;
            font-weight: 700;
        }}
        body, p, span, div, input, textarea, select, label, button {{
            font-family: var(--font-body) !important;
        }}

        /* ── #3 Hide ALL Streamlit chrome ── */
        #MainMenu,
        footer,
        .stDeployButton,
        header[data-testid="stHeader"],
        [data-testid="stSidebar"] > div:first-child {{
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
        }}
        [data-testid="stSidebar"] {{
            display: none !important;
        }}
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        .stApp {{
            background-color: var(--color-gray-bg) !important;
        }}
        /* Remove default Streamlit padding that creates gaps */
        .stApp > header {{
            display: none !important;
        }}
        section[data-testid="stSidebar"] {{
            display: none !important;
        }}

        /* ── #6 Layout: centered, intentional, not floating ── */
        .block-container {{
            padding: var(--space-md) var(--space-md) var(--space-xl) var(--space-md);
            max-width: 480px;
            margin: 0 auto;
            min-height: calc(100vh - 80px);
        }}
        @media (min-width: 768px) {{
            .block-container {{
                max-width: 900px;
                padding: var(--space-lg) var(--space-xl) var(--space-xl) var(--space-xl);
            }}
        }}
        @media (max-width: 480px) {{
            .block-container {{
                padding: var(--space-sm) var(--space-sm) var(--space-xl) var(--space-sm);
                max-width: 100%;
            }}
        }}

        /* ── #4 Restyle native Streamlit widgets globally ── */
        /* Text inputs */
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {{
            font-family: var(--font-body) !important;
            border-radius: var(--radius-sm) !important;
            border: 1.5px solid #E0E0E0 !important;
            padding: var(--space-sm) var(--space-md) !important;
            transition: border-color 0.2s, box-shadow 0.2s;
        }}
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {{
            border-color: var(--color-orange) !important;
            box-shadow: 0 0 0 3px rgba(255,109,0,0.15) !important;
        }}
        /* Select boxes */
        [data-testid="stSelectbox"] div[data-baseweb="select"] {{
            border-radius: var(--radius-sm) !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {{
            border-radius: var(--radius-sm) !important;
            border: 1.5px solid #E0E0E0 !important;
        }}
        [data-testid="stSelectbox"] [data-baseweb="select"]:hover > div {{
            border-color: var(--color-orange) !important;
        }}
        /* Number inputs */
        [data-testid="stNumberInput"] input {{
            border-radius: var(--radius-sm) !important;
            border: 1.5px solid #E0E0E0 !important;
            font-family: var(--font-body) !important;
        }}
        [data-testid="stNumberInput"] input:focus {{
            border-color: var(--color-orange) !important;
            box-shadow: 0 0 0 3px rgba(255,109,0,0.15) !important;
        }}
        /* File uploader */
        [data-testid="stFileUploader"] > section {{
            border-radius: var(--radius-sm) !important;
            border: 2px dashed #E0E0E0 !important;
            background: {WHITE} !important;
            transition: border-color 0.2s;
        }}
        [data-testid="stFileUploader"] > section:hover {{
            border-color: var(--color-orange) !important;
        }}
        /* Toggle */
        [data-testid="stToggleSwitch"] label {{
            font-family: var(--font-body) !important;
        }}
        [data-testid="stToggleSwitch"] button {{
            border-radius: var(--radius-pill) !important;
        }}
        [data-testid="stToggleSwitch"] button[kind="header"] {{
            background-color: var(--color-orange) !important;
        }}
        /* Chat messages */
        [data-testid="stChatMessage"] {{
            border-radius: var(--radius-sm) !important;
        }}
        /* Forms */
        [data-testid="stForm"] {{
            border: none !important;
            border-radius: var(--radius) !important;
            background: {WHITE} !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
            padding: var(--space-lg) !important;
        }}
        /* Time input */
        [data-testid="stTimeInput"] input {{
            border-radius: var(--radius-sm) !important;
            border: 1.5px solid #E0E0E0 !important;
            font-family: var(--font-body) !important;
        }}
        /* Progress bar */
        [data-testid="stProgress"] > div > div {{
            background: linear-gradient(90deg, var(--color-teal), var(--color-orange)) !important;
            border-radius: var(--radius-pill) !important;
        }}
        /* Info/success/error boxes */
        [data-testid="stAlert"] {{
            border-radius: var(--radius-sm) !important;
            font-family: var(--font-body) !important;
        }}
        /* Expander */
        .streamlit-expanderHeader {{
            border-radius: var(--radius-sm) !important;
            font-family: var(--font-body) !important;
        }}

        /* ── Cards (using spacing tokens) ── */
        .card {{
            background: var(--color-white);
            border-radius: var(--radius);
            padding: var(--space-lg);
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            margin-bottom: var(--space-md);
            border: none;
        }}
        .card-teal {{
            background: linear-gradient(135deg, var(--color-teal), var(--color-teal-dark));
            color: white;
            border-radius: var(--radius);
            padding: var(--space-lg);
            box-shadow: 0 2px 12px rgba(0,128,128,0.25);
            margin-bottom: var(--space-md);
        }}
        .card-orange {{
            background: linear-gradient(135deg, var(--color-orange), var(--color-orange-bg));
            color: white;
            border-radius: var(--radius);
            padding: var(--space-lg);
            box-shadow: 0 2px 12px rgba(255,109,0,0.25);
            margin-bottom: var(--space-md);
        }}
        .card-green {{
            background: linear-gradient(135deg, var(--color-green), #1B5E20);
            color: white;
            border-radius: var(--radius);
            padding: var(--space-lg);
            box-shadow: 0 2px 12px rgba(46,125,50,0.25);
            margin-bottom: var(--space-md);
        }}

        /* ── Stats ── */
        .stat-number {{
            font-size: var(--space-xl);
            font-weight: 800;
            line-height: 1.2;
            margin: 0;
        }}
        .stat-label {{
            font-size: 0.85rem;
            opacity: 0.9;
            margin: 0;
        }}

        /* ── Badges ── */
        .badge {{
            display: inline-block;
            padding: var(--space-xs) var(--space-sm);
            border-radius: var(--radius-pill);
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-baru {{ background: #E3F2FD; color: #1565C0; }}
        .badge-diproses {{ background: #FFF3E0; color: #E65100; }}
        .badge-selesai {{ background: #E8F5E9; color: #2E7D32; }}
        .badge-dibatalkan {{ background: #FFEBEE; color: #C62828; }}

        /* ── Buttons (using spacing tokens) ── */
        .stButton > button {{
            border-radius: var(--radius-pill);
            font-weight: 600;
            font-size: 0.95rem;
            padding: var(--space-sm) var(--space-lg);
            border: none;
            width: 100%;
            font-family: var(--font-body) !important;
            transition: transform 0.15s, box-shadow 0.15s;
        }}
        .stButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }}
        .stButton > button[kind="primary"] {{
            background: var(--color-orange);
            color: white;
        }}
        .stButton > button[kind="secondary"] {{
            background: var(--color-teal);
            color: white;
        }}

        /* ── Product cards (using spacing tokens) ── */
        .product-card {{
            background: white;
            border-radius: var(--radius);
            padding: 0;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            margin-bottom: var(--space-md);
            transition: transform 0.2s;
        }}
        .product-card:hover {{
            transform: translateY(-2px);
        }}
        .product-image {{
            width: 100%;
            height: 160px;
            object-fit: cover;
            background: var(--color-teal-light);
        }}
        .product-info {{
            padding: var(--space-sm) var(--space-md);
        }}
        .product-name {{
            font-weight: 700;
            font-size: 1rem;
            margin: 0 0 var(--space-xs) 0;
        }}
        .product-price {{
            font-weight: 700;
            color: var(--color-orange);
            font-size: 1.1rem;
            margin: 0 0 var(--space-xs) 0;
        }}
        .product-desc {{
            font-size: 0.8rem;
            color: var(--color-gray-text);
            margin: 0;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}

        /* ── Wizard (using spacing tokens) ── */
        .wizard-step {{
            background: white;
            border-radius: var(--radius);
            padding: var(--space-xl);
            text-align: center;
        }}
        .wizard-icon {{
            font-size: 3rem;
            margin-bottom: var(--space-md);
        }}

        /* ── Welcome header (using spacing tokens) ── */
        .welcome-header {{
            text-align: center;
            padding: var(--space-md) 0;
        }}
        .welcome-title {{
            font-size: 1.5rem;
            font-weight: 800;
            margin-bottom: var(--space-xs);
        }}
        .welcome-subtitle {{
            color: var(--color-gray-text);
            font-size: 0.9rem;
        }}

        /* ── #5 Bottom navigation — real mobile nav bar via styled st.buttons ── */
        /* The 5 nav buttons are rendered in st.columns at the bottom.
           We style them as a fixed bottom-nav bar with icon + label. */

        /* Target the bottom block container that holds the nav buttons */
        div[data-testid="stBottomBlockContainer"] {{
            position: fixed !important;
            bottom: 0 !important;
            left: 0 !important;
            right: 0 !important;
            z-index: 999 !important;
            background: white !important;
            border-top: 1px solid #E0E0E0 !important;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.06) !important;
            padding: var(--space-xs) var(--space-sm) !important;
            padding-bottom: max(var(--space-xs), env(safe-area-inset-bottom)) !important;
            max-width: 100% !important;
            margin: 0 !important;
        }}
        @media (min-width: 768px) {{
            div[data-testid="stBottomBlockContainer"] {{
                max-width: 900px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
            }}
        }}

        /* Style each nav button as a nav item */
        div[data-testid="stBottomBlockContainer"] .stButton > button {{
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.1rem !important;
            padding: var(--space-xs) 0 !important;
            border-radius: var(--radius-sm) !important;
            font-size: 1.3rem !important;
            line-height: 1 !important;
            min-height: 48px !important;
            background: transparent !important;
            color: var(--color-gray-text) !important;
            box-shadow: none !important;
            border: none !important;
            transition: color 0.2s, background 0.2s !important;
        }}
        div[data-testid="stBottomBlockContainer"] .stButton > button:hover {{
            background: var(--color-gray-bg) !important;
            color: var(--color-orange) !important;
            transform: none !important;
            box-shadow: none !important;
        }}
        /* Active (primary) button — orange */
        div[data-testid="stBottomBlockContainer"] .stButton > button[kind="primary"] {{
            background: transparent !important;
            color: var(--color-orange) !important;
            font-weight: 700 !important;
        }}

        /* Add label text below each icon via ::after pseudo-element.
           Buttons are in order: Beranda, Pesanan, Katalog, Auto-Balas, Panduan */
        div[data-testid="stBottomBlockContainer"] .stButton:nth-of-type(1) > button::after {{ content: "Beranda"; }}
        div[data-testid="stBottomBlockContainer"] .stButton:nth-of-type(2) > button::after {{ content: "Pesanan"; }}
        div[data-testid="stBottomBlockContainer"] .stButton:nth-of-type(3) > button::after {{ content: "Katalog"; }}
        div[data-testid="stBottomBlockContainer"] .stButton:nth-of-type(4) > button::after {{ content: "Auto-Balas"; }}
        div[data-testid="stBottomBlockContainer"] .stButton:nth-of-type(5) > button::after {{ content: "Panduan"; }}

        div[data-testid="stBottomBlockContainer"] .stButton > button::after {{
            font-size: 0.65rem !important;
            font-family: var(--font-body) !important;
            line-height: 1.2 !important;
            display: block !important;
        }}

        /* Remove the old footer-nav styles (no longer used as HTML nav) */
        .footer-nav {{
            display: none !important;
        }}

        /* ── Toggle switches — bigger, brand-colored ── */
        .stCheckbox {{
            transform: scale(1.3);
        }}

        /* ── Selectbox spacing ── */
        .row-widget.stSelectbox > div {{
            margin-bottom: var(--space-xs);
        }}

        /* ── Success message (using spacing tokens) ── */
        .success-msg {{
            background: #E8F5E9;
            color: var(--color-green);
            padding: var(--space-md);
            border-radius: var(--radius-sm);
            text-align: center;
            font-weight: 600;
        }}

        /* ── Bottom padding so content isn't hidden behind nav ── */
        .stApp {{
            padding-bottom: 80px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# HELPER
# ---------------------------------------------------------------------------

def fmt_rp(amount: float) -> str:
    """Format angka ke Rupiah. Contoh: Rp 50.000"""
    if amount is None:
        amount = 0
    return f"Rp {amount:,.0f}".replace(",", ".")


def get_api_client() -> WakuAPIClient:
    """Dapatkan instance API client — pakai backend URL + JWT dari session state."""
    url = st.session_state.get("backend_url", "")
    if not url:
        from api_client import DEFAULT_BACKEND_URL
        url = DEFAULT_BACKEND_URL
    return WakuAPIClient(url, token=st.session_state.get("token"))


def show_error(err: WakuAPIError):
    """Tampilkan pesan error yang ramah."""
    st.error(f"😅 {err.message}")
    if err.detail:
        with st.expander("Detail teknis"):
            st.caption(err.detail)


def show_success(msg: str):
    """Tampilkan pesan sukses."""
    st.markdown(f'<div class="success-msg">✅ {msg}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# NAVIGASI — Sidebar (simulasi bottom nav)
# ---------------------------------------------------------------------------

PAGES = {
    "Beranda": {"icon": "🏠", "page": "home"},
    "Pesanan": {"icon": "📋", "page": "orders"},
    "Katalog": {"icon": "🏪", "page": "catalog"},
    "Auto-Balas": {"icon": "⚙️", "page": "settings"},
    "Panduan": {"icon": "🚀", "page": "onboarding"},
}


def render_bottom_nav():
    """Render navigasi bawah (mobile-style) — icon above label, proper flexbox nav."""
    current = st.session_state.get("page", "home")
    cols = st.columns(5)
    for i, (label, info) in enumerate(PAGES.items()):
        with cols[i]:
            active = info["page"] == current
            icon = info["icon"]
            # Button with icon only; label added via CSS ::after
            click = st.button(
                icon,
                key=f"nav_{info['page']}",
                help=label,
                use_container_width=True,
                type="primary" if active else "secondary",
            )
            if click:
                st.session_state["page"] = info["page"]
                st.rerun()


# ---------------------------------------------------------------------------
# PAGE 1: BERANDA — Dashboard Home
# ---------------------------------------------------------------------------

def page_home():
    """Halaman utama — ringkasan harian."""
    st.markdown(
        '<div class="welcome-header">'
        '<div class="welcome-title">Selamat Datang di Waku 🤖</div>'
        '<div class="welcome-subtitle">Asisten WhatsApp pintar untuk usaha Anda</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Sapa berdasarkan waktu
    now = datetime.now()
    jam = now.hour
    if jam < 11:
        sapaan = "☀️ Selamat Pagi"
    elif jam < 15:
        sapaan = "🌤️ Selamat Siang"
    elif jam < 18:
        sapaan = "🌅 Selamat Sore"
    else:
        sapaan = "🌙 Selamat Malam"

    st.markdown(f"### {sapaan}")

    # Ambil data
    try:
        api = get_api_client()
        summary = api.get_summary()
    except WakuAPIError as e:
        show_error(e)
        # Gunakan data kosong
        summary = {
            "orders_today": 0,
            "revenue_today": 0,
            "messages_handled": 0,
            "top_products": [],
            "pending_orders": 0,
        }

    # Cards — 2 baris, 2 kolom
    row1 = st.columns(2)
    with row1[0]:
        st.markdown(
            f'<div class="card-teal">'
            f'<p class="stat-number">{summary["orders_today"]}</p>'
            f'<p class="stat-label">📦 Pesanan Hari Ini</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with row1[1]:
        st.markdown(
            f'<div class="card-orange">'
            f'<p class="stat-number">{fmt_rp(summary["revenue_today"])}</p>'
            f'<p class="stat-label">💰 Pendapatan Hari Ini</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    row2 = st.columns(2)
    with row2[0]:
        st.markdown(
            f'<div class="card-green">'
            f'<p class="stat-number">{summary["messages_handled"]}</p>'
            f'<p class="stat-label">💬 Pesan Dibalas Otomatis</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with row2[1]:
        pending = summary.get("pending_orders", 0)
        if pending > 0:
            bg = RED
        else:
            bg = TEAL
        st.markdown(
            f'<div class="card" style="background:{bg};color:white;">'
            f'<p class="stat-number">{pending}</p>'
            f'<p class="stat-label">⏳ Pesanan Menunggu</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Produk terlaris
    st.markdown("### 🏆 Produk Terlaris Hari Ini")
    top = summary.get("top_products", [])
    if top:
        for prod in top[:5]:
            nama = prod.get("name", prod.get("nama", "-"))
            terjual = prod.get("count", prod.get("terjual", 0))
            st.markdown(
                f'<div class="card" style="display:flex;justify-content:space-between;">'
                f'<span><strong>{nama}</strong></span>'
                f'<span class="badge badge-selesai">{terjual} terjual</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("Belum ada data penjualan hari ini. Ajak pelanggan Anda berbelanja! 🛍️")

    # Tombol cepat
    st.markdown("### ⚡ Aksi Cepat")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📋 Lihat Pesanan", key="quick_orders", use_container_width=True):
            st.session_state["page"] = "orders"
            st.rerun()
    with col2:
        if st.button("🏪 Atur Katalog", key="quick_catalog", use_container_width=True):
            st.session_state["page"] = "catalog"
            st.rerun()


# ---------------------------------------------------------------------------
# PAGE 2: PESANAN — Orders
# ---------------------------------------------------------------------------

def page_orders():
    """Halaman daftar pesanan dengan filter status."""
    st.markdown("## 📋 Daftar Pesanan")

    # Filter status
    status_filter = st.selectbox(
        "Filter status:",
        options=["semua", "baru", "diproses", "selesai", "dibatalkan"],
        format_func=lambda x: {
            "semua": "Semua Pesanan",
            "baru": "🆕 Baru",
            "diproses": "🔄 Diproses",
            "selesai": "✅ Selesai",
            "dibatalkan": "❌ Dibatalkan",
        }.get(x, x),
        key="order_filter",
    )

    try:
        api = get_api_client()
        orders = api.get_orders(status=None if status_filter == "semua" else status_filter)
    except WakuAPIError as e:
        show_error(e)
        orders = []

    if not orders:
        st.info("Belum ada pesanan. Tenang saja, Waku akan memberitahu Anda jika ada pesanan masuk! 😊")
        return

    for order in orders:
        order_id = order.get("id", order.get("order_id", "-"))
        customer = order.get("customer_name", order.get("nama_pelanggan", "Pelanggan"))
        status = order.get("status", "baru")
        total = order.get("total", order.get("total_harga", 0))
        items = order.get("items", order.get("pesanan", []))
        created = order.get("created_at", order.get("tanggal", ""))

        badge_class = f"badge-{status}"
        status_label = {
            "baru": "🆕 Baru",
            "diproses": "🔄 Diproses",
            "selesai": "✅ Selesai",
            "dibatalkan": "❌ Dibatalkan",
        }.get(status, status)

        st.markdown(
            f'<div class="card">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<strong>{customer}</strong>'
            f'<span class="badge {badge_class}">{status_label}</span>'
            f'</div>'
            f'<p style="font-size:0.85rem;color:{GRAY_TEXT};margin:0.3rem 0;">'
            f'Pesanan #{order_id[:8]} • {created}</p>'
            f'<p style="font-weight:700;color:{ORANGE};margin:0.3rem 0;">{fmt_rp(total)}</p>',
            unsafe_allow_html=True,
        )

        if items and isinstance(items, list):
            for item in items:
                qty = item.get("qty", item.get("quantity", 1))
                name = item.get("name", item.get("nama_produk", "Produk"))
                price = item.get("price", item.get("harga", 0))
                st.markdown(
                    f'<p style="font-size:0.8rem;margin:0 0 0 1rem;">• {name} x{qty} — {fmt_rp(price)}</p>',
                    unsafe_allow_html=True,
                )

        # Tombol aksi
        if status in ("baru", "diproses"):
            col1, col2 = st.columns(2)
            with col1:
                if status == "baru":
                    if st.button("🔄 Proses", key=f"process_{order_id}"):
                        try:
                            api.update_order_status(order_id, "diproses")
                            show_success("Pesanan sedang diproses!")
                            st.rerun()
                        except WakuAPIError as e:
                            show_error(e)
            with col2:
                if status in ("baru", "diproses"):
                    if st.button("✅ Selesaikan", key=f"done_{order_id}"):
                        try:
                            api.update_order_status(order_id, "selesai")
                            show_success("Pesanan selesai! 🎉")
                            st.rerun()
                        except WakuAPIError as e:
                            show_error(e)

        # Tombol batalkan (opsional)
        if status in ("baru", "diproses"):
            if st.button("❌ Batalkan", key=f"cancel_{order_id}"):
                try:
                    api.update_order_status(order_id, "dibatalkan")
                    show_success("Pesanan dibatalkan.")
                    st.rerun()
                except WakuAPIError as e:
                    show_error(e)

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# PAGE 3: KATALOG — Product Catalog CRUD
# ---------------------------------------------------------------------------

def page_catalog():
    """Halaman katalog produk — CRUD dengan tampilan grid."""
    st.markdown("## 🏪 Katalog Produk")

    api = get_api_client()

    # Tombol tambah produk
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("➕ Tambah Produk", use_container_width=True):
            st.session_state["show_add_product"] = True

    # Form tambah produk
    if st.session_state.get("show_add_product"):
        with st.form("add_product_form", clear_on_submit=True):
            st.markdown("### Tambah Produk Baru")
            name = st.text_input("Nama Produk *", placeholder="Contoh: Nasi Goreng")
            price = st.number_input("Harga (Rp) *", min_value=0, step=500, value=0)
            desc = st.text_area("Deskripsi", placeholder="Deskripsi singkat produk...", height=80)
            uploaded_img = st.file_uploader(
                "Foto Produk (opsional)", type=["jpg", "jpeg", "png"]
            )
            submitted = st.form_submit_button("💾 Simpan Produk", use_container_width=True)
            if submitted:
                if not name or price <= 0:
                    st.error("Nama produk dan harga harus diisi!")
                else:
                    try:
                        image_url = ""
                        if uploaded_img is not None:
                            img_bytes = uploaded_img.read()
                            image_url = api.upload_image(img_bytes, uploaded_img.name)
                        api.create_product(name=name, price=price, description=desc, image_url=image_url)
                        show_success(f"Produk {name} berhasil ditambahkan! 🎉")
                        st.session_state["show_add_product"] = False
                        st.rerun()
                    except WakuAPIError as e:
                        show_error(e)

    # Ambil daftar produk
    try:
        products = api.get_products()
    except WakuAPIError as e:
        show_error(e)
        products = []

    if not products:
        st.info("Belum ada produk. Yuk, tambahkan produk pertama Anda! 🏪")
        return

    # Tampilkan grid produk (2 kolom)
    cols = st.columns(2)
    for idx, prod in enumerate(products):
        prod_id = prod.get("id", prod.get("product_id", ""))
        name = prod.get("name", prod.get("nama", "Produk"))
        price = prod.get("price", prod.get("harga", 0))
        desc = prod.get("description", prod.get("deskripsi", ""))
        img_url = prod.get("image_url", prod.get("gambar", ""))

        with cols[idx % 2]:
            # Image placeholder or actual image
            if img_url:
                img_html = f'<img class="product-image" src="{img_url}" alt="{name}">'
            else:
                img_html = (
                    f'<div class="product-image" style="display:flex;align-items:center;'
                    f'justify-content:center;background:{TEAL_LIGHT};color:{TEAL};'
                    f'font-size:3rem;">📦</div>'
                )

            # Update/Delete keys
            edit_key = f"edit_{prod_id}"
            delete_key = f"del_{prod_id}"

            st.markdown(
                f'<div class="product-card">'
                f'{img_html}'
                f'<div class="product-info">'
                f'<p class="product-name">{name}</p>'
                f'<p class="product-price">{fmt_rp(price)}</p>'
                f'<p class="product-desc">{desc or "—"}</p>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            col_e, col_d = st.columns(2)
            with col_e:
                if st.button("✏️ Edit", key=edit_key, use_container_width=True):
                    st.session_state[f"editing_{prod_id}"] = True
            with col_d:
                if st.button("🗑️ Hapus", key=delete_key, use_container_width=True):
                    try:
                        api.delete_product(prod_id)
                        show_success(f"{name} berhasil dihapus.")
                        st.rerun()
                    except WakuAPIError as e:
                        show_error(e)

            # Inline edit form
            if st.session_state.get(f"editing_{prod_id}"):
                with st.form(key=f"edit_form_{prod_id}"):
                    new_name = st.text_input("Nama", value=name)
                    new_price = st.number_input("Harga (Rp)", min_value=0, step=500, value=int(price))
                    new_desc = st.text_area("Deskripsi", value=desc, height=60)
                    new_img = st.file_uploader(
                        "Ganti Foto", type=["jpg", "jpeg", "png"],
                        key=f"img_{prod_id}",
                    )
                    col_s, col_c = st.columns(2)
                    with col_s:
                        save_edit = st.form_submit_button("💾 Simpan", use_container_width=True)
                    with col_c:
                        cancel_edit = st.form_submit_button("❌ Batal", use_container_width=True)
                    if save_edit:
                        try:
                            img_url_new = img_url
                            if new_img is not None:
                                img_bytes = new_img.read()
                                img_url_new = api.upload_image(img_bytes, new_img.name)
                            api.update_product(
                                product_id=prod_id,
                                name=new_name,
                                price=new_price,
                                description=new_desc,
                                image_url=img_url_new,
                            )
                            show_success(f"{new_name} berhasil diupdate!")
                            st.session_state[f"editing_{prod_id}"] = False
                            st.rerun()
                        except WakuAPIError as e:
                            show_error(e)
                    if cancel_edit:
                        st.session_state[f"editing_{prod_id}"] = False
                        st.rerun()


# ---------------------------------------------------------------------------
# PAGE 4: AUTO-REPLY SETTINGS
# ---------------------------------------------------------------------------

def page_settings():
    """Halaman pengaturan auto-reply."""
    st.markdown("## ⚙️ Pengaturan Auto-Balas")
    st.caption("Atur cara Waku membalas pesan pelanggan otomatis.")

    api = get_api_client()

    # ── Profil bisnis (ganti nama) ──
    with st.expander("🏪 Profil Bisnis", expanded=False):
        new_name = st.text_input(
            "Nama Bisnis",
            value=st.session_state.get("business_name", "") or "",
            key="biz_name_edit",
        )
        if st.button("💾 Simpan Nama", key="save_biz_name", use_container_width=True):
            if new_name.strip():
                try:
                    data = api.update_business(new_name.strip())
                    st.session_state["business_name"] = data.get("business_name", new_name.strip())
                    show_success("Nama bisnis diperbarui!")
                    st.rerun()
                except WakuAPIError as e:
                    show_error(e)
            else:
                st.error("Nama bisnis tidak boleh kosong.")

    # Ambil pengaturan
    try:
        settings = api.get_settings()
    except WakuAPIError as e:
        show_error(e)
        settings = {}

    # Form pengaturan
    with st.form("settings_form"):
        # Toggle aktif/nonaktif
        enabled = st.toggle(
            "🤖 Aktifkan Auto-Balas",
            value=settings.get("auto_reply_enabled", True),
            help="Matikan jika ingin menjawab pelanggan secara manual.",
        )

        st.markdown("---")

        # Sambutan
        greeting = st.text_area(
            "💬 Pesan Sambutan",
            value=settings.get("greeting_message", ""),
            placeholder="Halo! Ada yang bisa Waku bantu?",
            help="Pesan yang dikirim saat pelanggan pertama kali chat.",
            height=80,
        )

        # Jam operasional
        st.markdown("### 🕐 Jam Operasional")
        col1, col2 = st.columns(2)
        with col1:
            open_time = st.time_input(
                "Buka",
                value=datetime.strptime(
                    settings.get("business_hours", {}).get("open", "08:00"), "%H:%M"
                ).time() if settings.get("business_hours", {}).get("open") else datetime.strptime("08:00", "%H:%M").time(),
            )
        with col2:
            close_time = st.time_input(
                "Tutup",
                value=datetime.strptime(
                    settings.get("business_hours", {}).get("close", "21:00"), "%H:%M"
                ).time() if settings.get("business_hours", {}).get("close") else datetime.strptime("21:00", "%H:%M").time(),
            )

        # Pesan di luar jam kerja
        after_hours_msg = st.text_input(
            "🌙 Pesan di Luar Jam Kerja",
            value=settings.get("after_hours_message", ""),
            placeholder="Maaf, saat ini di luar jam operasional...",
        )

        st.markdown("---")

        # FAQ
        st.markdown("### ❓ Pertanyaan Umum (FAQ)")
        faqs = settings.get("faq", [])
        if not faqs:
            faqs = [{"question": "", "answer": ""}]

        faq_container = []
        for i, faq in enumerate(faqs):
            st.markdown(f"**FAQ #{i+1}**")
            q = st.text_input(
                "Pertanyaan",
                value=faq.get("question", ""),
                key=f"faq_q_{i}",
                placeholder="Contoh: Berapa harga...",
            )
            a = st.text_area(
                "Jawaban",
                value=faq.get("answer", ""),
                key=f"faq_a_{i}",
                placeholder="Contoh: Harganya Rp...",
                height=60,
            )
            faq_container.append({"question": q, "answer": a})

        # Tombol tambah FAQ
        add_faq = st.form_submit_button("➕ Tambah FAQ", use_container_width=True)
        if add_faq:
            # We need to handle this — form submission, just add to session
            st.session_state["faq_count"] = st.session_state.get("faq_count", 1) + 1

        st.markdown("---")

        submitted = st.form_submit_button(
            "💾 Simpan Pengaturan", use_container_width=True, type="primary"
        )
        if submitted:
            payload = {
                "auto_reply_enabled": enabled,
                "greeting_message": greeting,
                "after_hours_message": after_hours_msg,
                "business_hours": {
                    "open": open_time.strftime("%H:%M"),
                    "close": close_time.strftime("%H:%M"),
                },
                "faq": [f for f in faq_container if f["question"] and f["answer"]],
            }
            try:
                api.update_settings(payload)
                show_success("Pengaturan berhasil disimpan! ✅")
            except WakuAPIError as e:
                show_error(e)

    # Preview section
    st.markdown("---")
    st.markdown("### 👁️ Pratinjau Balasan")
    preview_container = st.container()
    with preview_container:
        with st.chat_message("assistant"):
            if greeting:
                st.write(greeting)
            else:
                st.write("Halo! Ada yang bisa Waku bantu? 😊")


# ---------------------------------------------------------------------------
# PAGE 5: ONBOARDING WIZARD
# ---------------------------------------------------------------------------

def page_onboarding():
    """Halaman panduan awal — wizard setup bisnis."""
    st.markdown("## 🚀 Panduan Awal Waku")
    st.caption("Ikuti langkah-langkah berikut untuk mulai menggunakan Waku.")

    # Step tracker
    steps = [
        ("Nama Bisnis", "🏪"),
        ("Nomor WhatsApp", "📱"),
        ("Katalog Produk", "🏪"),
        ("Selesai!", "🎉"),
    ]

    current_step = st.session_state.get("wizard_step", 1)

    # Visual progress
    progress_val = current_step / len(steps)
    st.progress(progress_val)
    st.markdown(
        f'<p style="text-align:center;color:{GRAY_TEXT};">Langkah {current_step} dari {len(steps)}</p>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # --- STEP 1: Nama Bisnis ---
    if current_step == 1:
        st.markdown(
            '<div class="wizard-step">'
            '<div class="wizard-icon">🏪</div>'
            '<h3>Apa Nama Bisnis Anda?</h3>'
            '<p style="color:gray;">Masukkan nama toko/warung/usaha Anda.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        biz_name = st.text_input(
            "Nama Bisnis",
            value=st.session_state.get("biz_name", ""),
            placeholder="Contoh: Warung Makmur",
            key="wizard_biz_name",
        )
        st.caption("Nama ini akan muncul di pesan balasan otomatis ke pelanggan.")
        if st.button("▶️ Lanjut", use_container_width=True, type="primary"):
            if biz_name.strip():
                st.session_state["biz_name"] = biz_name.strip()
                st.session_state["wizard_step"] = 2
                st.rerun()
            else:
                st.error("Silakan masukkan nama bisnis Anda.")

    # --- STEP 2: Nomor WhatsApp ---
    elif current_step == 2:
        st.markdown(
            '<div class="wizard-step">'
            '<div class="wizard-icon">📱</div>'
            '<h3>Nomor WhatsApp Bisnis</h3>'
            '<p style="color:gray;">Masukkan nomor WhatsApp yang akan dihubungkan dengan Waku.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        phone = st.text_input(
            "Nomor WhatsApp",
            value=st.session_state.get("biz_phone", ""),
            placeholder="Contoh: 08123456789",
            key="wizard_phone",
            max_chars=15,
        )
        st.caption("Nomor ini akan digunakan Waku untuk menerima dan membalas pesan pelanggan.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Kembali", use_container_width=True):
                st.session_state["wizard_step"] = 1
                st.rerun()
        with col2:
            if st.button("▶️ Lanjut", use_container_width=True, type="primary"):
                if phone.strip():
                    st.session_state["biz_phone"] = phone.strip()
                    st.session_state["wizard_step"] = 3
                    st.rerun()
                else:
                    st.error("Silakan masukkan nomor WhatsApp Anda.")

    # --- STEP 3: Tambah Produk ---
    elif current_step == 3:
        st.markdown(
            '<div class="wizard-step">'
            '<div class="wizard-icon">🏪</div>'
            '<h3>Tambah Produk Pertama</h3>'
            '<p style="color:gray;">Tambahkan minimal satu produk agar Waku bisa mulai membantu pelanggan.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        api = get_api_client()

        # Cek apakah sudah ada produk
        try:
            existing_products = api.get_products()
        except WakuAPIError:
            existing_products = []

        if existing_products:
            st.success(f"✅ {len(existing_products)} produk sudah ada di katalog!")
            for p in existing_products[:3]:
                pname = p.get("name", p.get("nama", "-"))
                pprice = p.get("price", p.get("harga", 0))
                st.markdown(f"- {pname} — {fmt_rp(pprice)}")
        else:
            st.info("Belum ada produk. Tambahkan produk pertama Anda!")

        with st.form("wizard_product_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                p_name = st.text_input("Nama Produk", placeholder="Contoh: Es Teh Manis")
            with col2:
                p_price = st.number_input("Harga (Rp)", min_value=0, step=500, value=5000)
            p_desc = st.text_area("Deskripsi (opsional)", placeholder="Deskripsi singkat...", height=60)
            p_img = st.file_uploader("Foto (opsional)", type=["jpg", "jpeg", "png"], key="wizard_img")
            added = st.form_submit_button("➕ Tambah Produk Ini", use_container_width=True)
            if added:
                if p_name and p_price > 0:
                    try:
                        img_url = ""
                        if p_img is not None:
                            img_bytes = p_img.read()
                            img_url = api.upload_image(img_bytes, p_img.name)
                        api.create_product(name=p_name, price=p_price, description=p_desc, image_url=img_url)
                        show_success(f"{p_name} berhasil ditambahkan! 🎉")
                        st.rerun()
                    except WakuAPIError as e:
                        show_error(e)
                else:
                    st.error("Nama dan harga produk harus diisi!")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Kembali", use_container_width=True):
                st.session_state["wizard_step"] = 2
                st.rerun()
        with col2:
            if st.button("▶️ Lanjut — Selesai!", use_container_width=True, type="primary"):
                st.session_state["wizard_step"] = 4
                st.rerun()

    # --- STEP 4: SELESAI ---
    elif current_step == 4:
        st.markdown(
            '<div class="wizard-step">'
            '<div class="wizard-icon">🎉</div>'
            '<h3>Selamat! Bisnis Anda Siap!</h3>'
            '<p style="color:gray;">Waku sekarang siap membantu pelanggan Anda.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Bisnis sudah dibuat saat pendaftaran akun — wizard ini hanya panduan.
        biz_name = st.session_state.get("business_name") or st.session_state.get("biz_name", "Bisnis Saya")
        st.success(f"✅ **{biz_name}** siap digunakan!")
        st.caption("Langkah penting berikutnya: hubungkan nomor WhatsApp lewat panel **📲 Koneksi WhatsApp** di atas.")

        st.markdown(
            """
            ### 📋 Checklist Selanjutnya

            ✅ **Nama bisnis** — Terdaftar  
            ✅ **Nomor WhatsApp** — Siap digunakan  
            ✅ **Katalog produk** — Siap melayani pelanggan  

            ### 💡 Tips Memulai

            1. 📱 Bagikan nomor WhatsApp Waku ke pelanggan Anda
            2. ⚙️ Atur **Auto-Balas** di menu Pengaturan
            3. 📋 Pantau **Pesanan** yang masuk setiap hari
            4. 🏪 Update **Katalog** produk secara berkala
            """
        )

        if st.button("🏠 Kembali ke Beranda", use_container_width=True, type="primary"):
            st.session_state["wizard_step"] = 1
            st.session_state["page"] = "home"
            st.rerun()


# ---------------------------------------------------------------------------
# SETTINGS SIDEBAR (Backend URL)
# ---------------------------------------------------------------------------

def render_sidebar():
    """Sidebar untuk pengaturan backend URL."""
    with st.sidebar:
        st.markdown("### ⚙️ Pengaturan")
        st.markdown("---")

        # Backend URL
        current_url = st.session_state.get("backend_url", "")
        new_url = st.text_input(
            "URL Backend Waku",
            value=current_url or "http://localhost:8000",
            help="Alamat server backend Waku. Ubah jika backend berjalan di port/server lain.",
            key="sidebar_url_input",
        )
        if new_url != current_url:
            st.session_state["backend_url"] = new_url
            st.rerun()

        st.markdown("---")
        biz_name = st.session_state.get("business_name")
        if biz_name:
            st.caption(f"🏪 {biz_name}")
        if st.button("🚪 Keluar", use_container_width=True):
            for k in ("token", "business_name", "otp_instructions", "otp_phone_saved", "otp_code", "otp_platform"):
                st.session_state.pop(k, None)
            st.rerun()

        st.markdown("---")
        st.caption("Waku v1.0 — 🤖 Asisten WhatsApp UMKM")
        st.caption("Made with ❤️ untuk pengusaha Indonesia")


# ---------------------------------------------------------------------------
# AUTH GATE — login / daftar / OTP WhatsApp
# ---------------------------------------------------------------------------

def render_auth():
    """Layar masuk sebelum dashboard. Email+password (utama) atau reverse-OTP WhatsApp."""
    st.markdown(
        '<div class="welcome-header">'
        '<div class="welcome-title">Waku 🤖</div>'
        '<div class="welcome-subtitle">Masuk untuk mengelola asisten WhatsApp Anda</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    tab_login, tab_register, tab_otp = st.tabs(["🔑 Masuk", "✨ Daftar", "💬 OTP WhatsApp"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Masuk", type="primary", use_container_width=True):
                try:
                    data = get_api_client().login(email, password)
                    st.session_state["token"] = data["access_token"]
                    st.session_state["business_name"] = data.get("business_name")
                    st.rerun()
                except WakuAPIError as e:
                    show_error(e)

    with tab_register:
        with st.form("register_form"):
            biz = st.text_input("Nama Bisnis", placeholder="Contoh: Warung Makmur")
            phone = st.text_input("Nomor WhatsApp", placeholder="Contoh: 081234567890")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password (min. 6 karakter)", type="password", key="reg_pass")
            if st.form_submit_button("Daftar", type="primary", use_container_width=True):
                if not all([biz, phone, email, password]):
                    st.error("Semua kolom wajib diisi.")
                else:
                    try:
                        data = get_api_client().register(email, password, biz, phone)
                        st.session_state["token"] = data["access_token"]
                        st.session_state["business_name"] = data.get("business_name")
                        st.rerun()
                    except WakuAPIError as e:
                        show_error(e)

    with tab_otp:
        st.caption("Login lewat WhatsApp (gratis). Minta kode, kirim dari WA Anda ke nomor Waku, lalu verifikasi.")
        otp_phone = st.text_input("Nomor WhatsApp Anda", key="otp_phone_input", placeholder="081234567890")
        if st.button("1) Minta Kode", use_container_width=True):
            try:
                data = get_api_client().otp_request(otp_phone, "login")
                st.session_state["otp_phone_saved"] = otp_phone
                st.session_state["otp_code"] = data["code"]
                st.session_state["otp_instructions"] = data["instructions"]
                st.session_state["otp_platform"] = data.get("platform_number")
                st.rerun()
            except WakuAPIError as e:
                show_error(e)
        if st.session_state.get("otp_instructions"):
            plat = st.session_state.get("otp_platform")
            code = st.session_state.get("otp_code", "")
            if plat:
                st.markdown("**Kirim kode ini:**")
                st.code(code, language=None)
                st.markdown("**Ke nomor WhatsApp Waku ini:**")
                st.code(plat, language=None)
            st.info(st.session_state["otp_instructions"])
            if st.button("2) Saya Sudah Kirim — Verifikasi", type="primary", use_container_width=True):
                try:
                    data = get_api_client().otp_verify(
                        st.session_state.get("otp_phone_saved", ""),
                        st.session_state.get("otp_code", ""),
                    )
                    st.session_state["token"] = data["access_token"]
                    st.session_state["business_name"] = data.get("business_name")
                    st.session_state.pop("otp_instructions", None)
                    st.session_state.pop("otp_code", None)
                    st.session_state.pop("otp_platform", None)
                    st.rerun()
                except WakuAPIError as e:
                    show_error(e)


def render_whatsapp_panel():
    """Panel status koneksi WhatsApp + form connect manual (sebelum Embedded Signup aktif)."""
    with st.expander("📲 Koneksi WhatsApp", expanded=False):
        try:
            status = get_api_client().whatsapp_status()
        except WakuAPIError as e:
            show_error(e)
            return

        if status.get("is_connected"):
            st.markdown(
                f'<div class="success-msg">✅ Terhubung — phone_number_id: '
                f'{status.get("phone_number_id", "-")}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.warning("Belum terhubung. Nomor WhatsApp bisnis belum bisa membalas pelanggan.")

        st.caption(
            "Nanti via **Embedded Signup** Meta (sekali klik) setelah akun lolos App Review. "
            "Untuk sekarang (test), masukkan kredensial Cloud API manual:"
        )
        with st.form("connect_wa_form"):
            pnid = st.text_input("Phone Number ID", placeholder="dari Meta WhatsApp API Setup")
            token = st.text_input("Access Token", type="password", placeholder="token Cloud API")
            waba = st.text_input("WABA ID (opsional)")
            if st.form_submit_button("🔗 Hubungkan", type="primary", use_container_width=True):
                if not pnid or not token:
                    st.error("Phone Number ID dan Access Token wajib diisi.")
                else:
                    try:
                        get_api_client().connect_whatsapp(pnid, token, waba)
                        show_success("WhatsApp berhasil dihubungkan! 🎉")
                        st.rerun()
                    except WakuAPIError as e:
                        show_error(e)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    """Entry point aplikasi."""
    # Init session state
    if "token" not in st.session_state:
        st.session_state["token"] = None
    if "page" not in st.session_state:
        st.session_state["page"] = "home"
    if "wizard_step" not in st.session_state:
        st.session_state["wizard_step"] = 1
    if "show_add_product" not in st.session_state:
        st.session_state["show_add_product"] = False

    # Inject CSS
    local_css()

    # Auth gate — show login screen until authenticated.
    if not st.session_state.get("token"):
        render_auth()
        return

    # Render sidebar
    render_sidebar()

    # WhatsApp connection panel (always visible at top)
    render_whatsapp_panel()

    # Render page
    page_map = {
        "home": page_home,
        "orders": page_orders,
        "catalog": page_catalog,
        "settings": page_settings,
        "onboarding": page_onboarding,
    }

    current_page = st.session_state["page"]
    page_fn = page_map.get(current_page, page_home)
    page_fn()

    # Bottom navigation
    st.markdown("<br>", unsafe_allow_html=True)
    render_bottom_nav()


if __name__ == "__main__":
    main()
