"""tax_helper.py — Danish tax helper (Skat-hjælper) for the admin panel.

Income is pulled automatically from paid Stripe transactions (USD → DKK via
Nationalbank-aligned ECB daily rates, cached in Mongo). Expenses are entered
manually with optional receipt images. Produces a yearly summary, VAT
(moms) overview and CSV/PDF exports. Guidance text targets a CVR-registered
sole proprietorship (enkeltmandsvirksomhed). NOT professional tax advice.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

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
        "body": "Alle indtægter hentes automatisk fra Stripe, og du taster dine udgifter ind her. "
                "Gem kvitteringer (upload dem her) — bogføringsloven kræver 5 års opbevaring.",
    },
    {
        "title": "2. Moms — indberettes via TastSelv Erhverv",
        "body": "Log ind på skat.dk/erhverv → Moms. Nye/små virksomheder indberetter typisk halvårligt: "
                "1. halvår senest 1. september, 2. halvår senest 1. marts året efter. "
                "OBS: Moms på digitale ydelser afhænger af kundens land — danske kunder: 25% dansk moms; "
                "forbrugere i andre EU-lande: OSS-ordningen (One Stop Shop); kunder uden for EU: ingen dansk moms. "
                "Da dine Stripe-kunder kan komme fra hele verden, så afklar fordelingen med Skattestyrelsen (72 22 18 18) eller en revisor.",
    },
    {
        "title": "3. Skat af årets resultat — oplysningsskema",
        "body": "Årets resultat (indtægter minus udgifter) skrives i dit oplysningsskema på skat.dk: "
                "overskud i rubrik 111, underskud i rubrik 112. Frist: 1. juli året efter indkomståret. "
                "Brug PDF-eksporten fra denne side som dokumentation.",
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
                "Er beløbene store, så få en revisor til at bekræfte periodisering.",
    },
]

DISCLAIMER = ("Vejledende værktøj — ikke professionel skatterådgivning. "
              "Bekræft altid moms- og skatteforhold med Skattestyrelsen eller en revisor.")


def _month_key(iso: str) -> int:
    try:
        return int(iso[5:7])
    except (ValueError, TypeError, IndexError):
        return 0


async def _usd_dkk_rate(db, date_str: str) -> tuple[float, str]:
    """Daily USD→DKK rate (ECB via frankfurter.app), cached in Mongo.
    Returns (rate, source). Falls back to newest cached rate, then a constant."""
    key = f"usd-dkk-{date_str}"
    cached = await db[FX_COLL].find_one({"_id": key})
    if cached:
        return float(cached["rate"]), cached.get("source", "cache")
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
            r = await client.get(f"https://api.frankfurter.dev/v1/{date_str}", params={"base": "USD", "symbols": "DKK"})
            r.raise_for_status()
            rate = float(r.json()["rates"]["DKK"])
        await db[FX_COLL].update_one({"_id": key}, {"$set": {"rate": rate, "source": "ecb"}}, upsert=True)
        return rate, "ecb"
    except Exception as e:
        logger.warning("FX fetch failed for %s: %s", date_str, e)
    newest = await db[FX_COLL].find_one({"_id": {"$regex": "^usd-dkk-"}}, sort=[("_id", -1)])
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
            rate, source = await _usd_dkk_rate(db, date_str)
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


def _vat_block(income: dict, expenses: dict) -> dict:
    h1 = sum(m["gross_dkk"] for m in income["monthly"][:6])
    h2 = sum(m["gross_dkk"] for m in income["monthly"][6:])
    return {
        "half_year": [
            {"label": "1. halvår (jan–jun)", "revenue_dkk": round(h1, 2), "deadline": "1. september"},
            {"label": "2. halvår (jul–dec)", "revenue_dkk": round(h2, 2), "deadline": "1. marts (året efter)"},
        ],
        "salgsmoms_if_all_dk": round(income["total_dkk"] * 0.20, 2),
        "koebsmoms_deductible": expenses["vat_deductible_dkk"],
        "note": ("Salgsmoms-tallet er VEJLEDENDE og gælder kun hvis alle kunder er danske "
                 "(25% moms = 20% af bruttobeløbet). EU-forbrugere kræver OSS-ordningen; "
                 "kunder uden for EU er uden dansk moms."),
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

    line("MOMS (VEJLEDENDE)", 12, True, 7 * mm)
    for h in vat["half_year"]:
        line(f"{h['label']}: omsætning {_kr(h['revenue_dkk'])} kr. — frist {h['deadline']}")
    line(f"Salgsmoms hvis alle kunder er danske: {_kr(vat['salgsmoms_if_all_dk'])} kr.")
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
            "vat": _vat_block(income, expenses),
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
        pdf = _build_tax_pdf(year, income, expenses, _vat_block(income, expenses))
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="scoutmeplay-skat-{year}.pdf"'})

    return router
