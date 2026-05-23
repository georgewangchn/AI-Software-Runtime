import csv, io

def process_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    result = {"count": len(rows), "columns": reader.fieldnames or []}
    total = 0
    for row in rows:
        if "amount" in row:
            result["total"] = total + float(row["amount"])
    return result

def filter_by_column(text, col, value):
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader if row.get(col) == value]
