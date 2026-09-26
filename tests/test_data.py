import datetime as dt

import numpy as np
import pytest

from lineova._data import DataError, aggregate, factorize, resolve_xy, value_kind

pd = pytest.importorskip("pandas")


def test_plain_list():
    xy = resolve_xy([3, 1, 4])
    assert xy.x_kind == "num"
    assert xy.series[0].x.tolist() == [0, 1, 2]
    assert xy.series[0].y.dtype == np.float64


def test_dict_of_series_with_shared_x():
    xy = resolve_xy({"a": [1, 2], "b": [3, 4]}, x=[10, 20])
    assert [s.name for s in xy.series] == ["a", "b"]
    assert xy.series[1].x.tolist() == [10, 20]


def test_2d_array_columns_become_series():
    xy = resolve_xy(np.arange(12).reshape(4, 3))
    assert len(xy.series) == 3


def test_dataframe_auto_x_datetime_and_auto_group():
    df = pd.DataFrame({
        "day": pd.date_range("2024-01-01", periods=6).repeat(2),
        "city": ["A", "B"] * 6,
        "temp": np.arange(12.0),
    })
    xy = resolve_xy(df, y="temp", color="auto")
    assert xy.x_kind == "time"
    assert xy.grouped_by == "city"
    assert [s.name for s in xy.series] == ["A", "B"]
    assert len(xy.series[0].x) == 6


def test_pandas_series_uses_index():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-01", "2024-01-02"]), name="v")
    xy = resolve_xy(s)
    assert xy.x_kind == "time" and xy.series[0].name == "v"


def test_nullable_and_nan():
    s = pd.Series([1, None, 3], dtype="Int64")
    xy = resolve_xy(s)
    assert np.isnan(xy.series[0].y[1])


def test_tz_aware_datetimes():
    idx = pd.date_range("2024-01-01", periods=3, tz="Europe/Madrid")
    xy = resolve_xy(pd.Series([1, 2, 3], index=idx))
    assert xy.x_kind == "time"


def test_python_datetimes():
    xs = [dt.datetime(2024, 1, d) for d in (1, 2, 3)]
    assert resolve_xy(y=[1, 2, 3], x=xs).x_kind == "time"


def test_missing_column_message_lists_columns():
    df = pd.DataFrame({"a": [1], "b": [2]})
    with pytest.raises(DataError, match="Available columns: 'a', 'b'"):
        resolve_xy(df, x="a", y="zzz")


def test_length_mismatch():
    with pytest.raises(DataError, match="different lengths"):
        resolve_xy(y=[1, 2, 3], x=[1, 2])


def test_non_numeric_y():
    with pytest.raises(DataError, match="not numeric"):
        resolve_xy(y=["a", "b"], x=[1, 2])


def test_value_kind():
    assert value_kind(np.array(["a"])) == "cat"
    assert value_kind(np.array([1.5])) == "num"
    assert value_kind(np.array(["2024-01-01"], dtype="datetime64[D]")) == "time"


def test_factorize_first_appearance_and_missing():
    codes, names = factorize(np.array(["b", "a", None, "b"], dtype=object))
    assert names == ["b", "a"]
    assert codes.tolist() == [0, 1, -1, 0]


@pytest.mark.parametrize("how,expected", [("sum", [4.0, 2.0]), ("mean", [2.0, 2.0]), ("count", [2.0, 1.0]),
                                          ("max", [3.0, 2.0])])
def test_aggregate(how, expected):
    names, vals = aggregate(np.array(["x", "y", "x"]), np.array([1.0, 2.0, 3.0]), how)
    assert names == ["x", "y"]
    assert vals.tolist() == expected
