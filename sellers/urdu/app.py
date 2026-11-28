"""MUHR seller: Urdu <-> English translation."""

from __future__ import annotations

import os

from sellers.core import SellerConfig, create_seller_app
from shared import constants

app = create_seller_app(SellerConfig(
    kind="translator",
    seller_id=os.getenv("MUHR_SELLER_ID", "sel_urdu"),
    capability=constants.URDU_CAPABILITY,
    price_per_unit=constants.URDU_PRICE_PER_UNIT,
    unit_size=constants.URDU_UNIT_CHARS,  # "per 1000 characters"
))
