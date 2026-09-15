# INFORM → Apple Calendar automatikus szinkron

Ez a mini-projekt naponta egyszer bejelentkezik az ELTE GTK INFORM felületére,
kiolvassa az ÓRAREND táblázatot, leszűri a B csoportnak megfelelő órákra
(az előadásokból csak azokat tartja meg, ahol a csoportjelölésben szerepel a
"B" betű; a szemináriumokat mind megtartja), és generál belőle egy
`docs/orarend.ics` fájlt. Ezt a fájlt a GitHub Pages szolgálja ki egy állandó
URL-en, amire az Apple Calendar (vagy bármelyik más naptáralkalmazás) elő tud
fizetni — onnantól a naptárad tényleg magától frissül.

## 1. Repo létrehozása

1. Hozz létre egy **privát** GitHub repót (pl. `orarend-sync`).
2. Töltsd fel bele ennek a mappának a tartalmát (a `.github/workflows` mappát
   is, azzal együtt).

> Privátnak érdemes hagyni a repót — a kód maga nem tartalmaz jelszót, de
> így kevesebb kíváncsi szem látja, hogy pontosan milyen scriptet futtatsz.

## 2. Titkos adatok beállítása (GitHub Secrets)

A repóban: **Settings → Secrets and variables → Actions → New repository secret**

Hozz létre két secretet:

| Név | Érték |
|---|---|
| `INFORM_USER` | a IIG (caesar) azonosítód |
| `INFORM_PASS` | a IIG jelszavad |

Ezeket a GitHub titkosítva tárolja, a workflow futása közben csak
környezeti változóként érhetők el — a kódban sehol nincsenek kiírva vagy
logolva.

## 3. GitHub Pages bekapcsolása

**Settings → Pages** → Source: `Deploy from a branch` → Branch: `main`,
mappa: `/docs`.

Ez adja majd az .ics fájl állandó URL-jét, valahogy így:

```
https://<felhasználóneved>.github.io/<repónév>/orarend.ics
```

(Az első futás után jelenik meg ténylegesen a fájl — lásd 4. pont.)

## 4. Az automatikus futás kipróbálása

A workflow naponta 6:00 UTC-kor fut automatikusan, de az **Actions** fülön
a `Órarend frissítése` workflow-nál a `Run workflow` gombbal bármikor
kézzel is elindíthatod — érdemes ezzel tesztelni először.

Ha a bejelentkezés vagy az adatkiolvasás nem sikerül, a workflow hibával
leáll, és feltölt egy `debug` nevű artifact-ot (képernyőkép + HTML az adott
pillanatról) — ezt letöltve tudjuk közösen kideríteni, mit kell javítani a
scripten.

## 5. Feliratkozás az Apple Calendarban

Ha megvan a működő .ics URL:

1. iPhone-on: **Beállítások → Naptár → Fiókok → Fiók hozzáadása → Egyéb →
   Előfizetett naptár**
2. A "Kiszolgáló" mezőbe illeszd be a fenti URL-t (a `https://`-t nem kell
   `webcal://`-ra cserélni, mindkettő működik).
3. Mentés.

Az iOS ezután rendszeres időközönként (jellemzően napi szinten) újra
lekérdezi az URL-t, és frissíti a naptáradban lévő órákat.

## Karbantartás

Ha az INFORM felülete megváltozik (más HTML szerkezet, más menüpont-nevek),
a `scrape_and_generate_ics.py` scriptben a `scrape_rows` és `login`
függvényeket kell hozzáigazítani az új felülethez. Küldd el az új
képernyőképeket / a debug artifactot, és újra tudjuk igazítani.

## Csoport módosítása

Ha váltanál csoportot, a `.github/workflows/update.yml` fájlban a
`TARGET_GROUP: "B"` sort kell átírni a megfelelő betűre.
