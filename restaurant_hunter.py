"""
restaurant_hunter.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Multi-source Lagos restaurant hunter — finds businesses
with NO website so you can pitch your web-build service.

SOURCES (layered, best-to-fallback):
  1. Google Maps Places API  — deep pagination via grid search
  2. Overpass API (OpenStreetMap) — completely FREE, unlimited
  3. Foursquare Places API   — free tier, different dataset

INSTALL:
  pip install requests pandas googlemaps tqdm colorama

USAGE:
  python restaurant_hunter.py

OUTPUT:
  restaurants_no_website.csv  — ready to pitch
  restaurants_no_website.json — full data backup
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

# Lagos bounding box
LAGOS_CENTER   = (6.5244, 3.3792)
SEARCH_RADIUS  = 50_000   # meters — full Lagos

# Grid density: more cells = more results, more API calls
# 5×5 = 25 cells covers Lagos well without hammering rate limits
GRID_COLS, GRID_ROWS = 5, 5

OUTPUT_CSV  = "restaurants_no_website.csv"
OUTPUT_JSON = "restaurants_no_website.json"

# ── HELPERS ───────────────────────────────────────────────────

def log(color, label, msg):
    print(f"{color}[{label}]{Style.RESET_ALL} {msg}")


def has_website(place: dict) -> bool:
    """Return True if the place clearly has a web presence."""
    website = place.get("website", "").strip()
    if not website:
        return False
    # Ignore Facebook/Instagram pages — not a real site
    weak = ["facebook.com", "instagram.com", "twitter.com",
            "wa.me", "whatsapp", "youtube.com"]
    return not any(w in website.lower() for w in weak)


def deduplicate(records: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in records:
        key = (r.get("name","").lower().strip(), r.get("phone","").strip())
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ── SOURCE 1: GOOGLE MAPS (grid search) ──────────────────────

def google_grid_search() -> list[dict]:
    """
    Divide Lagos into a grid and search each cell independently.
    Overcomes the 60-result cap — each cell can return up to 60.
    A 5×5 grid = up to 1,500 unique results.
    """
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY":
        log(Fore.YELLOW, "GOOGLE", "API key not set — skipping Google source.")
        return []

    import googlemaps
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

    # Build grid of lat/lng centres
    lat0, lng0 = LAGOS_CENTER
    # Approx degrees per cell
    dlat = (SEARCH_RADIUS / 111_000) * 2 / GRID_ROWS
    dlng = (SEARCH_RADIUS / (111_000 * math.cos(math.radians(lat0)))) * 2 / GRID_COLS

    cells = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            clat = lat0 - SEARCH_RADIUS/111_000 + dlat * (row + 0.5)
            clng = lng0 - SEARCH_RADIUS/(111_000*math.cos(math.radians(lat0))) + dlng*(col+0.5)
            cells.append((clat, clng))

    cell_radius = int(SEARCH_RADIUS / max(GRID_COLS, GRID_ROWS) * 1.4)
    results, seen_ids = [], set()
    queries = ["restaurant", "food", "eatery", "cafe", "buka", "suya spot"]

    log(Fore.CYAN, "GOOGLE", f"Searching {len(cells)} grid cells × {len(queries)} queries…")

    for (clat, clng) in tqdm(cells, desc="Grid cells"):
        for q in queries:
            try:
                page = gmaps.places(query=q, location=(clat, clng), radius=cell_radius)
                while True:
                    for place in page.get("results", []):
                        pid = place["place_id"]
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        try:
                            det = gmaps.place(
                                place_id=pid,
                                fields=["name","formatted_phone_number",
                                        "website","formatted_address",
                                        "rating","user_ratings_total","types"]
                            )["result"]
                            if not has_website(det):
                                results.append({
                                    "source":   "google",
                                    "name":     det.get("name",""),
                                    "phone":    det.get("formatted_phone_number",""),
                                    "address":  det.get("formatted_address",""),
                                    "website":  "",
                                    "rating":   det.get("rating",""),
                                    "reviews":  det.get("user_ratings_total",""),
                                    "types":    ", ".join(det.get("types",[])),
                                    "place_id": pid,
                                })
                        except Exception:
                            pass
                        time.sleep(0.05)

                    next_token = page.get("next_page_token")
                    if not next_token:
                        break
                    time.sleep(2)  # Google requires 2s before using next_page_token
                    page = gmaps.places(page_token=next_token)

            except Exception as e:
                log(Fore.RED, "GOOGLE", f"Cell error: {e}")

    log(Fore.GREEN, "GOOGLE", f"Found {len(results)} prospects.")
    return results


# ── SOURCE 2: OVERPASS / OPENSTREETMAP (FREE, unlimited) ─────

def overpass_search() -> list[dict]:
    """
    Query OpenStreetMap via Overpass API.
    Completely free, no key needed, great coverage of Lagos.
    Filters for amenity=restaurant/cafe/fast_food/food_court
    and returns only those WITHOUT a 'website' tag.
    """
    log(Fore.CYAN, "OSM", "Querying Overpass API (free, no key)…")

    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"="restaurant"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
      node["amenity"="cafe"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
      node["amenity"="fast_food"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
      node["amenity"="food_court"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
      node["shop"="bakery"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
      way["amenity"="restaurant"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
      way["amenity"="cafe"](around:{SEARCH_RADIUS},{LAGOS_CENTER[0]},{LAGOS_CENTER[1]});
    );
    out body;
    """

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=120
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(Fore.RED, "OSM", f"Request failed: {e}")
        return []

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name", "").strip()
        if not name:
            continue
        website = tags.get("website", tags.get("contact:website", ""))
        if has_website({"website": website}):
            continue

        phone = (tags.get("phone","") or
                 tags.get("contact:phone","") or
                 tags.get("mobile","")).strip()

        # Build rough address from OSM tags
        addr_parts = [
            tags.get("addr:housenumber",""),
            tags.get("addr:street",""),
            tags.get("addr:suburb",""),
            tags.get("addr:city","Lagos"),
        ]
        address = ", ".join(p for p in addr_parts if p) or "Lagos, Nigeria"

        results.append({
            "source":   "openstreetmap",
            "name":     name,
            "phone":    phone,
            "address":  address,
            "website":  "",
            "rating":   "",
            "reviews":  "",
            "types":    tags.get("amenity", tags.get("shop","")),
            "place_id": f"osm_{el['type']}_{el['id']}",
        })

    log(Fore.GREEN, "OSM", f"Found {len(results)} prospects.")
    return results


# ── SOURCE 3: FOURSQUARE (free tier, 1000 calls/day) ─────────

def foursquare_search() -> list[dict]:
    """
    Foursquare Places API — different dataset, catches restaurants
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

    # Foursquare category IDs for food
    categories = [
        "13065",  # Restaurant
        "13032",  # Café
        "13145",  # Fast Food
        "13338",  # African Restaurant
        "13048",  # Barbeque Joint
    ]

    results, seen = [], set()

    # Use offset pagination — Foursquare allows up to 50 per call
    for cat in categories:
        for offset in range(0, 500, 50):
            try:
                resp = requests.get(
                    "https://api.foursquare.com/v3/places/search",
                    headers=headers,
                    params={
                        "ll": f"{LAGOS_CENTER[0]},{LAGOS_CENTER[1]}",
                        "radius": SEARCH_RADIUS,
                        "categories": cat,
                        "limit": 50,
                        "offset": offset,
                        "fields": "name,location,tel,website,rating,stats,categories",
                    },
                    timeout=20
                )
                resp.raise_for_status()
                places = resp.json().get("results", [])
                if not places:
                    break

                for p in places:
                    fsq_id = p.get("fsq_id","")
                    if fsq_id in seen:
                        continue
                    seen.add(fsq_id)

                    website = p.get("website","")
                    if has_website({"website": website}):
                        continue

                    loc = p.get("location", {})
                    addr = loc.get("formatted_address","") or \
                           ", ".join(filter(None,[
                               loc.get("address",""),
                               loc.get("locality",""),
                               loc.get("region",""),
                           ]))

                    results.append({
                        "source":   "foursquare",
                        "name":     p.get("name",""),
                        "phone":    p.get("tel",""),
                        "address":  addr or "Lagos, Nigeria",
                        "website":  "",
                        "rating":   p.get("rating",""),
                        "reviews":  p.get("stats",{}).get("total_ratings",""),
                        "types":    ", ".join(c.get("name","") for c in p.get("categories",[])),
                        "place_id": f"fsq_{fsq_id}",
                    })

                time.sleep(0.15)

            except Exception as e:
                log(Fore.RED, "4SQ", f"Error at offset {offset}: {e}")
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
    if r.get("phone"):       score += 30   # can actually contact them
    if r.get("rating"):
        try:
            score += int(float(r["rating"]) * 4)  # up to +20 for 5★
        except ValueError:
            pass
    if r.get("reviews"):
        try:
            score += min(int(r["reviews"]) // 10, 20)  # popular = good prospect
        except (ValueError, TypeError):
            pass
    if r.get("address"):     score += 10
    return score


# ── MAIN ──────────────────────────────────────────────────────

def main():
    print(f"\n{Fore.YELLOW}{'━'*56}")
    print(f"  🍽️  Lagos Restaurant Hunter — No-Website Edition")
    print(f"{'━'*56}{Style.RESET_ALL}\n")

    all_results: list[dict] = []

    # Run all sources
    all_results += overpass_search()   # free, run first
    all_results += google_grid_search()
    all_results += foursquare_search()

    if not all_results:
        log(Fore.RED, "DONE", "No results — check your API keys and internet connection.")
        return

    # Deduplicate across sources
    unique = deduplicate(all_results)
    log(Fore.CYAN, "MERGE", f"{len(all_results)} total → {len(unique)} unique after dedup.")

    # Score and sort
    for r in unique:
        r["lead_score"] = score_lead(r)
    unique.sort(key=lambda x: x["lead_score"], reverse=True)

    # Add a pitch note column
    for r in unique:
        r["pitch_note"] = (
            f"Hi, I noticed {r['name']} doesn't have a website yet. "
            f"I build premium restaurant sites for Lagos businesses — "
            f"yours could have online reservations and a digital menu live in 3 weeks."
        )

    # Save
    df = pd.DataFrame(unique)
    # Reorder columns nicely
    cols = ["name","phone","address","types","rating","reviews",
            "lead_score","source","pitch_note","place_id","website"]
    df = df[[c for c in cols if c in df.columns]]

    df.to_csv(OUTPUT_CSV, index=False)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    print(f"\n{Fore.GREEN}{'━'*56}")
    print(f"  ✅  Done! {len(unique)} restaurants with no website found.")
    print(f"  📄  CSV  → {OUTPUT_CSV}")
    print(f"  🗂️   JSON → {OUTPUT_JSON}")
    print(f"  🔥  Top lead: {unique[0]['name']} ({unique[0].get('address','')})")
    print(f"{'━'*56}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()
