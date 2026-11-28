"""MUHR seller: data classification."""

from __future__ import annotations

import os

from sellers.core import SellerConfig, create_seller_app
from shared import constants

app = create_seller_app(SellerConfig(
    kind="classifier",
    seller_id=os.getenv("MUHR_SELLER_ID", "sel_classifier"),
    capability=constants.CLASSIFIER_CAPABILITY,
    price_per_unit=constants.CLASSIFIER_PRICE_PER_UNIT,
    unit_size=100,  # "per 100 items"
))
