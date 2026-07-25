# -*- coding: utf-8 -*-
"""Test logic thuần cho watchlist và URL YouTube."""

import json

import pytest

from watch import MucTheoDoi, WatchList, doc_watchlist, ghi_watchlist, lay_id_youtube


@pytest.mark.parametrize("url", [
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?t=90",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=X",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share",
])
def test_tach_id_cac_dang_url(url):
    assert lay_id_youtube(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    "https://example.com/abc",
    "https://www.youtube.com/channel/UC123456",
    "https://youtu.be/abc",
    "khong-phai-url",
])
def test_tach_id_url_khong_hop_le(url):
    assert lay_id_youtube(url) == ""


def test_doc_file_khong_ton_tai(tmp_path):
    path = tmp_path / "chua_co.json"

    assert doc_watchlist(str(path)).muc == []
    assert not path.exists()


@pytest.mark.parametrize("noi_dung", ["", "{json hong"])
def test_doc_json_rong_hoac_hong(tmp_path, noi_dung):
    path = tmp_path / "watchlist.json"
    path.write_text(noi_dung, encoding="utf-8")

    assert doc_watchlist(str(path)) == WatchList()


def test_doc_json_co_muc_khong_phai_danh_sach(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text('{"muc": null}', encoding="utf-8")

    assert doc_watchlist(str(path)) == WatchList()


def test_doc_bo_qua_muc_thieu_url_va_loai_sai(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "muc": [
            {"loai": "kenh", "url": "https://youtube.com/@kenh"},
            {"loai": "link"},
            {"loai": "sai", "url": "https://youtu.be/dQw4w9WgXcQ"},
        ],
        "kho": "Kho chính",
        "gioi_han_moi_lan": 12,
    }), encoding="utf-8")

    wl = doc_watchlist(str(path))

    assert wl.muc == [MucTheoDoi(
        loai="kenh",
        url="https://youtube.com/@kenh",
    )]
    assert wl.kho == "Kho chính"
    assert wl.gioi_han_moi_lan == 12


def test_ghi_doc_watchlist_giu_nguyen_tieng_viet(tmp_path):
    path = tmp_path / "watchlist.json"
    wl = WatchList(
        muc=[
            MucTheoDoi(
                loai="link",
                url="https://youtu.be/dQw4w9WgXcQ",
                ghi_chu="Khiếu nại bản quyền",
                bat=False,
            ),
        ],
        kho="Kho tiếng Việt",
        gioi_han_moi_lan=7,
    )

    ghi_watchlist(wl, str(path))
    noi_dung = path.read_text(encoding="utf-8")
    doc_lai = doc_watchlist(str(path))

    assert "Khiếu nại bản quyền" in noi_dung
    assert "\\u" not in noi_dung
    assert doc_lai == wl
