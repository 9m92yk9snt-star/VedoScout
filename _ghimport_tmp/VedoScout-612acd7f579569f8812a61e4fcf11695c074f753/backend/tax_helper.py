"""tax_helper.py — Danish tax helper (Skat-hjælper) for the admin panel.

Income is pulled automatically from paid Stripe transactions (USD → DKK via
Nationalbank-aligned ECB daily rates, cached in Mongo). Expenses are entered
manually with optional receipt images. Produces a yearly summary, VAT
(moms) overview and CSV/PDF exports. Guidance text targets a CVR-registered
sole proprietorship (enkeltmandsvirksomhed). NOT professional tax advice.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import r2_storage

logger = logging.getLogger("tax_helper")

EXPENSE_COLL = "tax_expenses"
FX_COLL = "fx_rates"
FALLBACK_USD_DKK = 6.50
RECEIPT_EXTS = {"jpg", "jpeg", "png", "webp", "pdf", "heic"}

CATEGORIES = {
    "hosting": "Hosting & drift",
    "ai": "AI-forbrug",
    "domain": "Domæne & DNS",
    "software": "Software & værktøjer",
    "marketing": "Markedsføring",
    "equipment": "Udstyr",
    "other": "Andet",
}

KIND_LABELS = {
    "prepay_upload": "Forudbetalt upload",
    "report_unlock": "Rapport-køb",
    "subscription": "Abonnement",
    "scout_access": "Scout-adgang",
}

GUIDE_STEPS = [
    {
        "title": "1. Bogføring — det klarer denne side",
        "body": "Alle indtægter hentes automatisk fra Stripe. Udgifter taster du ind ovenfor — eller endnu nemmere: "
                "eksportér dit kontoudtog fra Revolut Business som CSV og brug 'Importér fra Revolut', så er det få klik. "
                "Upload kvitteringer her — bogføringsloven kræver 5 års opbevaring.",
    },
    {
        "title": "2. Moms — hvert kvartal via TastSelv Erhverv",
        "body": "Du indberetter kvartalsvis. Sådan gør du: 1) Log ind på skat.dk/erhverv med MitID → vælg 'Moms'. "
                "2) Tast tallene fra kvartals-boksen ovenfor: Salgsmoms i feltet 'Salgsmoms (udgående moms)', købsmoms i "
                "'Købsmoms (indgående moms)'. 3) Godkend — momstilsvaret er det beløb du skal betale. "
                "Frister: 1. kvt. → 1. juni · 2. kvt. → 1. september · 3. kvt. → 1. december · 4. kvt. → 1. marts. "
                "OBS: Salgsmoms-tallene her antager danske kunder. Har du mange kunder i andre EU-lande kan OSS-ordningen være "
                "relevant — ring gratis til Skattestyrelsen på 72 22 18 18, de hjælper med præcis dét.",
    },
    {
        "title": "3. Skat af årets resultat — oplysningsskema",
        "body": "Årets resultat (indtægter minus udgifter) skrives i dit oplysningsskema på skat.dk: "
                "overskud i rubrik 111, underskud i rubrik 112. Frist: 1. juli året efter indkomståret. "
                "Download PDF-rapporten fra denne side og gem den som dokumentation — så har du alt på ét sted.",
    },
    {
        "title": "4. Forskudsopgørelse — undgå restskat",
        "body": "Opdater din forskudsopgørelse på skat.dk med det forventede overskud (felt 221), "
                "så du betaler B-skat løbende i stedet for at få en restskat-regning.",
    },
    {
        "title": "5. Opstartsudgifter",
        "body": "Udgifter afholdt for at starte virksomheden (fx udvikling af ScoutMePlay) kan som udgangspunkt "
                "fratrækkes, når de er afholdt i tilknytning til opstarten — gem al dokumentation. "
                "Er du i tvivl om en konkret udgift, så ring til Skattestyrelsen på 72 22 18 18 — det er gratis.",
    },
]

DISCLAIMER = ("Vejledende værktøj — ikke professionel skatterådgivning. "
              "Er du i tvivl, så ring gratis til Skattestyrelsen på 72 22 18 18.")


# ===== Revolut Business CSV import =====

CATEGORY_KEYWORDS = {
    "hosting": ["emergent", "aws", "amazon web", "hetzner", "digitalocean", "cloudflare", "vercel", "railway", "render", "one.com", "simply"],
    "ai": ["openai", "anthropic", "gemini", "elevenlabs", "google cloud", "replicate", "fal.ai"],
    "domain": ["godaddy", "namecheap", "dk hostmaster", "gratisdns", "domain", "punktum"],
    "marketing": ["facebook", "meta plat", "google ads", "tiktok", "instagram", "linkedin", "mailchimp"],
    "software": ["adobe", "figma", "canva", "notion", "github", "apple.com/bill", "microsoft", "dropbox", "zoom"],
}


def _suggest_category(description: str) -> str:
    d = (description or "").lower()
    for cat, words in CATEGORY_KEYWORDS.items():
        if any(w in d for w in words):
            return cat
    return "other"


def _num(s) -> float | None:
    s = str(s or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return None
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    s = str(s or "").strip()
    for cand in (s, s[:19], s[:16], s[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                    "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(cand, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _parse_revolut_csv(data: bytes) -> list[dict]:
    """Tolerant parser for Revolut (Business & personal) CSV statements.
    Returns money-OUT rows as expense candidates."""
    text = data.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = {(h or "").lower().strip(): h for h in (reader.fieldnames or [])}

    def col(*names):
        for n in names:
            if n in headers:
                return headers[n]
        return None

    c_date = col("date completed (utc)", "completed date", "date completed", "date started (utc)", "started date", "date")
    c_desc = col("description", "reference", "payee", "beneficiary")
    c_amount = col("amount", "total amount")
    c_cur = col("payment currency", "currency")
    c_state = col("state")
    c_fee = col("fee")
    if not (c_date and c_amount):
        raise HTTPException(400, "Kunne ikke genkende kolonnerne i filen — eksportér kontoudtoget som CSV (Statement → Excel/CSV) fra Revolut og prøv igen")

    rows = []
    for r in reader:
        if c_state and str(r.get(c_state, "")).strip().lower() not in ("completed", "complete", ""):
            continue
        amt = _num(r.get(c_amount))
        if amt is None or amt >= 0:
            continue
        date = _parse_date(r.get(c_date))
        if not date:
            continue
        fee = abs(_num(r.get(c_fee)) or 0) if c_fee else 0.0
        desc = str(r.get(c_desc, "") or "").strip()[:200]
        cur = str(r.get(c_cur, "") or "DKK").strip().upper() or "DKK"
        rows.append({
            "date": date,
            "description": desc,
            "orig_amount": round(abs(amt) + fee, 2),
            "currency": cur,
        })
        if len(rows) >= 500:
            break
    return rows


class RevolutRow(BaseModel):
    hash: str
    date: str
    amount_dkk: float
    category: str = "other"
    note: str = ""
    vat_included: bool = False


class RevolutImportPayload(BaseModel):
    rows: list[RevolutRow]


def _month_key(iso: str) -> int:
    try:
        return int(iso[5:7])
    except (ValueError, TypeError, IndexError):
        return 0


async def _rate_to_dkk(db, date_str: str, currency: str) -> tuple[float, str]:
    """Daily {currency}→DKK rate (ECB via frankfurter.dev), cached in Mongo.
    Returns (rate, source). Falls back to newest cached rate, then a constant."""
    cur = (currency or "usd").lower()
    if cur == "dkk":
        return 1.0, "native"
    key = f"{cur}-dkk-{date_str}"
    cached = await db[FX_COLL].find_one({"_id": key})
    if cached:
        return float(cached["rate"]), cached.get("source", "cache")
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
            r = await client.get(f"https://api.frankfurter.dev/v1/{date_str}", params={"base": cur.upper(), "symbols": "DKK"})
            r.raise_for_status()
            rate = float(r.json()["rates"]["DKK"])
        await db[FX_COLL].update_one({"_id": key}, {"$set": {"rate": rate, "source": "ecb"}}, upsert=True)
        return rate, "ecb"
    except Exception as e:
        logger.warning("FX fetch failed for %s %s: %s", cur, date_str, e)
    newest = await db[FX_COLL].find_one({"_id": {"$regex": f"^{cur}-dkk-"}}, sort=[("_id", -1)])
    if newest:
        return float(newest["rate"]), "nearest-cache"
    return FALLBACK_USD_DKK, "fallback"


async def _year_income(db, year: int) -> dict:
    """All paid transactions for the year, each converted to DKK on payment date."""
    cursor = db.payment_transactions.find(
        {"payment_status": "paid", "created_at": {"$gte": f"{year}-01-01", "$lt": f"{year + 1}-01-01"}},
        {"_id": 0, "created_at": 1, "amount": 1, "currency": 1, "kind": 1, "user_email": 1},
    ).sort("created_at", 1)
    txns, monthly = [], {m: {"month": m, "gross_usd": 0.0, "gross_dkk": 0.0, "count": 0} for m in range(1, 13)}
    total_usd = total_dkk = 0.0
    approx_fx = False
    async for tx in cursor:
        amount = float(tx.get("amount") or 0)
        cur = (tx.get("currency") or "usd").lower()
        date_str = (tx.get("created_at") or "")[:10]
        if cur == "dkk":
            dkk, rate, source = amount, 1.0, "native"
        else:
            rate, source = await _rate_to_dkk(db, date_str, cur)
            dkk = round(amount * rate, 2)
        if source in ("nearest-cache", "fallback"):
            approx_fx = True
        m = _month_key(tx.get("created_at") or "")
        if m in monthly:
            monthly[m]["gross_usd"] += amount if cur == "usd" else 0
            monthly[m]["gross_dkk"] += dkk
            monthly[m]["count"] += 1
        total_usd += amount if cur == "usd" else 0
        total_dkk += dkk
        txns.append({
            "date": date_str, "kind": tx.get("kind") or "payment",
            "kind_label": KIND_LABELS.get(tx.get("kind"), tx.get("kind") or "Betaling"),
            "email": tx.get("user_email") or "", "amount": amount,
            "currency": cur.upper(), "rate": round(rate, 4), "amount_dkk": dkk,
        })
    for m in monthly.values():
        m["gross_usd"] = round(m["gross_usd"], 2)
        m["gross_dkk"] = round(m["gross_dkk"], 2)
    return {
        "transactions": txns,
        "monthly": [monthly[m] for m in range(1, 13)],
        "total_usd": round(total_usd, 2),
        "total_dkk": round(total_dkk, 2),
        "count": len(txns),
        "fx_approximate": approx_fx,
    }


async def _year_expenses(db, year: int) -> dict:
    docs = await db[EXPENSE_COLL].find(
        {"date": {"$gte": f"{year}-01-01", "$lt": f"{year + 1}-01-01"}}, {"_id": 0}
    ).sort("date", -1).to_list(2000)
    by_cat: dict[str, float] = {}
    total = vat_deductible = 0.0
    for e in docs:
        amt = float(e.get("amount_dkk") or 0)
        total += amt
        by_cat[e.get("category") or "other"] = by_cat.get(e.get("category") or "other", 0) + amt
        if e.get("vat_included"):
            vat_deductible += amt * 0.20
    return {
        "expenses": docs,
        "by_category": [
            {"category": c, "label": CATEGORIES.get(c, c), "total_dkk": round(v, 2)}
            for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
        "total_dkk": round(total, 2),
        "vat_deductible_dkk": round(vat_deductible, 2),
    }


def _vat_block(income: dict, expenses: dict, year: int) -> dict:
    q_rev = [0.0, 0.0, 0.0, 0.0]
    for m in income["monthly"]:
        q_rev[(m["month"] - 1) // 3] += m["gross_dkk"]
    q_kob = [0.0, 0.0, 0.0, 0.0]
    for e in expenses["expenses"]:
        if e.get("vat_included"):
            try:
                q_kob[(int(e["date"][5:7]) - 1) // 3] += float(e.get("amount_dkk") or 0) * 0.20
            except (ValueError, TypeError, IndexError):
                continue
    labels = ["1. kvartal (jan–mar)", "2. kvartal (apr–jun)", "3. kvartal (jul–sep)", "4. kvartal (okt–dec)"]
    deadlines = ["1. juni", "1. september", "1. december", f"1. marts {year + 1}"]
    quarters = []
    for i in range(4):
        salg = round(q_rev[i] * 0.20, 2)
        kob = round(q_kob[i], 2)
        quarters.append({
            "label": labels[i],
            "deadline": deadlines[i],
            "revenue_dkk": round(q_rev[i], 2),
            "salgsmoms": salg,
            "koebsmoms": kob,
            "tilsvar": round(salg - kob, 2),
        })
    return {
        "quarters": quarters,
        "salgsmoms_if_all_dk": round(income["total_dkk"] * 0.20, 2),
        "koebsmoms_deductible": expenses["vat_deductible_dkk"],
        "note": ("Salgsmoms-tallene er VEJLEDENDE og antager at alle kunder er danske "
                 "(25% moms = 20% af bruttobeløbet). Har du mange EU-kunder, så spørg "
                 "Skattestyrelsen (72 22 18 18) om OSS-ordningen."),
    }


def _kr(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_tax_pdf(year: int, income: dict, expenses: dict, vat: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    y = H - 20 * mm

    def line(txt, size=9, bold=False, dy=5.2 * mm, color=(0.06, 0.12, 0.09)):
        nonlocal y
        if y < 25 * mm:
            c.showPage()
            y = H - 20 * mm
        c.setFillColorRGB(*color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(20 * mm, y, txt)
        y -= dy

    line("SCOUTMEPLAY — SKATTERAPPORT", 16, True, 8 * mm)
    line(f"Indkomstår {year} · genereret {datetime.now(timezone.utc).strftime('%d-%m-%Y')}", 9, False, 10 * mm)

    line("RESULTAT", 12, True, 7 * mm)
    line(f"Indtægter (brutto): {_kr(income['total_dkk'])} kr.  ({income['count']} betalinger, {_kr(income['total_usd'])} USD)")
    line(f"Udgifter: {_kr(expenses['total_dkk'])} kr.")
    result = income["total_dkk"] - expenses["total_dkk"]
    rubrik = "rubrik 111 (overskud)" if result >= 0 else "rubrik 112 (underskud)"
    line(f"Årets resultat: {_kr(result)} kr.  →  oplysningsskema {rubrik}", 10, True, 9 * mm)

    line("INDTÆGTER PR. MÅNED (DKK)", 12, True, 7 * mm)
    months = ["Jan", "Feb", "Mar", "Apr", "Maj", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]
    for m in income["monthly"]:
        if m["count"]:
            line(f"{months[m['month'] - 1]}: {_kr(m['gross_dkk'])} kr.  ({m['count']} betalinger)")
    if not any(m["count"] for m in income["monthly"]):
        line("Ingen betalinger registreret i året.")
    y -= 4 * mm

    line("UDGIFTER PR. KATEGORI (DKK)", 12, True, 7 * mm)
    for c_row in expenses["by_category"]:
        line(f"{c_row['label']}: {_kr(c_row['total_dkk'])} kr.")
    if not expenses["by_category"]:
        line("Ingen udgifter registreret.")
    y -= 4 * mm

    line("UDGIFTSPOSTER", 12, True, 7 * mm)
    for e in expenses["expenses"][:60]:
        vat_tag = " · inkl. dansk moms" if e.get("vat_included") else ""
        line(f"{e.get('date')}  {CATEGORIES.get(e.get('category'), e.get('category'))}: "
             f"{_kr(float(e.get('amount_dkk') or 0))} kr. — {e.get('note') or ''}{vat_tag}", 8, dy=4.6 * mm)
    y -= 4 * mm

    line("MOMS PR. KVARTAL (VEJLEDENDE)", 12, True, 7 * mm)
    for q in vat["quarters"]:
        line(f"{q['label']}: omsætning {_kr(q['revenue_dkk'])} kr. · salgsmoms {_kr(q['salgsmoms'])} kr. · "
             f"købsmoms {_kr(q['koebsmoms'])} kr. · momstilsvar {_kr(q['tilsvar'])} kr. — frist {q['deadline']}", 8, dy=4.8 * mm)
    line(f"Salgsmoms i alt hvis alle kunder er danske: {_kr(vat['salgsmoms_if_all_dk'])} kr.")
    line(f"Fradragsberettiget købsmoms (danske køb): {_kr(vat['koebsmoms_deductible'])} kr.")
    y -= 6 * mm
    line(DISCLAIMER, 7, False, 4 * mm, color=(0.4, 0.4, 0.4))

    c.showPage()
    c.save()
    return buf.getvalue()


def build_tax_router(db, get_current_admin, upload_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/admin/tax")
    receipts_dir = upload_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    @router.get("/summary")
    async def tax_summary(year: int = 2026, _=Depends(get_current_admin)):
        income = await _year_income(db, year)
        expenses = await _year_expenses(db, year)
        result = round(income["total_dkk"] - expenses["total_dkk"], 2)
        return {
            "year": year,
            "income": income,
            "expenses": expenses,
            "result_dkk": result,
            "rubrik": "111" if result >= 0 else "112",
            "vat": _vat_block(income, expenses, year),
            "categories": CATEGORIES,
            "guide": GUIDE_STEPS,
            "disclaimer": DISCLAIMER,
        }

    @router.post("/expenses")
    async def add_expense(
        amount_dkk: float = Form(...),
        date: str = Form(...),
        category: str = Form(...),
        note: str = Form(""),
        vat_included: bool = Form(False),
        receipt: UploadFile | None = File(None),
        _=Depends(get_current_admin),
    ):
        if amount_dkk <= 0:
            raise HTTPException(400, "Beløbet skal være større end 0")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Dato skal være YYYY-MM-DD")
        if category not in CATEGORIES:
            raise HTTPException(400, "Ukendt kategori")

        expense_id = str(uuid.uuid4())[:12]
        receipt_url = receipt_filename = None
        if receipt and receipt.filename:
            ext = receipt.filename.rsplit(".", 1)[-1].lower()
            if ext not in RECEIPT_EXTS:
                raise HTTPException(400, f"Kvittering skal være {', '.join(sorted(RECEIPT_EXTS))}")
            data = await receipt.read()
            if len(data) > 15 * 1024 * 1024:
                raise HTTPException(400, "Kvittering må max være 15 MB")
            receipt_filename = f"{expense_id}.{ext}"
            local = receipts_dir / receipt_filename
            local.write_bytes(data)
            receipt_url = f"/api/uploads/receipts/{receipt_filename}"
            if r2_storage.is_configured():
                try:
                    ctype = "application/pdf" if ext == "pdf" else f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
                    r2_storage.upload_file(f"receipts/{receipt_filename}", local, ctype)
                    receipt_url = f"/api/media/receipts/{receipt_filename}"
                except Exception as e:
                    logger.warning("Receipt R2 flush failed: %s", e)

        doc = {
            "id": expense_id,
            "date": date,
            "amount_dkk": round(float(amount_dkk), 2),
            "category": category,
            "note": (note or "").strip()[:300],
            "vat_included": bool(vat_included),
            "receipt_filename": receipt_filename,
            "receipt_url": receipt_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[EXPENSE_COLL].insert_one({**doc})
        return doc

    @router.delete("/expenses/{expense_id}")
    async def delete_expense(expense_id: str, _=Depends(get_current_admin)):
        doc = await db[EXPENSE_COLL].find_one({"id": expense_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Udgiften findes ikke")
        await db[EXPENSE_COLL].delete_one({"id": expense_id})
        if doc.get("receipt_filename"):
            try:
                (receipts_dir / doc["receipt_filename"]).unlink(missing_ok=True)
            except OSError:
                pass
        return {"deleted": True}

    @router.get("/export.csv")
    async def export_csv(year: int = 2026, _=Depends(get_current_admin)):
        income = await _year_income(db, year)
        expenses = await _year_expenses(db, year)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow([f"ScoutMePlay skatterapport {year}"])
        w.writerow([])
        w.writerow(["INDTÆGTER"])
        w.writerow(["Dato", "Type", "Kunde", "Beløb", "Valuta", "Kurs", "Beløb DKK"])
        for t in income["transactions"]:
            w.writerow([t["date"], t["kind_label"], t["email"], f"{t['amount']:.2f}", t["currency"], f"{t['rate']:.4f}", f"{t['amount_dkk']:.2f}"])
        w.writerow(["I alt", "", "", "", "", "", f"{income['total_dkk']:.2f}"])
        w.writerow([])
        w.writerow(["UDGIFTER"])
        w.writerow(["Dato", "Kategori", "Note", "Inkl. dansk moms", "Beløb DKK"])
        for e in expenses["expenses"]:
            w.writerow([e.get("date"), CATEGORIES.get(e.get("category"), e.get("category")), e.get("note") or "", "ja" if e.get("vat_included") else "nej", f"{float(e.get('amount_dkk') or 0):.2f}"])
        w.writerow(["I alt", "", "", "", f"{expenses['total_dkk']:.2f}"])
        w.writerow([])
        w.writerow(["Årets resultat DKK", f"{income['total_dkk'] - expenses['total_dkk']:.2f}"])
        data = "\ufeff" + buf.getvalue()
        return Response(content=data.encode("utf-8"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="scoutmeplay-skat-{year}.csv"'})

    @router.get("/export.pdf")
    async def export_pdf(year: int = 2026, _=Depends(get_current_admin)):
        income = await _year_income(db, year)
        expenses = await _year_expenses(db, year)
        pdf = _build_tax_pdf(year, income, expenses, _vat_block(income, expenses, year))
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="scoutmeplay-skat-{year}.pdf"'})

    @router.post("/revolut/preview")
    async def revolut_preview(year: int = 2026, statement: UploadFile = File(...), _=Depends(get_current_admin)):
        data = await statement.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, "Filen må max være 10 MB")
        parsed = _parse_revolut_csv(data)
        parsed = [r for r in parsed if r["date"].startswith(str(year))]
        hashes = [hashlib.md5(f"{r['date']}|{r['description']}|{r['orig_amount']:.2f}|{r['currency']}".encode()).hexdigest()[:16] for r in parsed]
        existing = set()
        if hashes:
            async for doc in db[EXPENSE_COLL].find({"import_hash": {"$in": hashes}}, {"_id": 0, "import_hash": 1}):
                existing.add(doc["import_hash"])
        out = []
        for r, h in zip(parsed, hashes):
            rate, _src = await _rate_to_dkk(db, r["date"], r["currency"])
            out.append({
                "hash": h,
                "date": r["date"],
                "description": r["description"],
                "orig_amount": r["orig_amount"],
                "currency": r["currency"],
                "amount_dkk": round(r["orig_amount"] * rate, 2),
                "suggested_category": _suggest_category(r["description"]),
                "already_imported": h in existing,
            })
        return {"rows": out, "count": len(out)}

    @router.post("/revolut/import")
    async def revolut_import(payload: RevolutImportPayload, _=Depends(get_current_admin)):
        hashes = [r.hash for r in payload.rows]
        existing = set()
        if hashes:
            async for doc in db[EXPENSE_COLL].find({"import_hash": {"$in": hashes}}, {"_id": 0, "import_hash": 1}):
                existing.add(doc["import_hash"])
        imported = skipped = 0
        for r in payload.rows:
            if r.hash in existing or r.amount_dkk <= 0 or r.category not in CATEGORIES:
                skipped += 1
                continue
            await db[EXPENSE_COLL].insert_one({
                "id": str(uuid.uuid4())[:12],
                "date": r.date,
                "amount_dkk": round(float(r.amount_dkk), 2),
                "category": r.category,
                "note": (r.note or "").strip()[:300],
                "vat_included": bool(r.vat_included),
                "receipt_filename": None,
                "receipt_url": None,
                "source": "revolut",
                "import_hash": r.hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            existing.add(r.hash)
            imported += 1
        return {"imported": imported, "skipped": skipped}

    return router
