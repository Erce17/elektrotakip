"""Viko/Panasonic 2026-2 fiyat listesi PDF -> XLSX.
Tek seferlik donusturucu, Viko sayfa duzenine ozel. Urune girmez.
"""
import re, sys
import pdfplumber
from openpyxl import Workbook

KOD   = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9]*[-/][A-Z0-9][A-Z0-9\-/.]*|[A-Z]{3,}\d{4,}[A-Z0-9]*)\b")
FIYAT = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})(?!\S)")
PARA  = re.compile(r"Fiyat\s*\((TL|USD|EURO|EUR)\)", re.I)
# grup basligi: fiyat icermeyen, kisa, buyuk harfle baslayan satir
BASLIK_YOK = re.compile(r"^\d+$|^[A-Z]$")

def fiyat_cevir(s):
    return float(s.replace(".", "").replace(",", "."))

def isle(yol):
    kayit = []
    with pdfplumber.open(yol) as pdf:
        bolum = ""
        for sno, pg in enumerate(pdf.pages, 1):
            tam = pg.extract_text() or ""
            if not tam.strip():
                continue
            ilk = [s.strip() for s in tam.split("\n") if s.strip()]
            if ilk and not FIYAT.search(ilk[0]) and len(ilk[0]) < 70:
                bolum = ilk[0]
            pm = PARA.search(tam)
            para = pm.group(1).upper() if pm else ""
            mid = pg.width / 2
            for sutun, box in (("sol", (0, 0, mid, pg.height)),
                               ("sag", (mid, 0, pg.width, pg.height))):
                metin = pg.crop(box).extract_text() or ""
                grup = ""
                for ham in metin.split("\n"):
                    ham = ham.strip()
                    if not ham or BASLIK_YOK.match(ham):
                        continue
                    fiyatlar = FIYAT.findall(ham)
                    kodlar = KOD.findall(ham)
                    if not fiyatlar:
                        if len(ham) < 60 and not ham.startswith("Sipariş"):
                            grup = ham
                        continue
                    if not kodlar:
                        # kodsuz satir: anahtar-priz serileri (mekanizma+kapak+toplam)
                        ad = FIYAT.sub("", ham).strip(" .")
                        kayit.append({"bolum": bolum, "sayfa": sno, "sutun": sutun,
                                      "grup": grup, "kod": "", "ad": ad,
                                      "fiyat": fiyat_cevir(fiyatlar[-1]),
                                      "tum_fiyatlar": " | ".join(fiyatlar),
                                      "para": para, "ham": ham})
                        continue
                    for kod in kodlar:
                        kayit.append({"bolum": bolum, "sayfa": sno, "sutun": sutun,
                                      "grup": grup, "kod": kod,
                                      "ad": "", "fiyat": fiyat_cevir(fiyatlar[-1]),
                                      "tum_fiyatlar": " | ".join(fiyatlar),
                                      "para": para, "ham": ham})
                        break
    return kayit

def yaz(kayit, cikti):
    wb = Workbook(); ws = wb.active; ws.title = "VIKO 2026-2"
    ws.append(["Bolum", "Sayfa", "Sutun", "Grup", "Siparis Kodu", "Urun Adi",
               "Fiyat", "Tum Fiyatlar", "Para Birimi", "Ham Satir"])
    for k in kayit:
        ws.append([k["bolum"], k["sayfa"], k["sutun"], k["grup"], k["kod"], k["ad"],
                   k["fiyat"], k["tum_fiyatlar"], k["para"], k["ham"]])
    wb.save(cikti)

if __name__ == "__main__":
    k = isle("pdf/viko_2026_2.pdf")
    yaz(k, "tedarikci-xls/Viko_Panasonic_2026-2_PDFten.xlsx")
    import collections
    print("toplam satir:", len(k))
    print("kodlu:", sum(1 for x in k if x["kod"]), "| kodsuz:", sum(1 for x in k if not x["kod"]))
    print("para birimi:", collections.Counter(x["para"] for x in k).most_common())
    print("\nbolum dagilimi:")
    for b, n in collections.Counter(x["bolum"] for x in k).most_common(14):
        print(f"  {n:5}  {b[:58]}")
