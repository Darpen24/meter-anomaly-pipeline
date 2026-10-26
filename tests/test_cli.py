import json
import sys

import pytest

from meter_pipeline.cli import main
from meter_pipeline import store


def write_feed(path):
    path.write_text(
        "meter_id,site_id,ts,value,ingested_at\n"
        "M05,S2,2026-01-05T00:00:00Z,1000,2026-01-05T00:05:00Z\n"
        "M05,S2,2026-01-05T00:15:00Z,2000,2026-01-05T00:20:00Z\n",
        encoding="utf-8",
    )


def test_csv_cli_persists_readings_and_exports_json(tmp_path, monkeypatch, capsys):
    feed, db = tmp_path / "feed.csv", tmp_path / "meter.duckdb"
    output = tmp_path / "reports" / "result.json"
    write_feed(feed)
    monkeypatch.setattr(sys, "argv", ["meter-anomaly", "--input", str(feed),
                                      "--db", str(db), "--json-output", str(output)])
    main()
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["input_mode"] == "csv"
    assert result["stored_rows"] == result["quality"]["rows_in"] == 2
    assert result["evaluation"] is None
    assert result["findings"] == []
    with store.connect(str(db)) as con:
        assert store.load(con).kwh.tolist() == [1.0, 2.0]
    assert "CHECK AGAINST INJECTED" not in capsys.readouterr().out


def test_csv_cutoff_and_rerun(tmp_path, monkeypatch):
    feed, db = tmp_path / "feed.csv", tmp_path / "meter.duckdb"
    output = tmp_path / "result.json"
    write_feed(feed)
    base = ["meter-anomaly", "--input", str(feed), "--db", str(db),
            "--json-output", str(output)]
    monkeypatch.setattr(sys, "argv", base + ["--until", "2026-01-05T00:10:00Z"])
    main()
    assert json.loads(output.read_text())["stored_rows"] == 1
    monkeypatch.setattr(sys, "argv", base)
    main()
    main()
    assert json.loads(output.read_text())["stored_rows"] == 2


@pytest.mark.parametrize("problem", ["missing", "invalid", "cutoff"])
def test_cli_errors_are_actionable(tmp_path, monkeypatch, capsys, problem):
    feed = tmp_path / "feed.csv"
    write_feed(feed)
    extra = []
    if problem == "missing":
        feed = tmp_path / "absent.csv"
    elif problem == "invalid":
        feed.write_text("meter_id,value\nM01,-1\n")
    else:
        extra = ["--until", "NaT"]
    monkeypatch.setattr(sys, "argv", ["meter-anomaly", "--input", str(feed), *extra])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "error:" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("target", ["input", "db"])
def test_output_cannot_overwrite_input_or_database(tmp_path, monkeypatch, target):
    feed, db = tmp_path / "feed.csv", tmp_path / "meter.duckdb"
    write_feed(feed)
    original = feed.read_bytes()
    output = feed if target == "input" else db
    monkeypatch.setattr(sys, "argv", ["meter-anomaly", "--input", str(feed),
                                      "--db", str(db), "--json-output", str(output)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert feed.read_bytes() == original
    assert not db.exists()
