"""
api_client.py — HTTP client for Waku Backend API.

Semua fungsi berkomunikasi dengan backend FastAPI.
Pesan error dalam Bahasa Indonesia untuk pemilik UMKM.
"""

import os
from typing import Optional
from dotenv import load_dotenv
import httpx

load_dotenv()

DEFAULT_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class WakuAPIError(Exception):
    """Error dari API Waku — pesannya sudah siap pakai untuk pengguna."""
    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(self.message)


class WakuAPIClient:
    """Klien HTTP sederhana untuk backend Waku."""

    def __init__(self, base_url: str = DEFAULT_BACKEND_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)

    # ----------------------------------------------------------------
    # Ringkasan Harian
    # ----------------------------------------------------------------
    def get_summary(self) -> dict:
        """Ambil ringkasan harian (pesanan, revenue, pesan, produk teratas)."""
        try:
            resp = self.client.get(f"{self.base_url}/api/dashboard/summary")
            resp.raise_for_status()
            data = resp.json()
            return {
                "orders_today": data.get("orders_today", 0),
                "revenue_today": data.get("revenue_today", 0),
                "messages_handled": data.get("messages_handled", 0),
                "top_products": data.get("top_products", []),
                "pending_orders": data.get("pending_orders", 0),
            }
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengambil ringkasan harian.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    # ----------------------------------------------------------------
    # Pesanan (Orders)
    # ----------------------------------------------------------------
    def get_orders(self, status: Optional[str] = None) -> list:
        """Ambil daftar pesanan, bisa difilter berdasarkan status."""
        params = {}
        if status and status != "semua":
            params["status"] = status
        try:
            resp = self.client.get(
                f"{self.base_url}/api/orders", params=params
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengambil daftar pesanan.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    def update_order_status(self, order_id: str, status: str) -> dict:
        """Ubah status pesanan."""
        try:
            resp = self.client.patch(
                f"{self.base_url}/api/orders/{order_id}",
                json={"status": status},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengupdate status pesanan.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    # ----------------------------------------------------------------
    # Katalog Produk (Catalog)
    # ----------------------------------------------------------------
    def get_products(self) -> list:
        """Ambil semua produk di katalog."""
        try:
            resp = self.client.get(f"{self.base_url}/api/products")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengambil daftar produk.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    def create_product(self, name: str, price: float, description: str = "", image_url: str = "") -> dict:
        """Tambah produk baru ke katalog."""
        try:
            payload = {
                "name": name,
                "price": price,
                "description": description,
            }
            if image_url:
                payload["image_url"] = image_url
            resp = self.client.post(
                f"{self.base_url}/api/products",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal menambahkan produk.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    def update_product(self, product_id: str, name: str, price: float, description: str = "", image_url: str = "") -> dict:
        """Update data produk."""
        payload = {
            "name": name,
            "price": price,
            "description": description,
        }
        if image_url:
            payload["image_url"] = image_url
        try:
            resp = self.client.put(
                f"{self.base_url}/api/products/{product_id}",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengupdate produk.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    def delete_product(self, product_id: str) -> dict:
        """Hapus produk dari katalog."""
        try:
            resp = self.client.delete(
                f"{self.base_url}/api/products/{product_id}"
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal menghapus produk.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    # ----------------------------------------------------------------
    # Pengaturan Auto-Reply
    # ----------------------------------------------------------------
    def get_settings(self) -> dict:
        """Ambil pengaturan auto-reply."""
        try:
            resp = self.client.get(f"{self.base_url}/api/settings")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengambil pengaturan.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    def update_settings(self, settings: dict) -> dict:
        """Simpan pengaturan auto-reply."""
        try:
            resp = self.client.put(
                f"{self.base_url}/api/settings",
                json=settings,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal menyimpan pengaturan.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    # ----------------------------------------------------------------
    # Onboarding / Registrasi Bisnis
    # ----------------------------------------------------------------
    def register_business(self, data: dict) -> dict:
        """Daftarkan bisnis baru."""
        try:
            resp = self.client.post(
                f"{self.base_url}/api/business/register",
                json=data,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mendaftarkan bisnis.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    # ----------------------------------------------------------------
    # Upload Gambar
    # ----------------------------------------------------------------
    def upload_image(self, file_bytes: bytes, filename: str) -> str:
        """Upload gambar produk, return URL."""
        try:
            files = {"file": (filename, file_bytes, "image/jpeg")}
            resp = self.client.post(
                f"{self.base_url}/api/upload",
                files=files,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("url", "")
        except httpx.HTTPStatusError as e:
            raise WakuAPIError(
                "Gagal mengupload gambar.",
                f"Server merespon {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise WakuAPIError(
                "Tidak bisa terhubung ke server Waku.",
                "Periksa apakah backend sudah berjalan.",
            )

    def close(self):
        """Tutup koneksi HTTP client."""
        self.client.close()
