from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    s3_bucket_name: str
    openai_api_key: str
    classification_model: str = "gpt-5-mini-2025-08-07"
    commentary_model: str = "gpt-5.4-2026-03-05"
    ai_batch_size: int = 20

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()

        required = {
            "SUPABASE_URL": os.getenv("SUPABASE_URL"),
            "SUPABASE_SECRET_KEY": os.getenv("SUPABASE_SECRET_KEY"),
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        }

        missing = [k for k, v in required.items() if not v]
        if missing:
            print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)

        return cls(
            supabase_url=required["SUPABASE_URL"],
            supabase_secret_key=required["SUPABASE_SECRET_KEY"],
            aws_access_key_id=required["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=required["AWS_SECRET_ACCESS_KEY"],
            aws_region=os.getenv("AWS_REGION", "ap-south-1"),
            s3_bucket_name=required["S3_BUCKET_NAME"],
            openai_api_key=required["OPENAI_API_KEY"],
            classification_model=os.getenv("AI_CLASSIFICATION_MODEL", "gpt-4o-mini"),
            commentary_model=os.getenv("AI_COMMENTARY_MODEL", "gpt-4o"),
            ai_batch_size=int(os.getenv("AI_BATCH_SIZE", "20")),
        )
