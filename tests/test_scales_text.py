import numpy as np

from lineova._text import format_number, format_value, text_width, wrap
from lineova.scales import LinearScale, LogScale, TimeScale, linear_ticks, nice_domain


def test_nice_domain():
    lo, hi, step = nice_domain(3.2, 97.1, 5)
    assert (lo, hi, step) == (0.0, 100.0, 20.0)


def test_linear_ticks_cover_range():
    t, step = linear_ticks(0, 1, 5)
    assert step == 0.2 and t[0] == 0 and abs(t[-1] - 1) < 1e-12


def test_scale_maps_and_inverts():
    s = LinearScale((0, 10), (100, 200))
    assert s.scalar(5) == 150
    assert s.invert(150) == 5
    assert np.allclose(s(np.array([0, 10])), [100, 200])


def test_log_ticks_are_powers():
    s = LogScale((1, 1e6), (0, 300))
    t = s.ticks(5)
    assert all(np.log10(v) % 1 == 0 for v in t)


def test_time_ticks_months_are_month_starts():
    lo = np.datetime64("2024-01-01", "ns").astype(np.int64)
    hi = np.datetime64("2024-12-31", "ns").astype(np.int64)
    s = TimeScale((float(lo), float(hi)), (0, 600))
    t = s.ticks(6)
    days = t.astype(np.int64).astype("datetime64[ns]").astype("datetime64[D]")
    assert all(str(d).endswith("-01") for d in days)
    assert s.labels(t)[0] == "Jan 2024"


def test_time_ticks_hours():
    lo = np.datetime64("2024-03-05T00:00", "ns").astype(np.int64)
    s = TimeScale((float(lo), float(lo + 12 * 3600e9)), (0, 600))
    labs = s.labels(s.ticks(6))
    assert labs[0] == "Mar 5" and labs[1].endswith(":00")


def test_format_number():
    assert format_number(1500, 500) == "1,500"
    assert format_number(25000, 5000) == "25k"
    assert format_number(2.5e6, 5e5) == "2.5M"
    assert format_number(-0.25, 0.05) == "−0.25"
    assert format_number(0.1 + 0.2, 0.1) == "0.3"


def test_format_value():
    assert format_value(34.5) == "34.5"
    assert format_value(0.000123) == "0.000123"
    assert format_value(123456) == "123k"


def test_text_width_and_wrap():
    assert text_width("iii", 10) < text_width("WWW", 10)
    lines = wrap("the quick brown fox jumps over the lazy dog", 80, 11)
    assert len(lines) > 1 and all(text_width(l, 11) <= 80 or " " not in l for l in lines)
