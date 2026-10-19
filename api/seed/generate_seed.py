"""Generates listings.csv, ads.csv, reviews.csv and manifest.json — SAMPLE DATA, not real.

The manifest is hand-derived from the deliberate mutations below, not from running the
detector engine against the generated data. That keeps `pytest` a real check: if a
detector has a bug, the manifest and the engine's output will disagree.
"""

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
AS_OF = date(2026, 10, 19)
PREVIOUS = AS_OF - timedelta(days=1)
AD_DATES = [AS_OF - timedelta(days=d) for d in range(13, -1, -1)]  # 14 days, oldest first

BRANDS = {
    "GlowVeda": {
        "prefix": "GLOWVEDA",
        "category": "skincare",
        "seller_name": "GlowVeda Official Store",
        "price": 499.0,
        "mrp": 549.0,
        "units_sold_7d": 56.0,
        "rating": 4.3,
        "review_count": 140,
        "stock": 60,
        "bullet_count": 6,
        "image_count": 6,
        "ads_spend": 250.0,
        "ads_clicks": 40,
        "ads_orders": 6,
        "ads_sales": 650.0,
        "title": "GlowVeda Vitamin C Face Serum for Glowing Skin - 30ml, Pack of 1",
    },
    "Munchkraft": {
        "prefix": "MUNCHKRAFT",
        "category": "snacks",
        "seller_name": "Munchkraft Foods",
        "price": 199.0,
        "mrp": 219.0,
        "units_sold_7d": 140.0,
        "rating": 4.1,
        "review_count": 95,
        "stock": 200,
        "bullet_count": 6,
        "image_count": 6,
        "ads_spend": 150.0,
        "ads_clicks": 60,
        "ads_orders": 10,
        "ads_sales": 450.0,
        "title": "Munchkraft Roasted Masala Chips Snack Pack - 150 gm",
    },
    "Vayu Home": {
        "prefix": "VAYUHOME",
        "category": "home_appliances",
        "seller_name": "Vayu Home Appliances",
        "price": 1899.0,
        "mrp": 2099.0,
        "units_sold_7d": 14.0,
        "rating": 4.4,
        "review_count": 210,
        "stock": 25,
        "bullet_count": 7,
        "image_count": 7,
        "ads_spend": 350.0,
        "ads_clicks": 30,
        "ads_orders": 3,
        "ads_sales": 900.0,
        "title": "Vayu Home 1200 Watt Mixer Grinder Kitchen Appliance - Steel Jar, 3 Speed",
    },
}

# Each brand cycles through a small catalogue so SKUs read like distinct products.
# (title, price, mrp, rating). Titles sit inside the 40-150 char window and carry a
# category keyword; Flipkart's 3% uplift on price still stays under every MRP.
PRODUCTS = {
    "GlowVeda": [
        ("GlowVeda Vitamin C Face Serum for Glowing Skin - 30ml, Pack of 1", 499.0, 549.0, 4.3),
        ("GlowVeda Neem & Tulsi Foaming Face Wash for Oily Skin - 150ml", 299.0, 349.0, 4.2),
        ("GlowVeda Hyaluronic Acid Moisturising Face Cream - 50g", 449.0, 499.0, 4.4),
        ("GlowVeda SPF 50 Sunscreen Lotion for Face, Matte Finish - 50ml", 599.0, 699.0, 4.1),
        ("GlowVeda Aloe Vera Skin Soothing Gel for Face and Body - 200ml", 249.0, 299.0, 4.5),
        ("GlowVeda Niacinamide 10% Face Serum for Clear Skin - 30ml", 549.0, 649.0, 4.3),
        ("GlowVeda Kumkumadi Night Face Oil for Radiant Skin - 15ml", 799.0, 899.0, 4.6),
        ("GlowVeda Ubtan Face Pack for Tan Removal and Glow - 100g", 349.0, 399.0, 4.2),
    ],
    "Munchkraft": [
        ("Munchkraft Roasted Masala Chips Snack Pack - 150 gm", 199.0, 219.0, 4.1),
        ("Munchkraft Peri Peri Makhana Roasted Snack - 200 gm", 149.0, 175.0, 4.3),
        ("Munchkraft Ragi Millet Crisps, Baked Not Fried - 120 gm Pack", 129.0, 150.0, 4.2),
        ("Munchkraft Jaggery Peanut Chikki Bites - 250 gm Pack", 99.0, 120.0, 4.4),
        ("Munchkraft Cheese Jalapeno Nachos Chips - 170 gm", 179.0, 199.0, 4.0),
        ("Munchkraft Trail Mix Dry Fruit Snack Pack - 200 gm", 249.0, 299.0, 4.5),
        ("Munchkraft Banana Chips, Kerala Style in Coconut Oil - 180 gm", 159.0, 180.0, 4.3),
        ("Munchkraft Protein Puffs Snack, Tangy Tomato - 6 x 30 gm Pack", 299.0, 349.0, 4.1),
    ],
    "Vayu Home": [
        ("Vayu Home 1200 Watt Mixer Grinder Kitchen Appliance - Steel Jar, 3 Speed", 1899.0, 2099.0, 4.4),
        ("Vayu Home 1.8L Electric Kettle, 1500 Watt Stainless Steel Body", 1199.0, 1899.0, 4.3),
        ("Vayu Home 4.2L Digital Air Fryer, 1400 Watt, Kitchen Appliance", 4299.0, 5999.0, 4.2),
        ("Vayu Home 1000 Watt Dry Iron with Non-Stick Soleplate for Home", 899.0, 1199.0, 4.1),
        ("Vayu Home 2000 Watt Induction Cooktop for Kitchen, 8 Preset Menus", 2499.0, 3499.0, 4.3),
        ("Vayu Home 500 Watt Hand Blender with Steel Blades, 2 Speed", 1299.0, 1799.0, 4.0),
        ("Vayu Home 2 Slice Pop-Up Toaster, 750 Watt, Kitchen Appliance", 1099.0, 1499.0, 4.2),
        ("Vayu Home 1.5L Electric Rice Cooker, 500 Watt, Steel Inner Pot", 1799.0, 2499.0, 4.5),
    ],
}


def sku_profile(brand_name: str, brand_cfg: dict, local_idx: int) -> dict:
    """Per-SKU numbers: the brand's baseline with its own product and a sales-volume
    factor. Stock, units, spend, clicks, orders and sales all scale by the same factor,
    so ROAS and days-of-cover (what the detectors read) match the brand baseline and the
    manifest stays exact. The factor floor keeps every SKU's spend above min_spend_inr."""
    title, price, mrp, rating = PRODUCTS[brand_name][(local_idx - 1) % len(PRODUCTS[brand_name])]
    f = 0.75 + ((local_idx * 37) % 86) / 100  # 0.75 .. 1.60, deterministic
    return {
        **brand_cfg,
        "title": title,
        "price": price,
        "mrp": mrp,
        "rating": rating,
        "units_sold_7d": round(brand_cfg["units_sold_7d"] * f, 1),
        "stock": round(brand_cfg["stock"] * f),
        "ads_spend": round(brand_cfg["ads_spend"] * f, 2),
        "ads_clicks": max(1, round(brand_cfg["ads_clicks"] * f)),
        "ads_orders": max(1, round(brand_cfg["ads_orders"] * f)),
        "ads_sales": round(brand_cfg["ads_sales"] * f, 2),
        "review_count": round(brand_cfg["review_count"] * (0.5 + f)),
    }


PLATFORMS = ["Amazon", "Flipkart"]
FLIPKART_PRICE_MULT = 1.03  # baseline platform price gap, well under the 8% mismatch threshold

JOB_GROUPS = (
    ["oos_ads_live"] * 10
    + ["low_stock_high_spend"] * 10
    + ["price_mismatch"] * 10
    + ["price_above_mrp"] * 5  # applies to both platform rows per instance — see below
    + ["price_shock"] * 5      # applies to both platform rows per instance — see below
    + ["weak_content"] * 10
    + ["rating_drop_snapshot"] * 5
    + ["rating_drop_spike"] * 5
    + ["lost_buybox"] * 10
    + ["ad_waste_zero_orders"] * 5
    + ["ad_waste_low_roas"] * 5
    + ["suppressed"] * 10
    + ["stacked"] * 3
)

EN_POSITIVE = [
    "Good product, works as expected.",
    "Great value for money, will buy again.",
    "Quality is nice, delivery was quick.",
    "Satisfied with the purchase, no complaints.",
    "Works well, as described on the listing.",
]
HINGLISH_POSITIVE = [
    "Bahut acha product hai, paisa vasool!",
    "Delivery time pe hui, product bhi sahi hai.",
    "Quality thik thak hai, chalega.",
]
NEGATIVE_BY_BUCKET = {
    "damaged": ("Product tuta hua aaya, bahut disappointing.", 1),
    "fake": ("Lagta hai nakli product bheja hai, asli jaisa nahi hai.", 1),
    "quality": ("Quality bahut ghatiya hai, paisa waste ho gaya.", 1),
    "late": ("Order der se aaya, delivery bahut late thi.", 2),
    "packaging": ("Product acha tha pehle, ab box leak ho ke aaya, bahut ghatiya packaging 😡", 2),
}
NEGATIVE_BUCKET_ORDER = ["damaged", "fake", "quality", "late", "packaging"]

THIRD_PARTY_SELLER = "Shree Retail Traders"
WEAK_CONTENT_TITLE = "New Product Item"
INACTIVE_STATUS_ROTATION = ["suppressed", "inactive", "blocked"]


def build_assignment() -> dict[str, dict[int, str]]:
    """Round-robins the job list across the three brands so problem SKUs spread evenly,
    rather than piling up in whichever brand happens to come first."""
    brand_names = list(BRANDS.keys())
    assignment: dict[str, dict[int, str]] = {b: {} for b in brand_names}
    counters = {b: 0 for b in brand_names}
    for idx, job in enumerate(JOB_GROUPS):
        b = brand_names[idx % 3]
        counters[b] += 1
        assignment[b][counters[b]] = job
    return assignment


def make_sku(prefix: str, i: int) -> str:
    return f"{prefix}-{i:03d}"


def main() -> None:
    assignment = build_assignment()

    listing_rows: list[dict] = []
    ad_rows: list[dict] = []
    review_rows: list[dict] = []
    manifest: dict[str, list[str]] = {}

    for brand_name, brand_cfg in BRANDS.items():
        for local_idx in range(1, 41):
            cfg = sku_profile(brand_name, brand_cfg, local_idx)
            sku = make_sku(cfg["prefix"], local_idx)
            job = assignment[brand_name].get(local_idx)  # None => healthy

            for platform in PLATFORMS:
                platform_mult = FLIPKART_PRICE_MULT if platform == "Flipkart" else 1.0
                price = round(cfg["price"] * platform_mult, 2)
                mrp = cfg["mrp"]
                stock = cfg["stock"]
                rating_latest = cfg["rating"]
                rating_previous = cfg["rating"]
                buybox_owner = cfg["seller_name"]
                status = "active"
                title = cfg["title"]
                image_count = cfg["image_count"]
                bullet_count = cfg["bullet_count"]
                units_sold_7d = cfg["units_sold_7d"]

                ads_spend = cfg["ads_spend"]
                ads_clicks = cfg["ads_clicks"]
                ads_orders = cfg["ads_orders"]
                ads_sales = cfg["ads_sales"]

                expected_codes: list[str] = []

                # price_mismatch needs a cross-platform comparison: the designated
                # "target" platform (alternating by index) is pushed 15% above the
                # OTHER platform's own baseline price, on both snapshots (stable gap,
                # not a shock).
                is_target = (local_idx % 2 == 0 and platform == "Amazon") or (
                    local_idx % 2 == 1 and platform == "Flipkart"
                )

                if job == "oos_ads_live" and is_target:
                    stock = 0
                    expected_codes.append("oos_ads_live")

                elif job == "low_stock_high_spend" and is_target:
                    daily_units = units_sold_7d / 7
                    stock = max(1, int(daily_units * 1.5))
                    expected_codes.append("low_stock_high_spend")

                elif job == "price_mismatch" and is_target:
                    other_platform_price = round(cfg["price"] * (FLIPKART_PRICE_MULT if platform != "Flipkart" else 1.0), 2)
                    price = round(other_platform_price * 1.16, 2)
                    # decouple from price_above_mrp: this row's own MRP must clear the
                    # inflated price with room, or the 16% markup would double-fire it.
                    mrp = round(price * 1.3, 2)
                    expected_codes.append("price_mismatch")

                elif job == "price_above_mrp":
                    # applied to BOTH platform rows (no is_target gate): mrp never
                    # varies by platform here, so an identical price on both sides
                    # means zero cross-platform gap — no spurious price_mismatch.
                    price = round(mrp * 1.08, 2)
                    expected_codes.append("price_above_mrp")

                elif job == "price_shock":
                    # applied to BOTH platforms identically (not is_target-gated):
                    # a shock on only one side would create an artificial cross-
                    # platform price gap and spuriously fire price_mismatch too.
                    rating_previous = cfg["rating"]
                    expected_codes.append("price_shock")
                    # price set below, after previous-snapshot row is built

                elif job == "weak_content" and is_target:
                    title = WEAK_CONTENT_TITLE
                    image_count = 2
                    bullet_count = 3
                    expected_codes.append("weak_content")

                elif job == "rating_drop_snapshot" and is_target:
                    rating_previous = 4.5
                    rating_latest = 4.1
                    expected_codes.append("rating_drop")

                elif job == "rating_drop_spike" and is_target:
                    expected_codes.append("rating_drop")
                    # the spike itself comes from extra reviews added below

                elif job == "lost_buybox" and is_target:
                    buybox_owner = THIRD_PARTY_SELLER
                    expected_codes.append("lost_buybox")

                elif job == "ad_waste_zero_orders" and is_target:
                    ads_orders = 0
                    ads_sales = 0.0
                    expected_codes.append("ad_waste")

                elif job == "ad_waste_low_roas" and is_target:
                    ads_spend = cfg["ads_spend"] * 1.6
                    ads_sales = cfg["ads_sales"] * 0.25
                    ads_orders = 2
                    expected_codes.append("ad_waste")

                elif job == "suppressed" and is_target:
                    status = INACTIVE_STATUS_ROTATION[local_idx % 3]
                    expected_codes.append("suppressed")

                elif job == "stacked" and is_target:
                    stock = 0
                    buybox_owner = THIRD_PARTY_SELLER
                    ads_orders = 0
                    ads_sales = 0.0
                    expected_codes.extend(["oos_ads_live", "ad_waste", "lost_buybox"])

                key = f"{sku}|{platform}"
                manifest[key] = sorted(expected_codes)

                previous_price = price
                if job == "price_shock":
                    previous_price = price
                    price = round(price * 0.75, 2)  # -25% shock on the latest snapshot

                for snap_date, snap_price, snap_rating in (
                    (PREVIOUS, previous_price, rating_previous),
                    (AS_OF, price, rating_latest),
                ):
                    listing_rows.append(
                        {
                            "snapshot_date": snap_date.isoformat(),
                            "brand": brand_name,
                            "sku": sku,
                            "platform": platform,
                            "title": title,
                            "bullet_count": bullet_count,
                            "image_count": image_count,
                            "price": snap_price,
                            "mrp": mrp,
                            "stock": stock,
                            "rating": snap_rating,
                            "review_count": cfg["review_count"],
                            "buybox_owner": buybox_owner,
                            "category": cfg["category"],
                            "status": status,
                            "units_sold_7d": units_sold_7d,
                        }
                    )

                for d in AD_DATES:
                    ad_rows.append(
                        {
                            "date": d.isoformat(),
                            "sku": sku,
                            "platform": platform,
                            "spend": round(ads_spend, 2),
                            "clicks": ads_clicks,
                            "orders": ads_orders,
                            "sales": round(ads_sales, 2),
                        }
                    )

                # baseline review, always outside the 7-day window
                bucket = NEGATIVE_BUCKET_ORDER[local_idx % len(NEGATIVE_BUCKET_ORDER)]
                text_pool = HINGLISH_POSITIVE if local_idx % 2 == 0 else EN_POSITIVE
                review_rows.append(
                    {
                        "sku": sku,
                        "platform": platform,
                        "review_date": (AS_OF - timedelta(days=18)).isoformat(),
                        "stars": 5 if local_idx % 3 else 4,
                        "text": text_pool[local_idx % len(text_pool)],
                    }
                )

                if job == "rating_drop_snapshot" and is_target:
                    # older complaints behind the snapshot drop, dated outside the 7-day
                    # window so they explain the drop without also firing the spike rule
                    for i, days_ago in enumerate([9, 12]):
                        b = NEGATIVE_BUCKET_ORDER[(local_idx + i) % len(NEGATIVE_BUCKET_ORDER)]
                        text, stars = NEGATIVE_BY_BUCKET[b]
                        review_rows.append(
                            {
                                "sku": sku,
                                "platform": platform,
                                "review_date": (AS_OF - timedelta(days=days_ago)).isoformat(),
                                "stars": stars,
                                "text": text,
                            }
                        )

                if job == "rating_drop_spike" and is_target:
                    for i, days_ago in enumerate([2, 4, 6]):
                        b = NEGATIVE_BUCKET_ORDER[(local_idx + i) % len(NEGATIVE_BUCKET_ORDER)]
                        text, stars = NEGATIVE_BY_BUCKET[b]
                        review_rows.append(
                            {
                                "sku": sku,
                                "platform": platform,
                                "review_date": (AS_OF - timedelta(days=days_ago)).isoformat(),
                                "stars": stars,
                                "text": text,
                            }
                        )

    _write_csv(
        SEED_DIR / "listings.csv",
        listing_rows,
        [
            "snapshot_date", "brand", "sku", "platform", "title", "bullet_count",
            "image_count", "price", "mrp", "stock", "rating", "review_count",
            "buybox_owner", "category", "status", "units_sold_7d",
        ],
    )
    _write_csv(
        SEED_DIR / "ads.csv",
        ad_rows,
        ["date", "sku", "platform", "spend", "clicks", "orders", "sales"],
    )
    _write_csv(
        SEED_DIR / "reviews.csv",
        review_rows,
        ["sku", "platform", "review_date", "stars", "text"],
    )

    with open(SEED_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    n_flagged = sum(1 for v in manifest.values() if v)
    print(f"Wrote {len(listing_rows)} listing rows, {len(ad_rows)} ad rows, "
          f"{len(review_rows)} review rows.")
    print(f"Manifest: {n_flagged}/{len(manifest)} (sku, platform) pairs flagged "
          f"({100 * (1 - n_flagged / len(manifest)):.0f}% healthy).")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("# SAMPLE DATA — synthetic, generated for the Marketplace Listing Audit demo\n")
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
