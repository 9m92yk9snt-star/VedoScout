import asyncio, os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"

def resolver(url):
    if url and url.startswith("/api/uploads/"):
        p = UPLOAD_DIR / url[len("/api/uploads/"):]
        return str(p) if p.exists() else None
    return None

async def main():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    doc = await db.reports.find_one({"id": "demo-sample-report"})
    assert doc, "demo doc missing"
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pdf_v2 import build_pdf_v2
    out = "/tmp/demo_snapshot_test.pdf"
    build_pdf_v2(doc, out, image_resolver=resolver)
    import fitz
    pdf = fitz.open(out)
    print("pages:", len(pdf))
    for i in (0, 1):
        pix = pdf[i].get_pixmap(dpi=72)
        pix.save(f"/tmp/pdf_page{i+1}.png")
    print("rendered")

asyncio.run(main())
