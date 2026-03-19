"""
FastAPI Client — komunikasi bot ke HuggingFace FastAPI
"""
import os
import httpx

FASTAPI_URL = os.getenv("FASTAPI_URL", "")


async def upload_dataset(file_bytes: bytes, filename: str) -> dict:
    """Upload dataset ke FastAPI."""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{FASTAPI_URL}/upload",
            files={"file": (filename, file_bytes)},
        )
        return r.json()


async def train(session_id: str, country_code: str = "ID",
                test_ratio: float = 0.2, n_trials: int = 30) -> dict:
    """Jalankan training."""
    async with httpx.AsyncClient(timeout=300) as client:  # 5 menit timeout
        r = await client.post(
            f"{FASTAPI_URL}/train",
            json={
                "session_id"  : session_id,
                "country_code": country_code,
                "test_ratio"  : test_ratio,
                "n_trials"    : n_trials,
            }
        )
        return r.json()


async def get_products(session_id: str) -> dict:
    """Ambil daftar produk."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{FASTAPI_URL}/products/{session_id}")
        return r.json()


async def forecast(session_id: str, product_id: str = None,
                   skip_n1: bool = True) -> dict:
    """Ambil hasil forecast."""
    params = {"skip_n1": str(skip_n1).lower()}
    if product_id:
        params["product_id"] = product_id

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{FASTAPI_URL}/forecast/{session_id}",
            params=params,
        )
        return r.json()
