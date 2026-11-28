"""MUHR seller: text summarization."""

from __future__ import annotations

import os

from sellers.core import SellerConfig, create_seller_app
from shared import constants

app = create_seller_app(SellerConfig(
    kind="summarizer",
    seller_id=os.getenv("MUHR_SELLER_ID", "sel_summarizer"),
    capability=constants.SUMMARIZER_CAPABILITY,
    price_per_unit=constants.SUMMARIZER_PRICE_PER_UNIT,
    unit_size=1000,  # "per 1000 tokens"
))
