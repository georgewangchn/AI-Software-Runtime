from main import process_csv, filter_by_column

SAMPLE = "name,amount\nAlice,100\nBob,200\nCharlie,300\n"

def test_process_csv_count():
    result = process_csv(SAMPLE)
    assert result["count"] == 3
    assert result["columns"] == ["name", "amount"]

def test_process_csv_total():
    result = process_csv(SAMPLE)
    assert result["total"] == 600

def test_filter_by_column():
    result = filter_by_column(SAMPLE, "name", "Bob")
    assert len(result) == 1
    assert result[0]["amount"] == "200"

def test_filter_no_match():
    result = filter_by_column(SAMPLE, "name", "Nobody")
    assert len(result) == 0
