import json
import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

LIST_URL = "https://guide.michelin.com/sg/zh_CN/jiang-su-/nanjing_1029511_noindex/restaurants?sort=distance"
BASE = "https://guide.michelin.com"


def norm_text(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def abs_url(href):
    if not href:
        return None
    return urljoin(BASE, href)


def collect_restaurant_links(page):
    links = set()
    for _ in range(8):
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1200)
    hrefs = page.eval_on_selector_all(
        "a[href*='/restaurant/']",
        "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
    )
    for h in hrefs:
        u = abs_url(h)
        if u and "/restaurant/" in u:
            links.add(u.split("?")[0])
    return links


def collect_pagination_links(page):
    links = set()
    hrefs = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
    )
    current = page.url
    current_path = urlparse(current).path
    for h in hrefs:
        u = abs_url(h)
        if not u:
            continue
        pu = urlparse(u)
        if pu.path == current_path and "page=" in pu.query:
            links.add(u)

    for sel in ["a[rel='next']", "a:has-text('Next')", "a:has-text('下一页')", "a:has-text('下頁')"]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                href = loc.get_attribute("href")
                if href:
                    links.add(abs_url(href))
        except Exception:
            pass

    return links


def extract_from_jsonld(page):
    out = {}
    scripts = page.locator("script[type='application/ld+json']")
    count = scripts.count()
    for i in range(count):
        txt = scripts.nth(i).inner_text()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]
        expanded = []
        for item in items:
            expanded.append(item)
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                expanded.extend(item["@graph"])

        for item in expanded:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            is_rest = "Restaurant" in t if isinstance(t, list) else t == "Restaurant"
            if not is_rest:
                continue

            out["name"] = out.get("name") or norm_text(str(item.get("name", "")))
            out["telephone"] = out.get("telephone") or norm_text(str(item.get("telephone", "")))
            out["cuisine"] = out.get("cuisine") or item.get("servesCuisine")
            out["priceRange"] = out.get("priceRange") or norm_text(str(item.get("priceRange", "")))

            addr = item.get("address")
            if isinstance(addr, dict):
                parts = [
                    addr.get("streetAddress", ""),
                    addr.get("addressLocality", ""),
                    addr.get("addressRegion", ""),
                    addr.get("postalCode", ""),
                    addr.get("addressCountry", ""),
                ]
                full_addr = norm_text(" ".join([p for p in parts if p]))
                if full_addr:
                    out["address"] = out.get("address") or full_addr
    return out


def extract_detail(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)

    for _ in range(6):
        if page.locator("h1").count() > 0:
            break
        page.wait_for_timeout(1000)

    title = norm_text(page.title())
    h1 = norm_text(page.locator("h1").first.inner_text()) if page.locator("h1").count() > 0 else ""
    body_text = norm_text(page.locator("body").inner_text())
    jsonld = extract_from_jsonld(page)

    address = ""
    for sel in ["[itemprop='streetAddress']", "[class*='address']", "[data-test*='address']"]:
        loc = page.locator(sel)
        if loc.count() > 0:
            cand = norm_text(loc.first.inner_text())
            if len(cand) >= 6:
                address = cand
                break

    tel = ""
    tel_match = re.search(r"(?:\+?\d[\d\-\s]{6,}\d)", body_text)
    if tel_match:
        tel = norm_text(tel_match.group(0))

    cuisine = ""
    price = ""
    chip_texts = page.eval_on_selector_all(
        "span,div,p",
        "els => els.map(e => (e.innerText || '').trim()).filter(Boolean).slice(0, 1200)",
    )
    for t in chip_texts:
        tt = norm_text(t)
        if not tt:
            continue
        if not price and re.search(r"[¥$€]{1,4}", tt):
            price = tt
        if not cuisine and re.search(r"(菜|Cuisine|cuisine|川菜|粤菜|淮扬|江浙|日料|法餐|中餐)", tt, re.IGNORECASE):
            if 2 <= len(tt) <= 60:
                cuisine = tt

    desc = ""
    for sel in [".data-sheet__description", "[class*='description'] p", "main p"]:
        loc = page.locator(sel)
        if loc.count() > 0:
            cand = norm_text(loc.first.inner_text())
            if len(cand) > 40:
                desc = cand
                break

    return {
        "url": url,
        "name": h1 or jsonld.get("name", ""),
        "title": title,
        "address": address or jsonld.get("address", ""),
        "telephone": tel or jsonld.get("telephone", ""),
        "cuisine": cuisine or jsonld.get("cuisine", ""),
        "priceRange": price or jsonld.get("priceRange", ""),
        "description": desc,
    }


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="zh-CN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        visited_pages = set()
        page_queue = [LIST_URL]
        restaurant_links = set()

        while page_queue and len(visited_pages) < 40:
            list_url = page_queue.pop(0)
            if list_url in visited_pages:
                continue
            visited_pages.add(list_url)

            page.goto(list_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2500)

            for _ in range(8):
                if page.locator("a[href*='/restaurant/']").count() > 0:
                    break
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(1200)

            links = collect_restaurant_links(page)
            restaurant_links.update(links)

            next_pages = collect_pagination_links(page)
            for np in next_pages:
                if np not in visited_pages:
                    page_queue.append(np)

        results = []
        all_links = sorted(restaurant_links)
        for i, u in enumerate(all_links, 1):
            try:
                item = extract_detail(page, u)
                results.append(item)
                print(f"[{i}/{len(all_links)}] OK {item.get('name') or u}")
            except Exception as e:
                print(f"[{i}/{len(all_links)}] FAIL {u} :: {e}")

        output = {
            "source": LIST_URL,
            "list_pages_visited": sorted(visited_pages),
            "restaurant_count": len(restaurant_links),
            "restaurants": results,
        }

        with open("michelin_nanjing_restaurants.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print("DONE")
        print(f"LIST_PAGES={len(visited_pages)}")
        print(f"RESTAURANTS_FOUND={len(restaurant_links)}")
        print(f"DETAILS_EXTRACTED={len(results)}")

        browser.close()


if __name__ == "__main__":
    main()
