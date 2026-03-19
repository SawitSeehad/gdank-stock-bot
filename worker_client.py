"""
Worker Client — komunikasi bot ke Cloudflare Worker
"""
import os
import httpx

WORKER_URL = os.getenv("WORKER_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "")

HEADERS = {
    "X-Bot-Secret": BOT_SECRET,
    "Content-Type": "application/json",
}


async def check_user(telegram_id: int) -> dict:
    """Cek status user di D1."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{WORKER_URL}/tg/status/{telegram_id}",
            headers=HEADERS
        )
        return r.json()


async def register_user(telegram_id: int, username: str, full_name: str) -> dict:
    """Daftarkan user baru (belum aktif)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{WORKER_URL}/tg/register",
            headers=HEADERS,
            json={
                "telegram_id": telegram_id,
                "username"   : username,
                "full_name"  : full_name,
            }
        )
        return r.json()


async def activate_stars(telegram_id: int) -> dict:
    """Aktifkan user setelah bayar via Stars."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{WORKER_URL}/tg/activate/stars",
            headers=HEADERS,
            json={"telegram_id": telegram_id}
        )
        return r.json()
