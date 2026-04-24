#!/usr/bin/env python3

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = "https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml?origin=menu"
DEFAULT_KEYWORDS = [
    "artist",
    "art",
    "creative",
    "design",
    "photography",
    "photo",
    "videography",
    "video",
    "media",
    "workshop",
    "training",
    "event",
    "programme",
]
DEFAULT_VALIDATE_DOC_URL = "https://www.gebiz.gov.sg/ptn/opportunity/directlink.xhtml?docCode=MOE000ETQ26000095"
STATUS_WORDS = [
    "OPEN",
    "AWARDED",
    "CLOSED",
    "PENDING AWARD",
    "CANCELLED",
    "WITHDRAWN",
]
SECTION_MARKERS = [
    "PRIMARY",
    "SECONDARY",
    "AWARDING AGENCY",
    "CONTACT PERSON'S DETAILS",
    "ITEMS TO RESPOND",
    "WHO TO CONTACT",
]
FIELD_LABELS = [
    "Quotation No.",
    "Tender No.",
    "Qualification No.",
    "Reference No.",
    "Agency",
    "Published",
    "Offer Validity Duration",
    "Remarks",
    "Procurement Type",
    "Quotation Type",
    "Tender Type",
    "Procurement Nature",
    "Procurement Method",
    "Payment Terms",
    "Quotation Box No.",
    "Tender Box No.",
    "Procurement Category",
    "Closed",
    "Closing on",
    "Awarding Agency",
    # Awarded-tender fields — present only when status is AWARDED
    "Awarded To",
    "Awarded Suppliers",
    "Successful Tenderer",
    "Awarded Amount",
    "Total Awarded Amount",
    "Awarded Sum",
    "Contract Sum",
    "Awarded Date",
    "Awarded On",
]
_PRICE_RE = re.compile(r"S?\$?\s*([\d,]+(?:\.\d+)?)", re.I)
STOP_TOKENS = set(FIELD_LABELS + SECTION_MARKERS + STATUS_WORDS + ["Print", "#"])
STOP_TOKENS.update(
    [
        "Add to Calendar",
        "Electronic Submission",
        "QUOTATION DOCUMENTS",
        "TENDER DOCUMENTS",
        "QUALIFICATION DOCUMENTS",
    ]
)


def normalize_ws(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value or "item"


def sanitize_filename(value: str) -> str:
    value = normalize_ws(value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.strip(" .")
    return value or "download"


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def unique_items(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = normalize_ws(value)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def nonempty_lines(text: str) -> list[str]:
    return [normalize_ws(line) for line in text.splitlines() if normalize_ws(line)]


def first_index(lines: list[str], needle: str) -> int:
    for idx, line in enumerate(lines):
        if line == needle:
            return idx
    return -1


def extract_value_after(lines: list[str], label: str) -> str:
    idx = first_index(lines, label)
    if idx == -1:
        return ""
    values: list[str] = []
    for line in lines[idx + 1 :]:
        if line in STOP_TOKENS:
            break
        values.append(line)
    return normalize_ws(" ".join(values))


def extract_datetime_after(lines: list[str], label: str) -> str:
    idx = first_index(lines, label)
    if idx == -1:
        return ""
    values: list[str] = []
    for line in lines[idx + 1 :]:
        if line in STOP_TOKENS:
            break
        values.append(line)
        if re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM)", line, re.I):
            break
        if len(values) >= 2:
            break
    return normalize_ws(" ".join(values))


def section_lines(lines: list[str], start: str, end_markers: list[str]) -> list[str]:
    idx = first_index(lines, start)
    if idx == -1:
        return []
    values: list[str] = []
    for line in lines[idx + 1 :]:
        if line in end_markers:
            break
        values.append(line)
    return values


def parse_title(lines: list[str]) -> str:
    overview_idx = first_index(lines, "Overview")
    if overview_idx == -1:
        return ""
    title_lines: list[str] = []
    for line in lines[overview_idx + 1 :]:
        if line in STOP_TOKENS:
            break
        title_lines.append(line)
    return normalize_ws(" ".join(title_lines))


def parse_status(lines: list[str]) -> str:
    for line in lines:
        if line in STATUS_WORDS:
            return line
    return ""


def parse_contact_block(block_lines: list[str]) -> dict[str, str]:
    cleaned = [line for line in block_lines if not line.startswith("(")]
    emails = unique_items(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ".join(cleaned)))
    phones = unique_items(
        [
            normalize_ws(line)
            for line in cleaned
            if re.fullmatch(r"(?:(?:\+65|65)\s*)?\d[\d\s-]{6,}\d", line)
        ]
    )
    name = ""
    for line in cleaned:
        if line in emails or line in phones:
            continue
        if "@" in line:
            continue
        if re.fullmatch(r"(?:(?:\+65|65)\s*)?\d[\d\s-]{6,}\d", line):
            continue
        name = line
        break
    address_parts = [
        line
        for line in cleaned
        if line
        and line != name
        and line not in emails
        and line not in phones
        and "@" not in line
    ]
    return {
        "name": name,
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "address": normalize_ws(" ".join(address_parts)),
    }


def extract_document_names(lines: list[str]) -> list[str]:
    for header in ["QUOTATION DOCUMENTS", "TENDER DOCUMENTS", "QUALIFICATION DOCUMENTS"]:
        block = section_lines(lines, header, ["WHO TO CONTACT", "PRIMARY", "SECONDARY", "AWARDING AGENCY", "CONTACT PERSON'S DETAILS"])
        if not block:
            continue
        docs: list[str] = []
        for line in block:
            if re.search(r"please log in", line, re.I):
                continue
            if re.search(r"\.(pdf|docx?|xlsx?|zip|rar|pptx?)$", line, re.I):
                docs.append(line)
        return unique_items(docs)
    return []


def parse_detail_text(text: str) -> dict[str, Any]:
    lines = nonempty_lines(text)
    primary = parse_contact_block(
        section_lines(lines, "PRIMARY", ["SECONDARY", "AWARDING AGENCY", "CONTACT PERSON'S DETAILS", "ITEMS TO RESPOND"])
    )
    secondary = parse_contact_block(
        section_lines(lines, "SECONDARY", ["AWARDING AGENCY", "CONTACT PERSON'S DETAILS", "ITEMS TO RESPOND"])
    )
    awarding_contact = parse_contact_block(section_lines(lines, "CONTACT PERSON'S DETAILS", ["ITEMS TO RESPOND"]))
    document_names = extract_document_names(lines)
    emails = unique_items(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))
    phones = unique_items(
        [
            normalize_ws(line)
            for line in lines
            if re.fullmatch(r"(?:(?:\+65|65)\s*)?\d[\d\s-]{6,}\d", line)
        ]
    )
    result = {
        "title": parse_title(lines),
        "status": parse_status(lines),
        "opportunity_no": extract_value_after(lines, "Quotation No.")
        or extract_value_after(lines, "Tender No.")
        or extract_value_after(lines, "Qualification No."),
        "reference_no": extract_value_after(lines, "Reference No."),
        "agency": extract_value_after(lines, "Agency"),
        "published": extract_datetime_after(lines, "Published"),
        "offer_validity_duration": extract_value_after(lines, "Offer Validity Duration"),
        "remarks": extract_value_after(lines, "Remarks"),
        "procurement_type": extract_value_after(lines, "Procurement Type"),
        "procurement_subtype": extract_value_after(lines, "Quotation Type")
        or extract_value_after(lines, "Tender Type"),
        "procurement_nature": extract_value_after(lines, "Procurement Nature"),
        "procurement_method": extract_value_after(lines, "Procurement Method"),
        "payment_terms": extract_value_after(lines, "Payment Terms"),
        "box_no": extract_value_after(lines, "Quotation Box No.") or extract_value_after(lines, "Tender Box No."),
        "procurement_category": extract_value_after(lines, "Procurement Category"),
        "closing": extract_datetime_after(lines, "Closed") or extract_datetime_after(lines, "Closing on"),
        "awarding_agency": extract_value_after(lines, "Awarding Agency"),
        "primary_contact_name": primary["name"],
        "primary_contact_email": primary["email"],
        "primary_contact_phone": primary["phone"],
        "primary_contact_address": primary["address"],
        "secondary_contact_name": secondary["name"],
        "secondary_contact_email": secondary["email"],
        "secondary_contact_phone": secondary["phone"],
        "secondary_contact_address": secondary["address"],
        "awarding_contact_name": awarding_contact["name"],
        "awarding_contact_email": awarding_contact["email"],
        "awarding_contact_phone": awarding_contact["phone"],
        "awarding_contact_address": awarding_contact["address"],
        "all_emails": emails,
        "all_phones": phones,
        "document_names": document_names,
        # Awarded-only — first non-empty value across the synonym labels wins
        "awarded_supplier": (
            extract_value_after(lines, "Awarded To")
            or extract_value_after(lines, "Awarded Suppliers")
            or extract_value_after(lines, "Successful Tenderer")
        ),
        "awarded_amount_raw": (
            extract_value_after(lines, "Total Awarded Amount")
            or extract_value_after(lines, "Awarded Amount")
            or extract_value_after(lines, "Awarded Sum")
            or extract_value_after(lines, "Contract Sum")
        ),
        "awarded_at": (
            extract_value_after(lines, "Awarded Date")
            or extract_value_after(lines, "Awarded On")
        ),
    }
    # Parse "S$ 12,345.67" style amounts to a numeric value + currency
    raw = result.get("awarded_amount_raw") or ""
    if raw:
        m = _PRICE_RE.search(raw)
        if m:
            try:
                result["awarded_amount"] = float(m.group(1).replace(",", ""))
            except ValueError:
                result["awarded_amount"] = None
        result["award_currency"] = "SGD" if ("S$" in raw or "SGD" in raw.upper()) else ""
    return result


def extract_document_info(page) -> list[dict[str, str]]:
    script = """
    () => {
      const sections = [...document.querySelectorAll('div.formContainer_MAIN')];
      const section = sections.find((el) => {
        const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
        return /DOCUMENTS/i.test(text) && /\\.(pdf|docx?|xlsx?|zip|rar|pptx?)\\b/i.test(text);
      });
      if (!section) return [];
      const nodes = [...section.querySelectorAll('a, span')]
        .map((n, index) => ({
          index,
          tag: n.tagName,
          text: (n.textContent || '').replace(/\\s+/g, ' ').trim(),
          href: n.tagName === 'A' ? (n.href || '') : '',
          className: n.className || '',
        }))
        .filter((item) => /\\.(pdf|docx?|xlsx?|zip|rar|pptx?)\\b/i.test(item.text))
        .filter((item) => !/DOCUMENTS|WHO TO CONTACT|PUBLISHED|PROCUREMENT|CLOSING ON|ADD TO CALENDAR/i.test(item.text))
        .filter((item) => item.text.length < 220);
      const dedup = [];
      const seen = new Set();
      for (const item of nodes) {
        const key = item.text + '|' + item.href + '|' + item.tag;
        if (seen.has(key)) continue;
        seen.add(key);
        dedup.push({
          text: item.text,
          href: item.href,
          downloadable: item.tag === 'A' && !/DISABLED/i.test(item.className),
        });
      }
      return dedup;
    }
    """
    # GeBIZ frequently triggers post-load JS navigations that destroy the JS
    # execution context mid-evaluate. We swallow ALL Playwright errors here
    # (not just timeouts) so a single bad page doesn't crash the entire scrape.
    try:
        documents = page.evaluate(script)
    except (PlaywrightTimeoutError, PlaywrightError):
        return []
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(documents, list):
        return []
    filtered: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in documents:
        text = normalize_ws(item.get("text"))
        href = normalize_ws(item.get("href"))
        downloadable = "true" if item.get("downloadable") else "false"
        key = (text, href, downloadable)
        if not text or key in seen:
            continue
        seen.add(key)
        filtered.append({"text": text, "href": href, "downloadable": downloadable})
    return filtered


def extract_award_details(page) -> dict:
    """Click the 'Award' tab on a tender detail page and parse the awarded $ + supplier.

    Empirical labels (probed against MOESCHETQ25006155 in a live Singpass session):
      'Total Awarded Value' → '13,140.00 (SGD)'
      'Awarded to' → supplier company name (lowercase 'to' — not 'To')
      'Awarded Date' → 'DD MMM YYYY' format
    The Award tab is a JSF submit button with value starting "Award" — when
    no awards exist (open tenders) the tab simply isn't present, so we no-op.
    Stays in the SAME browser context as the surrounding scrape — Singpass
    session cookies live in memory only and don't survive across Playwright
    process boundaries.
    """
    out = {"awarded_supplier": "", "awarded_amount_raw": "",
           "awarded_amount": None, "awarded_at": "", "award_currency": ""}
    try:
        tab = page.locator('input[value^="Award"]').first
        if tab.count() == 0:
            return out
        tab.click(timeout=4000)
        page.wait_for_timeout(1500)
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except (PlaywrightTimeoutError, PlaywrightError):
            pass
        text = page.locator("body").inner_text(timeout=5000)
    except (PlaywrightTimeoutError, PlaywrightError):
        return out
    except Exception:  # noqa: BLE001
        return out

    lines = nonempty_lines(text)

    # extract_value_after slurps until a known STOP_TOKEN; the award panel's
    # labels (Awarded to / Awarded Value / Awarded Items / Item No. 1 ...) are
    # not in STOP_TOKENS, so it ingests the whole line-item dump after the
    # supplier name. Award-panel fields are always single-line values, so
    # take the first non-empty line after the label and stop.
    def _first_line(label: str) -> str:
        try:
            i = lines.index(label)
        except ValueError:
            return ""
        return lines[i + 1] if i + 1 < len(lines) else ""

    out["awarded_supplier"] = _first_line("Awarded to") or _first_line("Awarded To")
    out["awarded_amount_raw"] = _first_line("Total Awarded Value") or _first_line("Awarded Value")
    out["awarded_at"] = _first_line("Awarded Date")

    raw = out["awarded_amount_raw"]
    if raw:
        m = _PRICE_RE.search(raw)
        if m:
            try:
                out["awarded_amount"] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        out["award_currency"] = "SGD" if "(SGD)" in raw or "SGD" in raw.upper() else ""
    return out


def documents_are_downloadable(page) -> bool:
    docs = extract_document_info(page)
    return any(item.get("downloadable") == "true" for item in docs)


def page_requires_login_for_documents(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2000)
    except PlaywrightTimeoutError:
        return False
    return "Please log in to view the Documents" in text


def is_logged_into_gebiz(page) -> bool:
    """Locator-based login probe — survives mid-page navigation.

    After Singpass login GeBIZ shows a "Logout" link in the global header on every
    page (and a logged-out session shows "Login" instead). Locator queries are
    routed to the latest stable DOM snapshot by Playwright, so unlike page.evaluate
    they don't blow up with "Execution context was destroyed" when GeBIZ does its
    post-load JS redirects.
    """
    selectors = [
        # Common header layouts across the trade-partner portal
        'a:has-text("Logout")',
        'a:has-text("Log Out")',
        'button:has-text("Logout")',
        'text=/^\\s*Logout\\s*$/i',
    ]
    for sel in selectors:
        try:
            if page.locator(sel).count() > 0:
                return True
        except PlaywrightError:
            continue
        except Exception:  # noqa: BLE001
            continue
    return False


def ensure_search_page(page) -> None:
    for _ in range(3):
        page.goto(BASE_URL, wait_until="domcontentloaded")
        resolve_multiple_windows(page)
        try:
            page.wait_for_selector('[id="contentForm:j_idt179_searchBar_INPUT-SEARCH"]', timeout=6000)
            page.wait_for_timeout(1000)
            return
        except PlaywrightTimeoutError:
            page.wait_for_timeout(1500)
    raise PlaywrightTimeoutError("Could not reach GeBIZ opportunities search page.")


def resolve_multiple_windows(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=1500)
    except PlaywrightTimeoutError:
        return False
    if "MULTIPLE WINDOWS" not in text:
        return False
    for selector in [
        'input[value="Continue"]',
        'button:has-text("Continue")',
        'text=Continue',
    ]:
        try:
            locator = page.locator(selector).first
            if locator.count():
                locator.click(timeout=3000)
                page.wait_for_timeout(2500)
                return True
        except Exception:
            continue
    return False


def download_documents_from_detail(page, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    resolve_multiple_windows(page)
    try:
        doc_container = page.locator(
            "xpath=//div[contains(@class,'formContainer_MAIN')][.//div[contains(@class,'formSectionHeader1_TEXT') and contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'DOCUMENTS')]]"
        ).first
        if doc_container.count() == 0:
            return []
        links = doc_container.locator("a")
        count = links.count()
    except PlaywrightTimeoutError:
        return []
    downloaded: list[str] = []
    for idx in range(count):
        link = links.nth(idx)
        try:
            text = normalize_ws(link.inner_text(timeout=1500))
        except PlaywrightTimeoutError:
            continue
        if not text or text.lower() == "log in":
            continue
        if not re.search(r"\.(pdf|docx?|xlsx?|zip|rar|pptx?)\b", text, re.I):
            continue
        try:
            with page.expect_download(timeout=4000) as download_info:
                link.click()
            download = download_info.value
            filename = sanitize_filename(download.suggested_filename or "")
            text_filename = sanitize_filename(text)
            if not filename or UUID_RE.fullmatch(filename) or "." not in filename:
                filename = text_filename
            elif UUID_RE.fullmatch(Path(filename).stem) and "." in text_filename:
                filename = text_filename
            target = destination / filename
            suffix = 2
            while target.exists():
                stem = target.stem
                ext = target.suffix
                target = destination / f"{stem}-{suffix}{ext}"
                suffix += 1
            download.save_as(str(target))
            try:
                download.delete()
            except Exception:
                pass
            downloaded.append(str(target))
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return downloaded


_TAB_COUNT_RE = re.compile(r'(Open|Closed|All)\s*\(\s*(\d+)\s*\)', re.I)
_MASTER_COUNT_RE = re.compile(r'(\d+)\s+opportunit(?:y|ies)\s+found', re.I)


def _read_tab_counts(page) -> dict[str, int]:
    """Capture result counts from the BOListing search-results header.

    Two signals on the page, only one always present:
      - "Open (N) / Closed (M) / All (X)" tab labels — appear ONLY when the
        OPEN tab has matches (otherwise GeBIZ hides the tab bar entirely).
      - "X opportunities found for your search '...'" — always present, the
        master result count across both tabs.
    We capture both so the caller can tell "0 anywhere" from "0 open + N
    closed" — the latter triggers a /scrape_awarded suggestion.
    """
    out = {"open": 0, "closed": 0, "all": 0, "master": 0}
    try:
        text = page.locator("body").inner_text(timeout=2000)
    except (PlaywrightTimeoutError, PlaywrightError):
        return out
    except Exception:  # noqa: BLE001
        return out
    for m in _TAB_COUNT_RE.finditer(text):
        out[m.group(1).lower()] = int(m.group(2))
    m = _MASTER_COUNT_RE.search(text)
    if m:
        out["master"] = int(m.group(1))
    return out


def search_keyword(
    page,
    keyword: str,
    limit: int,
    days_filter: str,
    *,
    awarded_only: bool = False,
    out_tab_counts: dict | None = None,
) -> list[dict[str, str]]:
    ensure_search_page(page)
    resolve_multiple_windows(page)
    if awarded_only:
        # GeBIZ's BOListing page renders "Open (N)" / "Closed (M)" tabs above
        # results — Closed includes awarded tenders with their final price.
        # Try a few selector variants because the tab label sometimes carries
        # the count inline ("Closed (40)").
        for sel in ('text=/^Closed\\s*\\(/i', 'text=/^Closed$/i', 'a:has-text("Closed")', 'button:has-text("Closed")'):
            try:
                tab = page.locator(sel).first
                if tab.count():
                    tab.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    break
            except (PlaywrightTimeoutError, PlaywrightError):
                continue
            except Exception:  # noqa: BLE001
                continue
    if days_filter in {"2", "7"}:
        label = "Past 2 days" if days_filter == "2" else "Past 7 days"
        try:
            shortcut = page.get_by_text(re.compile(rf"^{re.escape(label)}", re.I)).first
            if shortcut.count():
                shortcut.click(timeout=4000)
                page.wait_for_timeout(1500)
        except PlaywrightTimeoutError:
            pass
    search_input = page.locator('[id="contentForm:j_idt179_searchBar_INPUT-SEARCH"]')
    go_button = page.locator('[id="contentForm:j_idt179_searchBar_BUTTON-GO"]')
    search_input.fill("")
    page.wait_for_timeout(250)
    search_input.fill(keyword)
    go_button.click()
    page.wait_for_timeout(2500)
    # Capture tab counts immediately after search so we know whether 0 results
    # means "nothing matched" or "matched but all closed/awarded".
    if out_tab_counts is not None:
        out_tab_counts.update(_read_tab_counts(page))
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    previous_first_title = ""
    while len(results) < limit:
        anchors = page.locator("a.commandLink_TITLE-BLUE")
        count = anchors.count()
        for idx in range(count):
            anchor = anchors.nth(idx)
            title = normalize_ws(anchor.inner_text())
            href = normalize_ws(anchor.get_attribute("href"))
            if not title or not href:
                continue
            absolute_url = urljoin("https://www.gebiz.gov.sg", href)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            results.append({"keyword": keyword, "title": title, "url": absolute_url})
            if len(results) >= limit:
                break
        next_button = page.locator('input[value="Next"]').first
        if len(results) >= limit or next_button.count() == 0 or next_button.is_disabled():
            break
        current_first_title = normalize_ws(anchors.first.inner_text()) if count else ""
        if current_first_title and current_first_title == previous_first_title:
            break
        previous_first_title = current_first_title
        next_button.click()
        page.wait_for_timeout(2000)
    return results[:limit]


def write_outputs(records: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"gebiz-opportunities-{timestamp}.json"
    csv_path = output_dir / f"gebiz-opportunities-{timestamp}.csv"
    json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    csv_fields = [
        "matched_keyword",
        "title",
        "status",
        "opportunity_no",
        "reference_no",
        "agency",
        "published",
        "closing",
        "procurement_type",
        "procurement_subtype",
        "procurement_category",
        "primary_contact_name",
        "primary_contact_email",
        "primary_contact_phone",
        "secondary_contact_name",
        "secondary_contact_email",
        "secondary_contact_phone",
        "awarding_contact_name",
        "awarding_contact_email",
        "awarding_contact_phone",
        "all_emails",
        "all_phones",
        "detail_url",
        "document_count",
        "downloaded_files",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "matched_keyword": record.get("matched_keyword", ""),
                    "title": record.get("title", ""),
                    "status": record.get("status", ""),
                    "opportunity_no": record.get("opportunity_no", ""),
                    "reference_no": record.get("reference_no", ""),
                    "agency": record.get("agency", ""),
                    "published": record.get("published", ""),
                    "closing": record.get("closing", ""),
                    "procurement_type": record.get("procurement_type", ""),
                    "procurement_subtype": record.get("procurement_subtype", ""),
                    "procurement_category": record.get("procurement_category", ""),
                    "primary_contact_name": record.get("primary_contact_name", ""),
                    "primary_contact_email": record.get("primary_contact_email", ""),
                    "primary_contact_phone": record.get("primary_contact_phone", ""),
                    "secondary_contact_name": record.get("secondary_contact_name", ""),
                    "secondary_contact_email": record.get("secondary_contact_email", ""),
                    "secondary_contact_phone": record.get("secondary_contact_phone", ""),
                    "awarding_contact_name": record.get("awarding_contact_name", ""),
                    "awarding_contact_email": record.get("awarding_contact_email", ""),
                    "awarding_contact_phone": record.get("awarding_contact_phone", ""),
                    "all_emails": "; ".join(record.get("all_emails", [])),
                    "all_phones": "; ".join(record.get("all_phones", [])),
                    "detail_url": record.get("detail_url", ""),
                    "document_count": len(record.get("documents", [])),
                    "downloaded_files": "; ".join(record.get("downloaded_files", [])),
                }
            )
    return json_path, csv_path


def run_search(
    keywords: list[str],
    output_dir: "str | Path",
    *,
    limit_per_keyword: int = 8,
    max_total: int = 40,
    profile_dir: "str | Path" = "tmp/gebiz_profile",
    days_filter: str = "7",
    headless: bool = True,
    skip_downloads: bool = True,
    wait_for_login_seconds: int = 0,
    on_login_state: "callable | None" = None,
    awarded_only: bool = False,
) -> dict:
    """Importable entry point. Returns {records, json_path, csv_path}.

    Sync — wrap in asyncio.to_thread from FastAPI handlers.

    Args:
        wait_for_login_seconds: If > 0, opens a non-headless browser, navigates to a
            Singpass-gated doc page, and polls for download access every 3s. Forces
            headless=False so the user can scan Singpass QR manually. Once access is
            detected OR the timeout hits, proceeds with the keyword search loop.
            Combine with skip_downloads=False to actually download tender PDFs.
        on_login_state: Optional callback(state: str) invoked at state transitions:
            'browser_open', 'login_detected', 'login_timeout'. Useful for DM updates.
    """
    keywords = unique_items([k for k in keywords if normalize_ws(k)])
    output_dir = Path(output_dir).resolve()
    profile_dir = Path(profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Singpass login requires a visible browser window
    effective_headless = headless and wait_for_login_seconds <= 0

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=effective_headless,
            accept_downloads=True,
            downloads_path=str(output_dir / "downloads"),
        )
        page = context.pages[0] if context.pages else context.new_page()
        for extra_page in context.pages[1:]:
            try:
                extra_page.close()
            except Exception:
                pass

        if wait_for_login_seconds > 0:
            # Singpass handoff: open GeBIZ home so the user can sign in. We poll the
            # SAME tab (the user's tab) for a "Logout" link via Playwright locators,
            # which queries the latest DOM snapshot and never crashes with
            # "Execution context was destroyed" mid-navigation.
            page.goto("https://www.gebiz.gov.sg/", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            if on_login_state:
                try: on_login_state("browser_open")
                except Exception: pass
            login_deadline = time.time() + wait_for_login_seconds
            logged_in = False
            while time.time() < login_deadline:
                try:
                    if is_logged_into_gebiz(page):
                        logged_in = True
                        if on_login_state:
                            try: on_login_state("login_detected")
                            except Exception: pass
                        break
                except Exception:
                    # Swallow any transient errors; next tick will retry
                    pass
                time.sleep(3)
            if not logged_in and on_login_state:
                try: on_login_state("login_timeout")
                except Exception: pass
            ensure_search_page(page)
        else:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

        matches: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        tab_counts_per_keyword: dict[str, dict[str, int]] = {}
        for keyword in keywords:
            tc: dict[str, int] = {}
            keyword_matches = search_keyword(
                page, keyword, limit_per_keyword, days_filter,
                awarded_only=awarded_only, out_tab_counts=tc,
            )
            tab_counts_per_keyword[keyword] = tc
            for match in keyword_matches:
                if match["url"] in seen_urls:
                    continue
                seen_urls.add(match["url"])
                matches.append(match)
                if len(matches) >= max_total:
                    break
            if len(matches) >= max_total:
                break

        records: list[dict[str, Any]] = []
        downloads_root = output_dir / "downloads"
        snapshots_root = Path.home() / ".beepbop" / "snapshots"
        snapshots_root.mkdir(parents=True, exist_ok=True)
        for index, match in enumerate(matches, start=1):
            # Per-page try/except — a single Playwright crash (e.g. "Execution
            # context was destroyed" mid-evaluate) must NOT take down the
            # scrape. We log a stub record and move on.
            try:
                page.goto(match["url"], wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                resolve_multiple_windows(page)
                try:
                    body_text = page.locator("body").inner_text(timeout=5000)
                except (PlaywrightTimeoutError, PlaywrightError):
                    body_text = ""
                parsed = parse_detail_text(body_text)
                documents = extract_document_info(page)
                if not parsed.get("title"):
                    parsed["title"] = match["title"]
                if not documents and parsed.get("document_names"):
                    documents = [{"text": name, "href": ""} for name in parsed["document_names"]]
                # IMPORTANT: download docs BEFORE clicking the Award tab, because
                # the JSF tab switch hides the QUOTATION DOCUMENTS container.
                # download_documents_from_detail relies on that container being
                # in the DOM, and it's a no-op (returns []) if the tab moved.
                downloaded_files: list[str] = []
                if documents and not skip_downloads:
                    doc_dir = downloads_root / f"{index:03d}-{slugify(parsed.get('opportunity_no') or parsed.get('title') or 'documents')}"
                    try:
                        downloaded_files = download_documents_from_detail(page, doc_dir)
                    except (PlaywrightTimeoutError, PlaywrightError):
                        downloaded_files = []
                # Award details live on a separate JSF tab on the SAME page — click
                # AFTER downloads since the click hides the documents section.
                if (parsed.get("status") in ("AWARDED", "PENDING AWARD")) or awarded_only:
                    award_info = extract_award_details(page)
                    parsed.update({k: v for k, v in award_info.items() if v not in (None, "")})
                # Snapshot the detail page — persistent across scrape runs, per-opp
                snapshot_path = ""
                try:
                    slug = slugify(parsed.get("opportunity_no") or parsed.get("title") or f"opp{index}")[:60]
                    out = snapshots_root / f"{slug}.png"
                    page.screenshot(path=str(out), full_page=True, timeout=15000)
                    snapshot_path = str(out)
                except Exception:
                    pass
                parsed.update(
                    {
                        "matched_keyword": match["keyword"],
                        "detail_url": match["url"],
                        "documents": documents,
                        "downloaded_files": downloaded_files,
                        "snapshot_path": snapshot_path,
                    }
                )
                records.append(parsed)
            except Exception as page_err:  # noqa: BLE001
                records.append(
                    {
                        "title": match.get("title", ""),
                        "matched_keyword": match.get("keyword", ""),
                        "detail_url": match.get("url", ""),
                        "documents": [],
                        "downloaded_files": [],
                        "snapshot_path": "",
                        "scrape_error": str(page_err)[:300],
                    }
                )

        json_path, csv_path = write_outputs(records, output_dir)
        context.close()
    return {
        "records": records,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "tab_counts_per_keyword": tab_counts_per_keyword,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GeBIZ opportunity contacts and documents.")
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated keywords to search.",
    )
    parser.add_argument(
        "--limit-per-keyword",
        type=int,
        default=8,
        help="Maximum result rows to inspect per keyword.",
    )
    parser.add_argument(
        "--max-total",
        type=int,
        default=40,
        help="Maximum total detail pages to scrape after deduplication.",
    )
    parser.add_argument(
        "--output-dir",
        default="tmp/gebiz_contacts",
        help="Directory for CSV/JSON output and downloaded files.",
    )
    parser.add_argument(
        "--profile-dir",
        default="tmp/gebiz_profile",
        help="Persistent Chrome profile directory for GeBIZ login state.",
    )
    parser.add_argument(
        "--days-filter",
        choices=["all", "2", "7"],
        default="7",
        help="Optional published-date shortcut to click before searching.",
    )
    parser.add_argument(
        "--wait-for-login",
        action="store_true",
        help="Pause after opening the browser so you can log in manually.",
    )
    parser.add_argument(
        "--skip-downloads",
        action="store_true",
        help="Do not attempt to download any attached documents.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless. Do not use this with --wait-for-login.",
    )
    parser.add_argument(
        "--validate-doc-url",
        default=DEFAULT_VALIDATE_DOC_URL,
        help="Document page used to verify that login really enables downloads.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.headless and args.wait_for_login:
        print("--headless cannot be used with --wait-for-login", file=sys.stderr)
        return 2

    keywords = unique_items([value for value in args.keywords.split(",") if normalize_ws(value)])
    output_dir = Path(args.output_dir).resolve()
    profile_dir = Path(args.profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=args.headless,
            accept_downloads=True,
            downloads_path=str(output_dir / "downloads"),
        )
        page = context.pages[0] if context.pages else context.new_page()
        for extra_page in context.pages[1:]:
            try:
                extra_page.close()
            except Exception:
                pass
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        if args.wait_for_login:
            print("")
            print("Chrome opened for GeBIZ.")
            while True:
                print("Log in there yourself. After login is complete, return here and press Enter.")
                input()
                page.goto(args.validate_doc_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                resolve_multiple_windows(page)
                if documents_are_downloadable(page):
                    print("Login validation passed. Document link is active.")
                    break
                if page_requires_login_for_documents(page):
                    print("Login validation failed. GeBIZ still shows document access as logged out.")
                    print("Use the same Chrome window, complete login there, then press Enter again.")
                    continue
                print("Login validation inconclusive. Proceeding with current session.")
                break
            ensure_search_page(page)

        matches: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for keyword in keywords:
            keyword_matches = search_keyword(page, keyword, args.limit_per_keyword, args.days_filter)
            for match in keyword_matches:
                if match["url"] in seen_urls:
                    continue
                seen_urls.add(match["url"])
                matches.append(match)
                if len(matches) >= args.max_total:
                    break
            if len(matches) >= args.max_total:
                break

        records: list[dict[str, Any]] = []
        downloads_root = output_dir / "downloads"
        for index, match in enumerate(matches, start=1):
            page.goto(match["url"], wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            resolve_multiple_windows(page)
            parsed = parse_detail_text(page.locator("body").inner_text())
            documents = extract_document_info(page)
            if not parsed.get("title"):
                parsed["title"] = match["title"]
            if not documents and parsed.get("document_names"):
                documents = [{"text": name, "href": ""} for name in parsed["document_names"]]
            downloaded_files: list[str] = []
            if documents and not args.skip_downloads:
                doc_dir = downloads_root / f"{index:03d}-{slugify(parsed.get('opportunity_no') or parsed.get('title') or 'documents')}"
                downloaded_files = download_documents_from_detail(page, doc_dir)
            parsed.update(
                {
                    "matched_keyword": match["keyword"],
                    "detail_url": match["url"],
                    "documents": documents,
                    "downloaded_files": downloaded_files,
                }
            )
            records.append(parsed)
            print(
                f"[{index}/{len(matches)}] {parsed.get('opportunity_no') or 'NO-CODE'} | "
                f"{parsed.get('title') or match['title']}"
            )

        json_path, csv_path = write_outputs(records, output_dir)
        print("")
        print(f"Saved {len(records)} records.")
        print(f"CSV:  {csv_path}")
        print(f"JSON: {json_path}")
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
