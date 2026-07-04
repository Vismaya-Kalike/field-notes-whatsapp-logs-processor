from __future__ import annotations

from supabase import Client, create_client


def create_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)
