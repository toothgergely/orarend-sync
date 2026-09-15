#!/usr/bin/env python3
"""
ELTE GTK INFORM -> .ics generator

Bejelentkezik a https://inform.gtk.elte.hu oldalra a központi IIG (idp.elte.hu)
SSO-n keresztül, kiolvassa az ÓRAREND táblázatot, leszűri a B csoportnak
megfelelő előadásokra (a szemináriumokat mind megtartja), és generál belőle
egy .ics naptárfájlt, amire az Apple/Google Calendar elő tud fizetni.

Env változók (GitHub Secrets-ből jönnek a CI-ban):
    INFORM_USER  - IIG (caesar) azonosító
    INFORM_PASS  - IIG jelszó
    TARGET_GROUP - szűrendő csoport betűjele (alapértelmezés: "B")

Kimenet:
    docs/orarend.ics  (ezt szolgálja ki a GitHub Pages)
"""

import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INFORM_HOME = "https://inform.gtk.elte.hu/"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "orarend.ics")
TZ = ZoneInfo("Europe/Budapest")

TARGET_GROUP = os.environ.get("TARGET_GROUP", "B")


def log(msg):
    print(f"[inform-sync] {msg}", flush=True)


def login(page):
    """Bejelentkezés az IIG SSO-n keresztül."""
    log("Megnyitom az INFORM kezdőoldalát")
    page.goto(INFORM_HOME, wait_until="networkidle")

    # "IIG BELÉPÉS" link a jobb felső sarokban
    log("Kattintok az IIG BELÉPÉS linkre")
    page.get_by_text("IIG BELÉPÉS", exact=False).click()

    # A központi login oldal (idp.elte.hu) betöltésére várunk.
    # A form mezői a screenshot alapján "IIG (caesar) ID" és "Password" címkéjűek.
    page.wait_for_load_state("networkidle")

    user = os.environ["INFORM_USER"]
    pwd = os.environ["INFORM_PASS"]

    # Több lehetséges selectort is kipróbálunk, mert a pontos HTML-t nem láttuk,
    # csak a képernyőképet.
    filled_user = False
    for selector in [
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[type='text']",
    ]:
        try:
            page.locator(selector).first.fill(user, timeout=3000)
            filled_user = True
            break
        except PWTimeout:
            continue
    if not filled_user:
        # végső próbálkozás: az első szövegmező a formban
        page.locator("form input[type='text'], form input:not([type])").first.fill(user)

    filled_pass = False
    for selector in [
        "input[name*='pass' i]",
        "input[id*='pass' i]",
        "input[type='password']",
    ]:
        try:
            page.locator(selector).first.fill(pwd, timeout=3000)
            filled_pass = True
            break
        except PWTimeout:
            continue
    if not filled_pass:
        page.locator("input[type='password']").first.fill(pwd)

    log("Beküldöm a bejelentkezési űrlapot")
    clicked = False
    for selector in [
        "button:has-text('Login')",
        "input[type='submit']",
        "button[type='submit']",
    ]:
        try:
            page.locator(selector).first.click(timeout=3000)
            clicked = True
            break
        except PWTimeout:
            continue
    if not clicked:
        page.keyboard.press("Enter")

    page.wait_for_load_state("networkidle")

    if "idp.elte.hu" in page.url:
        raise RuntimeError(
            "A bejelentkezés valószínűleg nem sikerült (még mindig az idp.elte.hu "
            "oldalon vagyunk). Ellenőrizd az INFORM_USER / INFORM_PASS secreteket, "
            "vagy hogy nem kér-e extra megerősítést a login."
        )
    log("Sikeres bejelentkezés, vissza az INFORM-on")


def open_orarend(page):
    log("Megnyitom az ÓRAREND menüpontot")
    page.get_by_text("ÓRAREND", exact=False).click()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("table")


HU_DAYS = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]

ROOM_LOCATION = {
    "MT": "Gólyavár, Budapest, Múzeum krt. 4.",
    "PP": "Gólyavár, Budapest, Múzeum krt. 4.",
}


def scrape_rows(page):
    """A lila ÓRAREND táblázat sorainak kiolvasása."""
    rows = []
    table_rows = page.locator("table tr")
    count = table_rows.count()
    log(f"{count} táblázatsort találtam (a fejléccel együtt)")

    for i in range(count):
        row = table_rows.nth(i)
        cells = row.locator("td")
        n = cells.count()
        if n < 5:
            continue  # fejléc sor vagy üres sor

        texts = [cells.nth(j).inner_text().strip() for j in range(n)]
        # Elvárt oszlopok: Nap | Idősáv | Tárgynév(+kód) | Kurzustípus(+csoport+kód) | Tanterem | Oktatók
        if len(texts) < 5:
            continue

        date_str = texts[0].strip()
        if not re.match(r"\d{4}\.\d{2}\.\d{2}", date_str):
            continue  # nem adatsor

        time_str = texts[1].strip()

        subject_block = texts[2]
        subject_lines = [l.strip() for l in subject_block.split("\n") if l.strip()]
        subject = subject_lines[0].replace(" (BSc)", "").replace(" (BSC)", "")
        tantargykod = subject_lines[1] if len(subject_lines) > 1 else ""

        type_block = texts[3]
        type_lines = [l.strip() for l in type_block.split("\n") if l.strip()]
        ctype = type_lines[0] if type_lines else ""
        # A csoport (pl. "A, D") és a kurzuskód (pl. "SzV1-MEX") a maradék sorokban van.
        group = ""
        kurzuskod = ""
        rest = type_lines[1:]
        for line in rest:
            if re.match(r"^[A-L](\s*,\s*[A-L])*$", line.replace(" ", "").replace(",", ", ")) or \
               re.match(r"^[A-L](,[A-L])*$", line.replace(" ", "")):
                group = line
            else:
                kurzuskod = line
        if not kurzuskod and rest:
            kurzuskod = rest[-1]
            if len(rest) > 1:
                group = rest[0]

        room = texts[4].strip() if len(texts) > 4 else ""
        teacher = texts[5].strip() if len(texts) > 5 else ""

        try:
            d = datetime.strptime(date_str, "%Y.%m.%d")
        except ValueError:
            continue

        rows.append({
            "date": d,
            "weekday": HU_DAYS[d.weekday()],
            "time": time_str,
            "subject": subject,
            "tantargykod": tantargykod,
            "ctype": ctype,
            "group": group,
            "kurzuskod": kurzuskod,
            "room": room,
            "teacher": teacher,
        })

    return rows


def group_has_target(group, target):
    if not group:
        return True  # nincs csoportmegkötés -> mindenkinek szól
    tokens = re.split(r"[,\s]+", group.strip())
    tokens = [t for t in tokens if t]
    return target in tokens


def filter_rows(rows, target_group):
    out = []
    for r in rows:
        is_sz = r["ctype"].lower().startswith("szeminárium")
        if is_sz or group_has_target(r["group"], target_group):
            out.append(r)
    out.sort(key=lambda r: (r["date"], r["time"]))
    return out


def ics_escape(text):
    return (text or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


VTIMEZONE_BUDAPEST = """BEGIN:VTIMEZONE
TZID:Europe/Budapest
X-LIC-LOCATION:Europe/Budapest
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def build_ics(rows, target_group):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//inform-sync//orarend//HU",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:Egyetemi órák ({target_group} csoport)",
        "X-WR-TIMEZONE:Europe/Budapest",
        VTIMEZONE_BUDAPEST,
    ]

    now_stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")

    for r in rows:
        try:
            start_str, end_str = r["time"].replace("–", "-").split("-")
        except ValueError:
            continue
        start_str = start_str.strip()
        end_str = end_str.strip()
        dt_start = f"{r['date'].strftime('%Y%m%d')}T{start_str.replace(':', '')}00"
        dt_end = f"{r['date'].strftime('%Y%m%d')}T{end_str.replace(':', '')}00"

        title = f"{r['subject']} – {r['ctype']}"
        location = r["room"]
        addr = ROOM_LOCATION.get(r["room"], "")
        if addr:
            location = f"{r['room']}, {addr}"

        desc_parts = [r["tantargykod"], r["kurzuskod"]]
        if r["group"]:
            desc_parts.append(f"Csoport: {r['group']}")
        desc_parts.append(f"Oktató: {r['teacher']}")
        description = " | ".join(p for p in desc_parts if p)

        uid_source = f"{r['date'].strftime('%Y%m%d')}-{start_str}-{r['tantargykod']}-{r['ctype']}"
        uid = re.sub(r"[^A-Za-z0-9]+", "-", uid_source).strip("-") + "@inform-sync"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;TZID=Europe/Budapest:{dt_start}",
            f"DTEND;TZID=Europe/Budapest:{dt_end}",
            f"SUMMARY:{ics_escape(title)}",
            f"LOCATION:{ics_escape(location)}",
            f"DESCRIPTION:{ics_escape(description)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            login(page)
            open_orarend(page)
            rows = scrape_rows(page)
        except Exception:
            # hibakereséshez mentünk egy screenshotot és a HTML-t is
            os.makedirs("debug", exist_ok=True)
            try:
                page.screenshot(path="debug/failure.png", full_page=True)
                with open("debug/failure.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                log("Hiba történt — mentettem egy debug/failure.png és debug/failure.html fájlt")
            except Exception:
                pass
            raise
        finally:
            browser.close()

    if not rows:
        raise RuntimeError("Nem sikerült egyetlen órát sem kiolvasni a táblázatból — "
                            "valószínűleg megváltozott az oldal szerkezete.")

    log(f"{len(rows)} sort olvastam ki összesen")
    filtered = filter_rows(rows, TARGET_GROUP)
    log(f"{len(filtered)} sor maradt a szűrés után ({TARGET_GROUP} csoport + összes szeminárium)")

    ics_content = build_ics(filtered, TARGET_GROUP)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(ics_content)

    log(f"Kiírva: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
