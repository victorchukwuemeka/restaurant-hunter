"""
restaurant_hunter.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Multi-city Nigerian business hunter — finds businesses
with NO website so you can pitch your web-build service.

Now covers ALL major Nigerian cities and ALL business types:
  Food & Dining, Beauty & Salons, Health & Medical,
  Auto & Garage, Fashion & Retail, Fitness, Education,
  Events & Hospitality, Professional Services, Home Services,
  Electronics & Tech, Printing & Media, Supermarkets

SOURCES (layered, best-to-fallback):
  1. Google Maps Places API  — deep pagination via grid search
  2. Overpass API (OpenStreetMap) — completely FREE, unlimited
  3. Foursquare Places API   — free tier, different dataset

INSTALL:
  pip install requests pandas googlemaps tqdm colorama

USAGE:
  python restaurant_hunter.py

OUTPUT:
  leads_raw.csv  — all leads, ready to clean
  leads_raw.json — full data backup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import time
import json
import math
import requests
import pandas as pd
from tqdm import tqdm
from colorama import Fore, Style, init

init(autoreset=True)

# ── CONFIG ────────────────────────────────────────────────────
GOOGLE_API_KEY     = "YOUR_GOOGLE_API_KEY"      # cloud.google.com
FOURSQUARE_API_KEY = "YOUR_FOURSQUARE_API_KEY"  # foursquare.com/developer (free)

SEARCH_RADIUS  = 30_000   # meters per city centre

# Grid density: 5×5 = 25 cells per city
GRID_COLS, GRID_ROWS = 5, 5

OUTPUT_CSV  = "leads_raw.csv"
OUTPUT_JSON = "leads_raw.json"

# ── NIGERIAN CITIES ───────────────────────────────────────────
CITIES = {
    "Lagos":        {"lat": 6.5244, "lng": 3.3792},
    "Abuja":        {"lat": 9.0579, "lng": 7.4951},
    "Port Harcourt": {"lat": 4.8156, "lng": 7.0498},
    "Ibadan":       {"lat": 7.3775, "lng": 3.9470},
    "Kano":         {"lat": 12.0022, "lng": 8.5920},
    "Benin City":   {"lat": 6.3350, "lng": 5.6276},
    "Enugu":        {"lat": 6.4413, "lng": 7.4988},
    "Calabar":      {"lat": 4.9586, "lng": 8.3276},
    "Warri":        {"lat": 5.5167, "lng": 5.7500},
    "Jos":          {"lat": 9.8965, "lng": 8.8583},
    "Aba":          {"lat": 5.1063, "lng": 7.3667},
    "Owerri":       {"lat": 5.4833, "lng": 7.0333},
    "Kaduna":       {"lat": 10.5222, "lng": 7.4383},
    "Zaria":        {"lat": 11.0800, "lng": 7.7100},
    "Maiduguri":    {"lat": 11.8464, "lng": 13.1603},
}

# ── BUSINESS CATEGORIES ───────────────────────────────────────
# Each category maps to:
#   overpass_tags  → amenity/shop/tag pairs for OSM
#   foursquare_ids → Foursquare category IDs
#   google_queries → search terms for Google Maps

BUSINESS_CATEGORIES = {
    "Food & Dining": {
        "overpass_tags": [
            ("amenity", "restaurant"), ("amenity", "cafe"),
            ("amenity", "fast_food"),   ("amenity", "food_court"),
            ("shop",    "bakery"),
        ],
        "foursquare_ids": [
            "13065",  # Restaurant
            "13032",  # Café
            "13145",  # Fast Food
            "13338",  # African Restaurant
            "13048",  # Barbeque Joint
        ],
        "google_queries": [
            "restaurant", "food", "eatery", "cafe",
            "buka", "suya spot", "fast food", "food court",
        ],
    },
    "Beauty & Salons": {
        "overpass_tags": [
            ("shop", "beauty"),       ("shop", "hairdresser"),
            ("shop", "cosmetics"),    ("shop", "perfume"),
            ("amenity", "beauty_salon"),
        ],
        "foursquare_ids": [
            "11024",  # Hair Salon
            "11131",  # Nail Salon
            "11029",  # Day Spa
            "11132",  # Tanning Salon
            "11127",  # Massage Studio
        ],
        "google_queries": [
            "salon", "hair salon", "beauty salon", "barbershop",
            "nail salon", "spa", "cosmetics shop", "perfume store",
        ],
    },
    "Health & Medical": {
        "overpass_tags": [
            ("amenity", "pharmacy"),      ("amenity", "clinic"),
            ("amenity", "hospital"),       ("amenity", "dentist"),
            ("amenity", "doctors"),        ("amenity", "optician"),
            ("healthcare", "laboratory"),
        ],
        "foursquare_ids": [
            "15014",  # Hospital
            "15016",  # Dentist
            "15017",  # Doctor
            "15019",  # Pharmacy
            "15025",  # Lab
            "15031",  # Optometrist
            "15028",  # Chiropractor
        ],
        "google_queries": [
            "pharmacy", "hospital", "clinic", "dentist",
            "doctor", "medical lab", "optician", "eye clinic",
        ],
    },
    "Auto & Garage": {
        "overpass_tags": [
            ("shop", "car_repair"),    ("shop", "car_parts"),
            ("shop", "tyres"),         ("shop", "car"),
            ("shop", "car_cleaning"),  ("amenity", "car_wash"),
            ("shop", "bicycle_repair"),
        ],
        "foursquare_ids": [
            "15536",  # Auto Garage
            "15532",  # Auto Shop
            "15530",  # Auto Dealer
            "15535",  # Auto Parts
            "15542",  # Tire Shop
            "15540",  # Car Wash
        ],
        "google_queries": [
            "mechanic", "auto repair", "car wash", "car parts",
            "tyre shop", "car dealer", "garage", "auto electrical",
        ],
    },
    "Fashion & Retail": {
        "overpass_tags": [
            ("shop", "clothes"),     ("shop", "fashion"),
            ("shop", "shoes"),       ("shop", "bag"),
            ("shop", "jewelry"),     ("shop", "watches"),
            ("shop", "accessories"),
        ],
        "foursquare_ids": [
            "17028",  # Clothing Store
            "17029",  # Shoe Store
            "17031",  # Accessories Store
            "17030",  # Jewelry Store
            "17043",  # Lingerie Store
        ],
        "google_queries": [
            "boutique", "fashion store", "clothing shop", "shoe store",
            "jewelry store", "bags shop", "accessories store", "tailor",
        ],
    },
    "Fitness & Gym": {
        "overpass_tags": [
            ("leisure", "fitness_centre"), ("leisure", "sports_centre"),
            ("shop", "sports"),
        ],
        "foursquare_ids": [
            "18020",  # Gym / Fitness Center
            "18021",  # Boxing Gym
            "18022",  # Yoga Studio
            "18029",  # Dance Studio
        ],
        "google_queries": [
            "gym", "fitness center", "yoga studio", "crossfit",
            "fitness club", "exercise gym", "personal trainer",
        ],
    },
    "Education & Training": {
        "overpass_tags": [
            ("amenity", "school"),       ("amenity", "college"),
            ("amenity", "university"),    ("amenity", "kindergarten"),
            ("amenity", "language_school"),
        ],
        "foursquare_ids": [
            "12056",  # School
            "12058",  # College
            "12057",  # University
            "12064",  # Music School
            "12062",  # Language School
        ],
        "google_queries": [
            "school", "nursery school", "tutorial center", "coaching center",
            "skill acquisition", "vocational training", "learning center",
        ],
    },
    "Events & Hospitality": {
        "overpass_tags": [
            ("tourism", "hotel"),       ("tourism", "hostel"),
            ("tourism", "guest_house"), ("amenity", "bar"),
            ("amenity", "nightclub"),   ("amenity", "pub"),
            ("leisure", "event_venue"),
        ],
        "foursquare_ids": [
            "19014",  # Hotel
            "19015",  # Motel
            "19017",  # Hostel
            "19016",  # Bed & Breakfast
            "19029",  # Bar
            "19030",  # Nightclub
            "13003",  # Event Space
        ],
        "google_queries": [
            "hotel", "guest house", "event center", "event hall",
            "bar", "lounge", "nightclub", "banquet hall", "wedding venue",
        ],
    },
    "Professional Services": {
        "overpass_tags": [
            ("office", "lawyer"),       ("office", "accountant"),
            ("office", "insurance"),    ("office", "estate_agent"),
            ("amenity", "bank"),        ("amenity", "bureau_de_change"),
            ("office", "it"),
        ],
        "foursquare_ids": [
            "12021",  # Bank
            "12023",  # ATM
            "11047",  # Law Firm
            "11044",  # Accountant
            "12072",  # Real Estate Office
            "11138",  # Tech Startup
        ],
        "google_queries": [
            "lawyer", "law firm", "accountant", "insurance agent",
            "real estate", "property agent", "consultant", "bank",
            "IT company", "tech company",
        ],
    },
    "Home Services": {
        "overpass_tags": [
            ("shop", "furniture"),     ("shop", "hardware"),
            ("shop", "electrical"),    ("shop", "plumber"),
            ("shop", "paint"),         ("shop", "tiles"),
            ("shop", "plastic"),
        ],
        "foursquare_ids": [
            "17022",  # Home Store
            "17023",  # Hardware Store
            "17021",  # Furniture Store
            "11133",  # Plumbing Supply
        ],
        "google_queries": [
            "interior decorator", "furniture store", "home decor",
            "plumber", "electrician", "architect", "building materials",
            "paint store", "tiles shop", "real estate developer",
        ],
    },
    "Electronics & Tech": {
        "overpass_tags": [
            ("shop", "electronics"),   ("shop", "computer"),
            ("shop", "mobile_phone"),  ("shop", "telecom"),
            ("shop", "software"),
        ],
        "foursquare_ids": [
            "17025",  # Electronics Store
            "17027",  # Phone Repair
            "17044",  # Mobile Phone Shop
            "17046",  # Computer Store
        ],
        "google_queries": [
            "electronics store", "phone shop", "computer shop",
            "phone repair", "CCTV installer", "internet cafe",
            "software company", "tech store", "generator dealer",
        ],
    },
    "Printing & Media": {
        "overpass_tags": [
            ("shop", "print"),
            ("shop", "stationery"),
        ],
        "foursquare_ids": [
            "11046",  # Print Shop
            "11037",  # Office Supply Store
        ],
        "google_queries": [
            "print shop", "printing press", "advertising agency",
            "signage", "branding company", "photography studio",
            "video production", "media company",
        ],
    },
    "Supermarkets & Grocery": {
        "overpass_tags": [
            ("shop", "supermarket"),  ("shop", "grocery"),
            ("shop", "convenience"),   ("shop", "wholesale"),
            ("shop", "kiosk"),
        ],
        "foursquare_ids": [
            "17026",  # Supermarket
            "17032",  # Grocery Store
            "17033",  # Convenience Store
            "17034",  # Wholesale Store
        ],
        "google_queries": [
            "supermarket", "grocery store", "shoprite", "spar",
            "wholesale store", "mini market", "provision store",
        ],
    },
}

# ── HELPERS ───────────────────────────────────────────────────

def log(color, label, msg):
    print(f"{color}[{label}]{Style.RESET_ALL} {msg}")


def has_website(place: dict) -> bool:
    """Return True if the place clearly has a web presence."""
    website = place.get("website", "").strip()
    if not website:
        return False
    weak = ["facebook.com", "instagram.com", "twitter.com",
            "wa.me", "whatsapp", "youtube.com", "tiktok.com"]
    return not any(w in website.lower() for w in weak)


def deduplicate(records: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in records:
        key = (
            r.get("name", "").lower().strip(),
            r.get("phone", "").strip(),
            r.get("city", "").strip(),
        )
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ── SOURCE 1: GOOGLE MAPS (grid search) ──────────────────────

def google_grid_search() -> list[dict]:
    """
    For each city × category, divide into a grid and search.
    Overcomes the 60-result cap — each cell can return up to 60.
    """
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY":
        log(Fore.YELLOW, "GOOGLE", "API key not set — skipping Google source.")
        return []

    import googlemaps
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

    results, seen_ids = [], set()

    total_cities = len(CITIES)
    total_cats = len(BUSINESS_CATEGORIES)
    total_tasks = total_cities * total_cats
    log(Fore.CYAN, "GOOGLE",
        f"Searching {total_cities} cities × {total_cats} categories "
        f"= {total_tasks} jobs…")

    city_pbar = tqdm(CITIES.items(), desc="Cities", position=0)
    for city_name, coords in city_pbar:
        city_pbar.set_postfix(city=city_name)
        lat0, lng0 = coords["lat"], coords["lng"]

        dlat = (SEARCH_RADIUS / 111_000) * 2 / GRID_ROWS
        dlng = (SEARCH_RADIUS / (111_000 * math.cos(math.radians(lat0)))) * 2 / GRID_COLS

        cells = []
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                clat = lat0 - SEARCH_RADIUS / 111_000 + dlat * (row + 0.5)
                clng = lng0 - SEARCH_RADIUS / (111_000 * math.cos(math.radians(lat0))) + dlng * (col + 0.5)
                cells.append((clat, clng))

        cell_radius = int(SEARCH_RADIUS / max(GRID_COLS, GRID_ROWS) * 1.4)

        for cat_name, cat_data in BUSINESS_CATEGORIES.items():
            for q in cat_data["google_queries"]:
                for clat, clng in cells:
                    try:
                        page = gmaps.places(
                            query=q,
                            location=(clat, clng),
                            radius=cell_radius,
                        )
                        while True:
                            for place in page.get("results", []):
                                pid = place.get("place_id", "")
                                if pid in seen_ids:
                                    continue
                                seen_ids.add(pid)
                                try:
                                    det = gmaps.place(
                                        place_id=pid,
                                        fields=[
                                            "name", "formatted_phone_number",
                                            "website", "formatted_address",
                                            "rating", "user_ratings_total", "types",
                                        ],
                                    )["result"]
                                    if not has_website(det):
                                        results.append({
                                            "source":   "google",
                                            "city":     city_name,
                                            "category": cat_name,
                                            "name":     det.get("name", ""),
                                            "phone":    det.get("formatted_phone_number", ""),
                                            "address":  det.get("formatted_address", ""),
                                            "website":  "",
                                            "rating":   det.get("rating", ""),
                                            "reviews":  det.get("user_ratings_total", ""),
                                            "types":    ", ".join(det.get("types", [])),
                                            "place_id": pid,
                                        })
                                except Exception:
                                    pass
                                time.sleep(0.05)

                            next_token = page.get("next_page_token")
                            if not next_token:
                                break
                            time.sleep(2)
                            page = gmaps.places(page_token=next_token)

                    except Exception as e:
                        log(Fore.RED, "GOOGLE", f"{city_name}/{q} error: {e}")

    log(Fore.GREEN, "GOOGLE", f"Found {len(results)} prospects.")
    return results


# ── SOURCE 2: OVERPASS / OPENSTREETMAP (FREE, unlimited) ─────

def overpass_search() -> list[dict]:
    """
    Query OpenStreetMap via Overpass API for ALL cities and categories.
    Completely free, no key needed.
    """
    log(Fore.CYAN, "OSM", "Querying Overpass API (free, no key)…")

    results = []

    for city_name, coords in tqdm(CITIES.items(), desc="OSM cities"):
        lat, lng = coords["lat"], coords["lng"]

        # Collect all OSM tag pairs for this city
        tag_clauses = []
        for cat_name, cat_data in BUSINESS_CATEGORIES.items():
            for tag_key, tag_val in cat_data["overpass_tags"]:
                tag_clauses.append(f'node["{tag_key}"="{tag_val}"](around:{SEARCH_RADIUS},{lat},{lng});')
                tag_clauses.append(f'way["{tag_key}"="{tag_val}"](around:{SEARCH_RADIUS},{lat},{lng});')

        query = f"""
        [out:json][timeout:120];
        (
          {chr(10).join(tag_clauses)}
        );
        out body;
        """

        try:
            resp = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(Fore.RED, "OSM", f"{city_name} request failed: {e}")
            continue

        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name", "").strip()
            if not name:
                continue

            website = tags.get("website", tags.get("contact:website", ""))
            if has_website({"website": website}):
                continue

            # Determine category from tags
            cat_label = _categorize_osm(tags)

            phone = (
                tags.get("phone", "")
                or tags.get("contact:phone", "")
                or tags.get("mobile", "")
                or tags.get("contact:mobile", "")
            ).strip()

            addr_parts = [
                tags.get("addr:housenumber", ""),
                tags.get("addr:street", ""),
                tags.get("addr:suburb", ""),
                tags.get("addr:city", city_name),
            ]
            address = ", ".join(p for p in addr_parts if p) or city_name + ", Nigeria"

            results.append({
                "source":   "openstreetmap",
                "city":     city_name,
                "category": cat_label,
                "name":     name,
                "phone":    phone,
                "address":  address,
                "website":  "",
                "rating":   "",
                "reviews":  "",
                "types":    _osm_type_label(tags),
                "place_id": f"osm_{el['type']}_{el['id']}",
            })

    log(Fore.GREEN, "OSM", f"Found {len(results)} prospects.")
    return results


def _categorize_osm(tags: dict) -> str:
    """Map OSM tags to our BUSINESS_CATEGORIES labels."""
    for cat_name, cat_data in BUSINESS_CATEGORIES.items():
        for tag_key, tag_val in cat_data["overpass_tags"]:
            if tags.get(tag_key) == tag_val:
                return cat_name
    return "Other"


def _osm_type_label(tags: dict) -> str:
    """Get a readable type label from OSM tags."""
    for key in ["amenity", "shop", "office", "tourism", "leisure", "healthcare"]:
        if key in tags:
            return tags[key]
    return "business"


# ── SOURCE 3: FOURSQUARE (free tier, 1000 calls/day) ─────────

def foursquare_search() -> list[dict]:
    """
    Foursquare Places API — different dataset, catches businesses
    that Google/OSM miss. Free tier: 1,000 calls/day.
    """
    if not FOURSQUARE_API_KEY or FOURSQUARE_API_KEY == "YOUR_FOURSQUARE_API_KEY":
        log(Fore.YELLOW, "4SQ", "API key not set — skipping Foursquare source.")
        return []

    log(Fore.CYAN, "4SQ", "Querying Foursquare Places API…")

    headers = {
        "Authorization": FOURSQUARE_API_KEY,
        "Accept": "application/json",
    }

    results, seen = [], set()

    for city_name, coords in tqdm(CITIES.items(), desc="4SQ cities"):
        ll = f"{coords['lat']},{coords['lng']}"

        for cat_name, cat_data in BUSINESS_CATEGORIES.items():
            for fsq_cat in cat_data["foursquare_ids"]:
                for offset in range(0, 200, 50):
                    try:
                        resp = requests.get(
                            "https://api.foursquare.com/v3/places/search",
                            headers=headers,
                            params={
                                "ll": ll,
                                "radius": SEARCH_RADIUS,
                                "categories": fsq_cat,
                                "limit": 50,
                                "offset": offset,
                                "fields": "name,location,tel,website,rating,stats,categories",
                            },
                            timeout=20,
                        )
                        resp.raise_for_status()
                        places = resp.json().get("results", [])
                        if not places:
                            break

                        for p in places:
                            fsq_id = p.get("fsq_id", "")
                            if fsq_id in seen:
                                continue
                            seen.add(fsq_id)

                            website = p.get("website", "")
                            if has_website({"website": website}):
                                continue

                            loc = p.get("location", {})
                            addr = (
                                loc.get("formatted_address", "")
                                or ", ".join(filter(None, [
                                    loc.get("address", ""),
                                    loc.get("locality", ""),
                                    loc.get("region", ""),
                                ]))
                            )

                            results.append({
                                "source":   "foursquare",
                                "city":     city_name,
                                "category": cat_name,
                                "name":     p.get("name", ""),
                                "phone":    p.get("tel", ""),
                                "address":  addr or city_name + ", Nigeria",
                                "website":  "",
                                "rating":   p.get("rating", ""),
                                "reviews":  p.get("stats", {}).get("total_ratings", ""),
                                "types":    ", ".join(
                                    c.get("name", "") for c in p.get("categories", [])
                                ),
                                "place_id": f"fsq_{fsq_id}",
                            })

                        time.sleep(0.15)

                    except Exception as e:
                        log(Fore.RED, "4SQ", f"{city_name}/{fsq_cat} error: {e}")
                        break

    log(Fore.GREEN, "4SQ", f"Found {len(results)} prospects.")
    return results


# ── SCORING: prioritise best leads ────────────────────────────

def score_lead(r: dict) -> int:
    """
    Score each lead so the CSV is sorted best → worst.
    Higher = easier / warmer pitch.
    """
    score = 0
    if r.get("phone"):
        score += 30   # can actually contact them
    if r.get("rating"):
        try:
            score += int(float(r["rating"]) * 4)  # up to +20 for 5★
        except ValueError:
            pass
    if r.get("reviews"):
        try:
            score += min(int(r["reviews"]) // 10, 20)  # popular = good
        except (ValueError, TypeError):
            pass
    if r.get("address") and r["address"] != "Lagos, Nigeria":
        score += 10
    return score


# ── MAIN ──────────────────────────────────────────────────────

def main():
    print(f"\n{Fore.YELLOW}{'━' * 60}")
    print(f"  🇳🇬  Nigeria Business Hunter — No-Website Edition")
    print(f"  📍  {len(CITIES)} cities  ×  {len(BUSINESS_CATEGORIES)} categories")
    print(f"{'━' * 60}{Style.RESET_ALL}\n")

    all_results: list[dict] = []

    # Run all sources
    all_results += overpass_search()     # free, run first
    all_results += google_grid_search()
    all_results += foursquare_search()

    if not all_results:
        log(Fore.RED, "DONE",
            "No results — check your API keys and internet connection.")
        return

    # Deduplicate across sources
    unique = deduplicate(all_results)
    log(Fore.CYAN, "MERGE",
        f"{len(all_results)} total → {len(unique)} unique after dedup.")

    # Score and sort
    for r in unique:
        r["lead_score"] = score_lead(r)
    unique.sort(key=lambda x: x["lead_score"], reverse=True)

    # Add pitch note
    for r in unique:
        r["pitch_note"] = (
            f"Hi, I noticed {r['name']} in {r['city']} doesn't have a website yet. "
            f"I build premium business websites for Nigerian businesses — "
            f"yours could be live in 3 weeks."
        )

    # Save
    df = pd.DataFrame(unique)
    cols = [
        "name", "phone", "city", "category", "address", "types",
        "rating", "reviews", "lead_score", "source", "pitch_note",
        "place_id", "website",
    ]
    df = df[[c for c in cols if c in df.columns]]

    df.to_csv(OUTPUT_CSV, index=False)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    # Summary stats
    print(f"\n{Fore.GREEN}{'━' * 60}")
    print(f"  ✅  Done! {len(unique)} businesses with no website found.")
    print(f"  📄  CSV  → {OUTPUT_CSV}")
    print(f"  🗂️   JSON → {OUTPUT_JSON}")
    print(f"{'━' * 60}{Style.RESET_ALL}")

    # Breakdown by city
    city_counts = df["city"].value_counts()
    print(f"\n{Fore.CYAN}── By City ──{Style.RESET_ALL}")
    for city, count in city_counts.items():
        print(f"  {city:20s} {count}")

    # Breakdown by category
    cat_counts = df["category"].value_counts()
    print(f"\n{Fore.CYAN}── By Category ──{Style.RESET_ALL}")
    for cat, count in cat_counts.items():
        print(f"  {cat:20s} {count}")

    # Top lead
    if unique:
        top = unique[0]
        print(f"\n  🔥  Top lead: {top['name']} ({top['city']})")

    print()


if __name__ == "__main__":
    main()
