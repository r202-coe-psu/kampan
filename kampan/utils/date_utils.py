import datetime

MONTHS_TH = [
    "",
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]


def format_date_th(date_str):
    """
    Receives date string in 'YYYY-MM-DD' format
    and returns 'D Month YYYY' in Thai (Buddhist Era).
    Example: '2024-03-08' -> '8 มีนาคม 2567'
    """
    if not date_str:
        return "-"

    try:
        # Parse the input string
        if isinstance(date_str, str):
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = date_str

        day = dt.day
        month = MONTHS_TH[dt.month]
        year_be = dt.year + 543

        return f"{day} {month} {year_be}"
    except Exception as e:
        print(f"Error formatting Thai date: {e}")
        return date_str
