import json
import re
import csv
from collections import defaultdict
from pathlib import Path

import requests

BASE = "https://guide.michelin.com"
ALGOLIA_URL = "https://8nvhrd7onv-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_PARAMS = {
    "x-algolia-agent": "Algolia for JavaScript (5.47.0); Lite (5.47.0); Browser",
    "x-algolia-api-key": "3222e669cf890dc73fa5f38241117ba5",
    "x-algolia-application-id": "8NVHRD7ONV",
}
HEADERS = {
    "Referer": "https://guide.michelin.com/sg/zh_CN/restaurants",
    "Origin": "https://guide.michelin.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
}

DOWNLOAD_DIR = Path("download")


def norm_text(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def to_abs_url(url):
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{BASE}{url}"


def slugify_filename(s):
    txt = norm_text(s).lower().replace(" ", "-")
    txt = re.sub(r"[^a-z0-9\-_]+", "-", txt)
    txt = re.sub(r"-+", "-", txt).strip("-")
    return txt or "unknown-city"


def cuisine_labels(cuisines):
    out = []
    for c in cuisines or []:
        if isinstance(c, dict):
            label = norm_text(c.get("label", ""))
            if label:
                out.append(label)
    return out


def award_label(code):
    mapping = {
        "selected": "Selected",
        "BIB_GOURMAND": "Bib Gourmand",
        "1_star": "1 Star",
        "2_stars": "2 Stars",
        "3_stars": "3 Stars",
        "GREEN_STAR": "Green Star",
    }
    return mapping.get(code, code or "")


def fetch_all_china_restaurants():
    restaurants = []
    page = 0
    per_page = 100

    while True:
        payload = {
            "requests": [
                {
                    "indexName": "prod-restaurants-zh_CN",
                    "filters": "status:Published AND country.slug:cn",
                    "optionalFilters": ["sites:sg"],
                    "attributesToRetrieve": [
                        "name",
                        "city",
                        "country",
                        "region",
                        "phone",
                        "main_desc",
                        "michelin_award",
                        "cuisines",
                        "price_category",
                        "url",
                    ],
                    "hitsPerPage": per_page,
                    "page": page,
                    "query": "",
                }
            ]
        }

        resp = requests.post(
            ALGOLIA_URL,
            params=ALGOLIA_PARAMS,
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()

        result = resp.json()["results"][0]
        hits = result.get("hits", [])
        restaurants.extend(hits)

        nb_pages = result.get("nbPages", 0)
        print(f"Fetched page {page + 1}/{max(nb_pages, 1)}: +{len(hits)}")

        page += 1
        if page >= nb_pages:
            break

    return restaurants


def normalize_restaurant(raw):
    city = raw.get("city") or {}
    region = raw.get("region") or {}
    country = raw.get("country") or {}
    price = raw.get("price_category") or {}

    return {
        "name": norm_text(raw.get("name", "")),
        "url": to_abs_url(raw.get("url", "")),
        "telephone": norm_text(raw.get("phone", "")),
        "description": norm_text(raw.get("main_desc", "")),
        "michelin_award": award_label(raw.get("michelin_award", "")),
        "city": norm_text(city.get("name", "")),
        "city_slug": norm_text(city.get("slug", "")),
        "region": norm_text(region.get("name", "")),
        "country": norm_text(country.get("name", "")),
        "price": norm_text(price.get("label", "")),
        "cuisines": cuisine_labels(raw.get("cuisines")),
    }


def write_city_files(restaurants):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    by_city = defaultdict(list)
    for raw in restaurants:
        item = normalize_restaurant(raw)
        city_name = item.get("city") or "Unknown"
        city_slug = item.get("city_slug") or city_name
        key = f"{city_name}||{city_slug}"
        by_city[key].append(item)

    city_index = []
    for key in sorted(by_city.keys()):
        city_name, city_slug = key.split("||", 1)
        city_restaurants = sorted(by_city[key], key=lambda x: x.get("name", ""))

        safe_slug = slugify_filename(city_slug)
        out_name = f"michelin_china_{safe_slug}_restaurants.json"
        out_path = DOWNLOAD_DIR / out_name

        payload = {
            "source": "https://guide.michelin.com/sg/zh_CN/restaurants",
            "country_filter": "cn",
            "city": city_name,
            "city_slug": city_slug,
            "restaurant_count": len(city_restaurants),
            "restaurants": city_restaurants,
        }

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        city_index.append(
            {
                "city": city_name,
                "city_slug": city_slug,
                "restaurant_count": len(city_restaurants),
                "file": str(out_path).replace("\\", "/"),
            }
        )

    index_payload = {
        "source": "https://guide.michelin.com/sg/zh_CN/restaurants",
        "country_filter": "cn",
        "city_count": len(city_index),
        "restaurant_count": len(restaurants),
        "cities": city_index,
    }

    index_path = DOWNLOAD_DIR / "michelin_china_city_index.json"
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index_payload, f, ensure_ascii=False, indent=2)

    return index_path, len(city_index)


def write_master_csv(restaurants):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DOWNLOAD_DIR / "michelin_china_restaurants_master.csv"

    fieldnames = [
        "name",
        "city",
        "city_slug",
        "region",
        "country",
        "michelin_award",
        "price",
        "cuisines",
        "telephone",
        "url",
        "description",
    ]

    normalized = [normalize_restaurant(raw) for raw in restaurants]
    normalized.sort(key=lambda x: (x.get("city", ""), x.get("name", "")))

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in normalized:
            writer.writerow(
                {
                    "name": item.get("name", ""),
                    "city": item.get("city", ""),
                    "city_slug": item.get("city_slug", ""),
                    "region": item.get("region", ""),
                    "country": item.get("country", ""),
                    "michelin_award": item.get("michelin_award", ""),
                    "price": item.get("price", ""),
                    "cuisines": "; ".join(item.get("cuisines", [])),
                    "telephone": item.get("telephone", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                }
            )

    return csv_path


def main():
    all_restaurants = fetch_all_china_restaurants()
    index_path, city_count = write_city_files(all_restaurants)
    csv_path = write_master_csv(all_restaurants)

    print("DONE")
    print(f"TOTAL_RESTAURANTS={len(all_restaurants)}")
    print(f"TOTAL_CITIES={city_count}")
    print(f"INDEX_FILE={index_path}")
    print(f"MASTER_CSV_FILE={csv_path}")


if __name__ == "__main__":
    main()
