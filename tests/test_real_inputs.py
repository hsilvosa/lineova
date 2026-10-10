import datetime as dt
import importlib.util
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
SPEC = importlib.util.spec_from_file_location("build_real_inputs", Path(__file__).resolve().parent.parent / "tools" / "build_real_inputs.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

PRICES = "MARGINALPDBC;\r\n2024;01;15;1;77.7;77.9;\r\n2024;01;15;2;-0.01;67;\r\n2024;01;15;3;64.99;64.99;\r\n*\r\n"
CURVES = ("OMIE - Mercado de electricidad;Fecha Emisión :31/12/2023 - 12:55;;01/01/2024;Mercado diario;;;;\r\n\r\n"
          "Hora;Fecha;Pais;Unidad;Tipo Oferta;Energía Compra/Venta;Precio Compra/Venta;Ofertada (O)/Casada (C);\r\n"
          "1;01/01/2024;MI;TOTRM01;C;380,7;1.500,00;O;\r\n"
          "1;01/01/2024;MI;ACAVADO;V;43,2;42,09;C;\r\n"
          "24;01/01/2024;MI;EUCDR01;C;1.234,5;-5,25;C;\r\n"
          ";;;;;;;;\r\n")


def test_parse_prices():
    rows = tool.parse_prices(PRICES)
    assert rows == [("2024-01-15", 1, 77.7, 77.9), ("2024-01-15", 2, -0.01, 67.0), ("2024-01-15", 3, 64.99, 64.99)]
    assert tool.parse_prices("MARGINALPDBC;\n*") == []


def test_parse_curves_handles_spanish_numbers_and_filler_lines():
    d = tool.parse_curves(CURVES)
    assert d["day"].tolist() == [20240101] * 3 and d["hour"].tolist() == [1, 1, 24]
    assert d["side"].tolist() == [0, 1, 0] and d["status"].tolist() == [0, 1, 1]
    assert d["price"].tolist() == pytest.approx([1500.0, 42.09, -5.25])
    assert d["energy"].tolist() == pytest.approx([380.7, 43.2, 1234.5])
    assert {k: v.dtype for k, v in d.items()}["price"] == np.float32
    with pytest.raises(ValueError, match="header"):
        tool.parse_curves("nothing here")


IGN_A = ("Evento;Fecha;Hora;Latitud;Longitud;Prof. (Km);Inten.;Mag;Tipo Mag;Localización\n"
         "es2024aaa;01/02/2024;03:04:05;37,1234;-4,5;10;III;3,2;mbLg;SW GRANADA\n"
         "es2024bbb;02/02/2024;13:14:15;28.1;-17.9;35;;2,8;mbLg;LA PALMA\n"
         "es2024ccc;03/02/2024;00:00:01;;;5;;1,0;mbLg;NO POSITION\n")
IGN_B = ("Mag;Latitud;Longitud;Fecha;Hora;Evento;Profundidad\n"
         "4,1;42.5;0,5;05/03/2024;11:11:11;es2024ddd;12\n")


def test_parse_quakes_variants():
    a = tool.parse_quakes(IGN_A)
    assert list(a.columns) == tool.QUAKE_COLUMNS and len(a) == 2                 # the row without a position is dropped
    assert a["lat"].tolist() == pytest.approx([37.1234, 28.1]) and a["magnitude"].tolist() == pytest.approx([3.2, 2.8])
    assert a["location"].tolist() == ["SW GRANADA", "LA PALMA"] and a["event_id"][0] == "es2024aaa"
    b = tool.parse_quakes(IGN_B)
    assert len(b) == 1 and b["depth_km"][0] == "12" and b["lon"][0] == pytest.approx(0.5) and b["location"][0] == ""
    with pytest.raises(ValueError, match="no column"):
        tool.parse_quakes("a;b\n1;2\n")


def test_build_quakes_merges_and_deduplicates(tmp_path):
    f1, f2 = tmp_path / "a.csv", tmp_path / "b.csv"
    f1.write_text(IGN_A, encoding="utf-8")
    f2.write_text(IGN_A.replace("es2024bbb", "es2024zzz"), encoding="utf-8")
    n = tool.build_quakes(tmp_path, [f1, f2])
    out = pd.read_csv(tmp_path / "ign_earthquakes.csv", sep=";")
    assert n == len(out) == 3 and list(out.columns) == tool.QUAKE_COLUMNS


def test_build_prices_with_a_fake_server(tmp_path, monkeypatch):
    calls = []

    def fake(folder, name, cache=None, retries=3):
        calls.append(name)
        if name.endswith("20240116.1"):
            return None                                             # a day the site does not have
        day = name.split("_")[1][:8]
        return f"MARGINALPDBC;\n{day[:4]};{day[4:6]};{day[6:]};1;50.5;51;\n{day[:4]};{day[4:6]};{day[6:]};2;60;61;\n*\n".encode()

    monkeypatch.setattr(tool, "fetch", fake)
    n = tool.build_prices(tmp_path, dt.date(2024, 1, 15), dt.date(2024, 1, 17), workers=2)
    out = pd.read_csv(tmp_path / "omie_prices.csv", parse_dates=["date"])
    assert n == len(out) == 4 and list(out.columns) == ["date", "period", "price_es", "price_pt"]
    assert out["date"].dt.day.tolist() == [15, 15, 17, 17] and len(calls) == 3


def test_build_curves_from_a_zip(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("curva_pbc_uof_20240101.1", CURVES.encode("latin-1"))
        z.writestr("curva_pbc_uof_20240102.1", CURVES.replace("01/01/2024", "02/01/2024").encode("latin-1"))
    monkeypatch.setattr(tool, "fetch", lambda folder, name, cache=None, retries=3: buf.getvalue())
    assert tool.build_curves(tmp_path, "2024-01") == 6
    z = np.load(tmp_path / "curves_202401.npz")
    assert sorted(z.files) == ["day", "energy", "hour", "price", "side", "status"]
    assert np.unique(z["day"]).tolist() == [20240101, 20240102]
    monkeypatch.setattr(tool, "fetch", lambda *a, **k: None)
    with pytest.raises(SystemExit):
        tool.build_curves(tmp_path, "2030-01")


def test_fetch_uses_the_cache(tmp_path, monkeypatch):
    (tmp_path / "f.1").write_bytes(b"cached")
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    assert tool.fetch("x", "f.1", tmp_path) == b"cached"


def test_fetch_html_means_missing(tmp_path, monkeypatch):
    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *a, **k: R(b"<!DOCTYPE html><html>404"))
    assert tool.fetch("x", "nope.1", tmp_path) is None and not (tmp_path / "nope.1").exists()


def test_command_line(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "fetch", lambda folder, name, cache=None, retries=3: PRICES.encode())
    assert tool.main(["prices", str(tmp_path), "--start", "2024-01-15", "--end", "2024-01-15"]) == 0
    assert (tmp_path / "omie_prices.csv").exists()
