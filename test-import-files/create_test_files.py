"""Create 3 messy sample import files for testing.

All data is FICTIONAL — no real guests, hotels, or bookings.
"""
import csv
import os

DIR = os.path.dirname(os.path.abspath(__file__))


# --- 1. Excel: past occupancy with Italian headers, merged-ish cells ---
def create_occupancy_xlsx():
    try:
        import openpyxl
    except ImportError:
        print("openpyxl not installed — skipping Excel file")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Occupazione 2025"

    # Messy: title row spanning columns
    ws.merge_cells("A1:E1")
    ws["A1"] = "Grand Hotel Bristol — Occupazione Mensile 2025"
    ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)

    # Empty row
    # Headers in Italian, some abbreviated
    ws["A3"] = "Mese"
    ws["B3"] = "Camere Vendute"
    ws["C3"] = "Camere Totali"
    ws["D3"] = "% Occupaz."
    ws["E3"] = "Ricavo medio (€)"

    data = [
        ("Gennaio 2025", 1240, 2635, "47%", "€ 195"),
        ("Febbraio 2025", 1190, 2380, "50%", "€ 198"),
        ("Marzo 2025", 1580, 2635, "60%", "€ 210"),
        ("Aprile 2025", 1860, 2550, "73%", "€ 245"),
        ("Maggio 2025", 2100, 2635, "80%", "€ 260"),
        ("Giugno 2025", 2300, 2550, "90%", "€ 290"),
        ("Luglio 2025", 2450, 2635, "93%", "€ 310"),
        ("Agosto 2025", 2500, 2635, "95%", "€ 320"),
        ("Settembre 2025", 2200, 2550, "86%", "€ 275"),
        ("Ottobre 2025", 1700, 2635, "65%", "€ 230"),
        ("Novembre 2025", 1100, 2550, "43%", "€ 185"),
        # Messy: missing December, typo in month
    ]

    for i, row in enumerate(data, start=4):
        for j, val in enumerate(row):
            ws.cell(row=i, column=j + 1, value=val)

    # Random note at the bottom
    ws.cell(row=16, column=1, value="Note: dati provvisori, conferma con contabilità")

    # Second sheet with room types
    ws2 = wb.create_sheet("Tipologie Camere")
    ws2["A1"] = "Tipo"
    ws2["B1"] = "Numero"
    ws2["C1"] = "Letti"
    ws2["D1"] = "Vista"
    rooms = [
        ("Classic", 30, 2, "Giardino"),
        ("Superior", 25, 2, "Lago"),
        ("Junior Suite", 15, 2, "Lago panoramico"),
        ("Suite", 10, 3, "Lago panoramico"),
        ("Presidential", 5, 4, "Lago 360°"),
    ]
    for i, row in enumerate(rooms, start=2):
        for j, val in enumerate(row):
            ws2.cell(row=i, column=j + 1, value=val)

    path = os.path.join(DIR, "occupazione_bristol_2025.xlsx")
    wb.save(path)
    print(f"Created: {path}")


# --- 2. Text file (simulating a Word doc): rates and rules ---
def create_rates_txt():
    text = """GRAND HOTEL BRISTOL — TARIFFE E REGOLE 2026

TARIFFE CAMERA (per notte, colazione inclusa)
=============================================

Bassa stagione (Nov-Mar, escluso Natale/Capodanno):
  Classic         € 180
  Superior        € 220
  Junior Suite    € 290
  Suite           € 380
  Presidential    € 550

Media stagione (Apr, Ott):
  Classic         € 220
  Superior        € 260
  Junior Suite    € 340
  Suite           € 450
  Presidential    € 680

Alta stagione (Mag-Set):
  Classic         € 280
  Superior        € 340
  Junior Suite    € 420
  Suite           € 560
  Presidential    € 850

Natale/Capodanno (20 Dic - 6 Gen):
  Supplemento +30% su tariffa alta stagione
  Soggiorno minimo 3 notti

REGOLE GENERALI
===============
- Check-in: 15:00 — Check-out: 11:00
- Cancellazione gratuita fino a 7 giorni prima
- Soggiorno minimo alta stagione: 2 notti
- Soggiorno minimo bassa stagione: 1 notte
- Bambini sotto 6 anni: gratuito nel letto dei genitori
- Animali ammessi (piccola taglia): supplemento € 25/notte
- Parcheggio: € 15/giorno
- Spa: accesso incluso per Superior e oltre

SUPPLEMENTI E PACCHETTI
========================
- Mezza pensione: +€ 45/persona/notte
- Pensione completa: +€ 75/persona/notte
- Pacchetto romantico: +€ 120 (champagne, petali, late checkout)
- Pacchetto famiglia: -15% su seconda camera
- Escursione in barca: € 90/persona (2 ore, Isola Bella + Isola Madre)

Ultimo aggiornamento: Marzo 2026
Approvato da: Direzione
"""

    path = os.path.join(DIR, "tariffe_regole_bristol_2026.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Created: {path}")


# --- 3. CSV: guest list with missing consent ---
def create_guest_csv():
    path = os.path.join(DIR, "lista_ospiti_bristol.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Nome", "Cognome", "Email", "Telefono", "Città", "Soggiorni", "Ultimo Soggiorno", "Consenso Marketing", "Data Consenso"])
        guests = [
            ("Marco", "Rossi", "m.rossi@example.it", "+39 333 1234567", "Milano", 5, "2025-08-15", "Sì", "2024-01-10"),
            ("Anna", "Bianchi", "anna.bianchi@example.com", "+39 335 7654321", "Torino", 3, "2025-07-22", "Sì", "2023-06-15"),
            ("Giovanni", "Verdi", "g.verdi@example.de", "+49 170 1234567", "München", 2, "2025-09-01", "", ""),  # Missing consent
            ("Sophie", "Dupont", "sophie.d@example.fr", "+33 6 12345678", "Lyon", 1, "2025-06-10", "Sì", "2025-06-10"),
            ("Thomas", "Weber", "t.weber@example.ch", "+41 79 1234567", "Zürich", 7, "2025-10-05", "Sì", "2022-03-20"),
            ("", "Colombo", "colombo@example.it", "", "Como", 2, "2025-04-18", "No", ""),  # Missing first name, explicit No
            ("Laura", "Ferrari", "l.ferrari@example.it", "+39 340 9876543", "Roma", 4, "2025-11-20", "Sì", "2024-05-01"),
            ("Hans", "Müller", "", "+41 76 9876543", "Basel", 1, "2024-12-28", "Sì", "2024-12-28"),  # Missing email
            ("Elena", "Conti", "elena.conti@example.it", "+39 347 1111222", "Bergamo", 6, "2025-09-30", "Sì", "2023-09-15"),
            ("Pierre", "Martin", "p.martin@example.fr", "+33 7 98765432", "Paris", 2, "2025-07-14", "", ""),  # Missing consent
            ("Lucia", "Moretti", "lucia.m@example.it", "+39 329 3334444", "Firenze", 3, "2025-08-25", "Sì", "2024-08-01"),
            ("James", "Smith", "j.smith@example.co.uk", "+44 7700 123456", "London", 1, "2025-05-02", "Sì", "2025-05-02"),
        ]
        for g in guests:
            w.writerow(g)
    print(f"Created: {path}")


if __name__ == "__main__":
    create_occupancy_xlsx()
    create_rates_txt()
    create_guest_csv()
    print("\nAll test files created!")
