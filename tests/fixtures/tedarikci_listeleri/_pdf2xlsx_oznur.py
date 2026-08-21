"""Oznur Kablo fiyat listesi PDF -> XLSX.
Tek seferlik donusturucu: parser fixture'i uretmek icin. Urune girmez.
"""
import re, sys
import pdfplumber
from openpyxl import Workbook

AMB = r"(?:R\d+|M\d+|T\d+|Tambur|TAMBUR)"
ROW = re.compile(
    r"^(?P<pre>.*?)"
    r"(?P<kesit>\d[\d.,]*(?:\s*[x+/]\s*\d[\d.,]*)*)\s*[*†‡]?\s+"
    r"(?P<fiyat>\d{1,3}(?:\.\d{3})+|\d+[.,]\d+|\d+)\s+"
    r"(?P<amb>" + AMB + r"(?:\s*-\s*" + AMB + r")*)\s*$"
)
BASLIK = re.compile(r"[A-Z0-9][A-Z0-9\-/()]{2,}.*?\d+/\d+\s*[kK]?[vV]")

def fiyat_cevir(s):
    # 1.371.000 -> 1371000 ; 18.410 -> 18410 (nokta binlik ayirici)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        return float(s.replace(".", ""))
    return float(s.replace(".", "").replace(",", "."))

def isle(pdf_yolu):
    satirlar = []
    with pdfplumber.open(pdf_yolu) as pdf:
        for sno, pg in enumerate(pdf.pages, 1):
            mid = pg.width / 2
            for sutun, box in (("sol", (0, 0, mid, pg.height)),
                               ("sag", (mid, 0, pg.width, pg.height))):
                metin = pg.crop(box).extract_text() or ""
                urun = None
                for ham in metin.split("\n"):
                    ham = ham.strip()
                    if not ham:
                        continue
                    m = ROW.match(ham)
                    if not m:
                        b = BASLIK.search(ham)
                        if b and "Kesit" not in ham:
                            urun = ham
                        continue
                    pre = m.group("pre").strip()
                    if pre and BASLIK.search(pre):
                        urun = pre
                    satirlar.append({
                        "sayfa": sno, "sutun": sutun,
                        "urun": urun or "",
                        "kesit": m.group("kesit").replace(" ", ""),
                        "fiyat": fiyat_cevir(m.group("fiyat")),
                        "fiyat_ham": m.group("fiyat"),
                        "birim": "TL/km",
                        "ambalaj": m.group("amb"),
                    })
    return satirlar

def yaz(satirlar, cikti):
    wb = Workbook(); ws = wb.active; ws.title = "OZNUR HAZIRAN 2026"
    basliklar = ["Sayfa", "Sutun", "Urun", "Kesit (mm2)", "Fiyat", "Fiyat (ham)", "Birim", "Ambalaj"]
    ws.append(basliklar)
    for s in satirlar:
        ws.append([s["sayfa"], s["sutun"], s["urun"], s["kesit"],
                   s["fiyat"], s["fiyat_ham"], s["birim"], s["ambalaj"]])
    wb.save(cikti)

if __name__ == "__main__":
    kaynak = sys.argv[1] if len(sys.argv) > 1 else "pdf/oznur_haziran_2026.pdf"
    cikti = sys.argv[2] if len(sys.argv) > 2 else "tedarikci-xls/Oznur_Kablo_Haziran_2026_PDFten.xlsx"
    s = isle(kaynak)
    yaz(s, cikti)
    print(f"cikarilan satir: {len(s)}")
    urunler = sorted({x['urun'] for x in s if x['urun']})
    print(f"farkli urun basligi: {len(urunler)}")
    print(f"urunsuz satir: {sum(1 for x in s if not x['urun'])}")
    print("\nornek 15 satir:")
    for x in s[:15]:
        print(f"  s{x['sayfa']}/{x['sutun']:3} | {x['urun'][:42]:42} | {x['kesit']:12} | {x['fiyat']:>12,.0f} | {x['ambalaj']}")
    print("\nen yuksek 5 fiyat:")
    for x in sorted(s, key=lambda k: -k['fiyat'])[:5]:
        print(f"  {x['urun'][:40]:40} | {x['kesit']:12} | {x['fiyat_ham']:>12} -> {x['fiyat']:>14,.0f}")
