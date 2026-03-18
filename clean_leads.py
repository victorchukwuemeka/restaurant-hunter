"""
clean_leads.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cleans and organizes restaurants_no_website.csv into a
neat, readable table — sorted, deduped, and ready to pitch.

INSTALL:
  pip install pandas tabulate openpyxl

USAGE:
  python clean_leads.py

OUTPUT:
  leads_clean.csv    — clean CSV
  leads_clean.xlsx   — Excel with formatting (open this)
  leads_preview.txt  — pretty table preview in terminal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import pandas as pd
from tabulate import tabulate
from colorama import Fore, Style, init

init(autoreset=True)

INPUT_CSV   = "restaurants_no_website.csv"
OUTPUT_CSV  = "leads_clean.csv"
OUTPUT_XLSX = "leads_clean.xlsx"
OUTPUT_TXT  = "leads_preview.txt"

DEMO_LINK   = "https://labella-lagos.netlify.app"  # ← your live site

# ── WHATSAPP MESSAGE TEMPLATE ─────────────────────────────────
def make_whatsapp_msg(name: str) -> str:
    return (
        f"Hi {name} 👋\n\n"
        f"I noticed your restaurant doesn't have a website yet.\n\n"
        f"I built this demo for a Lagos restaurant:\n"
        f"👉 {DEMO_LINK}\n\n"
        f"I can build something like this for you — with your menu, "
        f"your photos, and an online booking system.\n\n"
        f"Ready in 3 weeks. Interested?"
    )

# ── CLEAN PHONE NUMBERS ───────────────────────────────────────
def clean_phone(phone: str) -> str:
    if not isinstance(phone, str) or not phone.strip():
        return ""
    # strip spaces, dashes, dots
    p = phone.strip().replace(" ","").replace("-","").replace(".","")
    # normalise to +234 format
    if p.startswith("0") and len(p) >= 10:
        p = "+234" + p[1:]
    if p.startswith("234") and not p.startswith("+"):
        p = "+" + p
    return p

# ── CLEAN ADDRESS ─────────────────────────────────────────────
def clean_address(addr: str) -> str:
    if not isinstance(addr, str):
        return ""
    # Remove duplicate comma-separated parts
    parts = [p.strip() for p in addr.split(",")]
    seen, out = set(), []
    for p in parts:
        if p.lower() not in seen and p:
            seen.add(p.lower())
            out.append(p)
    return ", ".join(out)

# ── CLEAN TYPE LABEL ──────────────────────────────────────────
def clean_type(t: str) -> str:
    if not isinstance(t, str):
        return "Restaurant"
    mapping = {
        "restaurant":  "Restaurant",
        "cafe":        "Café",
        "fast_food":   "Fast Food",
        "food_court":  "Food Court",
        "bakery":      "Bakery",
        "bar":         "Bar & Grill",
    }
    t = t.lower().strip()
    for k, v in mapping.items():
        if k in t:
            return v
    return t.title() if t else "Restaurant"

# ── SCORE LABEL ───────────────────────────────────────────────
def score_label(score) -> str:
    try:
        s = int(score)
        if s >= 60: return "🔥 Hot"
        if s >= 35: return "⚡ Warm"
        return "❄️ Cold"
    except (ValueError, TypeError):
        return "❄️ Cold"

# ── MAIN ──────────────────────────────────────────────────────
def main():
    print(f"\n{Fore.YELLOW}{'━'*52}")
    print(f"  🧹  Lead List Cleaner")
    print(f"{'━'*52}{Style.RESET_ALL}\n")

    # Load
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"{Fore.RED}❌  {INPUT_CSV} not found.")
        print(f"    Run restaurant_hunter.py first.{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}Loaded {len(df)} rows from {INPUT_CSV}{Style.RESET_ALL}")

    # ── Clean each column ──────────────────────────────────────
    df["name"]    = df["name"].astype(str).str.strip().str.title()
    df["phone"]   = df["phone"].astype(str).apply(clean_phone)
    df["address"] = df["address"].astype(str).apply(clean_address)
    df["types"]   = df["types"].astype(str).apply(clean_type)

    # ── Drop rows with no name ─────────────────────────────────
    df = df[df["name"].notna() & (df["name"] != "") & (df["name"] != "Nan")]

    # ── Deduplicate by name + phone ────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["name","phone"], keep="first")
    print(f"{Fore.CYAN}Removed {before - len(df)} duplicates{Style.RESET_ALL}")

    # ── Add priority label ─────────────────────────────────────
    if "lead_score" in df.columns:
        df["priority"] = df["lead_score"].apply(score_label)
    else:
        df["priority"] = "❄️ Cold"

    # ── Add WhatsApp message ───────────────────────────────────
    df["whatsapp_message"] = df["name"].apply(make_whatsapp_msg)

    # ── Add status column (for tracking outreach) ──────────────
    df["status"] = "Not Contacted"

    # ── Add notes column ──────────────────────────────────────
    df["notes"] = ""

    # ── Select and reorder final columns ──────────────────────
    final_cols = [
        "priority",
        "name",
        "phone",
        "types",
        "address",
        "rating",
        "reviews",
        "source",
        "status",
        "notes",
        "whatsapp_message",
    ]
    # only keep cols that exist
    final_cols = [c for c in final_cols if c in df.columns]
    df = df[final_cols]

    # ── Sort: Hot first, then by rating ───────────────────────
    priority_order = {"🔥 Hot": 0, "⚡ Warm": 1, "❄️ Cold": 2}
    df["_sort"] = df["priority"].map(priority_order).fillna(3)
    df = df.sort_values(["_sort", "rating"], ascending=[True, False])
    df = df.drop(columns=["_sort"])
    df = df.reset_index(drop=True)
    df.index += 1  # start row numbers from 1

    # ── Save CSV ───────────────────────────────────────────────
    df.to_csv(OUTPUT_CSV, index_label="#")
    print(f"{Fore.GREEN}✅  CSV  → {OUTPUT_CSV}{Style.RESET_ALL}")

    # ── Save Excel with formatting ─────────────────────────────
    try:
        with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Leads", index_label="#")
            ws = writer.sheets["Leads"]

            from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            # Header style
            header_fill = PatternFill("solid", fgColor="1A1108")
            header_font = Font(bold=True, color="C8A96E", size=11)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Row colors
            hot_fill  = PatternFill("solid", fgColor="2D1A0E")
            warm_fill = PatternFill("solid", fgColor="1A1A0E")
            cold_fill = PatternFill("solid", fgColor="111111")

            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                priority_val = str(row[1].value) if len(row) > 1 else ""
                fill = hot_fill if "Hot" in priority_val else \
                       warm_fill if "Warm" in priority_val else cold_fill
                for cell in row:
                    cell.fill = fill
                    cell.font = Font(color="FAF7F2", size=10)
                    cell.alignment = Alignment(
                        vertical="center",
                        wrap_text=(cell.column == ws.max_column)
                    )

            # Column widths
            col_widths = {
                "priority": 10, "name": 28, "phone": 18,
                "types": 14, "address": 38, "rating": 8,
                "reviews": 10, "source": 14, "status": 16,
                "notes": 20, "whatsapp_message": 60,
            }
            for i, col_name in enumerate(df.columns, start=2):
                letter = get_column_letter(i)
                width  = col_widths.get(col_name, 16)
                ws.column_dimensions[letter].width = width

            # Row height
            ws.row_dimensions[1].height = 22
            for i in range(2, ws.max_row + 1):
                ws.row_dimensions[i].height = 18

            # Freeze top row
            ws.freeze_panes = "B2"

        print(f"{Fore.GREEN}✅  Excel → {OUTPUT_XLSX}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️  Excel export failed: {e}{Style.RESET_ALL}")

    # ── Terminal preview (top 20) ──────────────────────────────
    preview_cols = ["priority","name","phone","types","address","status"]
    preview = df[[c for c in preview_cols if c in df.columns]].head(20)

    table = tabulate(
        preview,
        headers="keys",
        tablefmt="rounded_outline",
        showindex=True,
        maxcolwidths=[4,4,26,18,14,32,16],
    )

    print(f"\n{Fore.YELLOW}── Top 20 Leads Preview ──────────────────────────{Style.RESET_ALL}")
    print(table)

    # Save preview to txt
    with open(OUTPUT_TXT, "w") as f:
        f.write(table)

    # ── Summary ────────────────────────────────────────────────
    hot  = len(df[df["priority"] == "🔥 Hot"])
    warm = len(df[df["priority"] == "⚡ Warm"])
    cold = len(df[df["priority"] == "❄️ Cold"])
    with_phone = len(df[df["phone"] != ""])

    print(f"\n{Fore.YELLOW}── Summary ───────────────────────────────────────{Style.RESET_ALL}")
    print(f"  Total leads     : {Fore.WHITE}{len(df)}{Style.RESET_ALL}")
    print(f"  🔥 Hot          : {Fore.RED}{hot}{Style.RESET_ALL}")
    print(f"  ⚡ Warm         : {Fore.YELLOW}{warm}{Style.RESET_ALL}")
    print(f"  ❄️  Cold         : {Fore.CYAN}{cold}{Style.RESET_ALL}")
    print(f"  📞 With phone   : {Fore.GREEN}{with_phone}{Style.RESET_ALL}  ← these are your targets today")
    print(f"\n  Open {Fore.GREEN}{OUTPUT_XLSX}{Style.RESET_ALL} in Excel or Google Sheets\n")


if __name__ == "__main__":
    main()
