# -*- coding: utf-8 -*-
"""Test logic thuần cho watchlist và URL YouTube."""

import json

import pytest

from watch import (
    MucTheoDoi,
    UngVien,
    WatchList,
    doc_watchlist,
    ghi_watchlist,
    id_da_quet,
    lay_id_youtube,
    loc_can_quet,
)


class _EngineGia:
    def __init__(self, jobs):
        self.jobs = jobs
        self.limit = None

    def list_jobs(self, limit=200):
        self.limit = limit
        return self.jobs


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


def test_id_da_quet_khi_lich_su_rong():
    engine = _EngineGia([])

    assert id_da_quet(engine) == set()
    assert engine.limit == 100000


def test_id_da_quet_chi_lay_job_thanh_cong_va_id_khong_rong():
    engine = _EngineGia([
        {"source_id": "ok-1", "status": "ok"},
        {"source_id": "loi-1", "status": "error"},
        {"source_id": "", "status": "ok"},
        {"source_id": None, "status": "ok"},
    ])

    assert id_da_quet(engine) == {"ok-1"}


def test_id_da_quet_co_the_tinh_ca_job_loi():
    engine = _EngineGia([
        {"source_id": "ok-1", "status": "ok"},
        {"source_id": "loi-1", "status": "error"},
    ])

    assert id_da_quet(engine, chi_thanh_cong=False) == {"ok-1", "loi-1"}


def test_khu_trung_lap_trong_ung_vien():
    uv = [UngVien("a", "u1"), UngVien("a", "u1"), UngVien("b", "u2")]

    assert [x.video_id for x in loc_can_quet(uv, set())] == ["a", "b"]


def test_bo_qua_id_da_quet():
    uv = [UngVien("a", "u1"), UngVien("b", "u2")]

    assert [x.video_id for x in loc_can_quet(uv, {"a"})] == ["b"]


def test_loc_can_quet_bo_id_rong_va_giu_nguyen_thu_tu():
    uv = [
        UngVien("", "rong"),
        UngVien("c", "u3"),
        UngVien("a", "u1"),
        UngVien("b", "u2"),
    ]

    assert [x.video_id for x in loc_can_quet(uv, set())] == ["c", "a", "b"]


def test_loc_can_quet_cat_theo_gioi_han():
    uv = [UngVien("a", "u1"), UngVien("b", "u2"), UngVien("c", "u3")]

    assert [x.video_id for x in loc_can_quet(uv, set(), gioi_han=2)] == ["a", "b"]


@pytest.mark.parametrize("gioi_han", [0, -1, 10])
def test_loc_can_quet_khong_cat_khi_gioi_han_khong_ap_dung(gioi_han):
    uv = [UngVien("a", "u1"), UngVien("b", "u2")]

    assert loc_can_quet(uv, set(), gioi_han=gioi_han) == uv


def test_loc_can_quet_danh_sach_rong():
    assert loc_can_quet([], {"a"}, gioi_han=3) == []
