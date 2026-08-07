# -*- coding: utf-8 -*-
"""Test logic thuần cho Engine._merge(), không dùng audio thật."""

from engine import ScanResult


def _ket_qua_tho(
    clip: str = "C:/kho/clip.opus",
    bat_dau: float = 100.0,
    khop: float = 30.0,
    t_clip: float = 0.0,
    so_hash: int = 100,
    align: float = 100.0,
) -> dict:
    return {
        "clip": clip,
        "bat_dau": bat_dau,
        "khop": khop,
        "t_clip": t_clip,
        "hash": so_hash,
        "align": align,
    }


def test_merge_list_rong(engine):
    assert engine._merge([]) == []


def test_merge_loai_ket_qua_duoi_min_hash(engine):
    engine.config.min_hash = 100
    tho = [_ket_qua_tho(so_hash=99)]

    assert engine._merge(tho) == []


def test_merge_loai_ket_qua_duoi_min_match_s(engine):
    engine.config.min_match_s = 10
    tho = [_ket_qua_tho(khop=9)]

    assert engine._merge(tho) == []


def test_merge_cung_clip_align_gan_nhau(engine):
    engine.config.dedup_s = 20
    tho = [
        _ket_qua_tho(bat_dau=100, align=100),
        _ket_qua_tho(bat_dau=105, align=105),
    ]

    assert len(engine._merge(tho)) == 1


def test_merge_cung_clip_align_cach_xa_nhau(engine):
    engine.config.dedup_s = 20
    tho = [
        _ket_qua_tho(bat_dau=100, align=100),
        _ket_qua_tho(bat_dau=200, align=200),
    ]

    assert len(engine._merge(tho)) == 2


def test_merge_khong_gop_hai_clip_khac_nhau(engine):
    engine.config.dedup_s = 20
    tho = [
        _ket_qua_tho(clip="C:/kho/clip-a.opus", align=100),
        _ket_qua_tho(clip="C:/kho/clip-b.opus", align=105),
    ]

    assert len(engine._merge(tho)) == 2


def test_merge_giu_hash_lon_hon(engine):
    engine.config.dedup_s = 20
    tho = [
        _ket_qua_tho(so_hash=50, align=100),
        _ket_qua_tho(so_hash=80, align=105),
    ]

    ket_qua = engine._merge(tho)

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 80


def test_merge_doan_chong_lan_lay_bien_ngoai_cung(engine):
    engine.config.dedup_s = 20
    tho = [
        _ket_qua_tho(bat_dau=100, khop=30, t_clip=0, align=100),
        _ket_qua_tho(bat_dau=120, khop=40, t_clip=15, align=105),
    ]

    ket_qua = engine._merge(tho)

    assert len(ket_qua) == 1
    assert ket_qua[0].start_s == 100
    assert ket_qua[0].end_s == 160


def test_merge_sap_xep_tang_dan_theo_start_s(engine):
    tho = [
        _ket_qua_tho(clip="C:/kho/c.opus", bat_dau=300, align=300),
        _ket_qua_tho(clip="C:/kho/a.opus", bat_dau=100, align=100),
        _ket_qua_tho(clip="C:/kho/b.opus", bat_dau=200, align=200),
    ]

    ket_qua = engine._merge(tho)

    assert [m.start_s for m in ket_qua] == [100, 200, 300]


def test_merge_chi_tra_ten_file_clip(engine):
    tho = [_ket_qua_tho(clip="C:/kho/thu_muc/clip-goc.opus")]

    ket_qua = engine._merge(tho)

    assert ket_qua[0].clip == "clip-goc.opus"


def test_ids_da_quet_loc_dung(engine):
    engine.save_job(
        ScanResult(source_name="A lỗi", source_id="a", status="error"),
        "youtube",
    )
    engine.save_job(
        ScanResult(source_name="A thành công", source_id="a"),
        "youtube",
    )
    engine.save_job(
        ScanResult(source_name="B lỗi", source_id="b", status="error"),
        "youtube",
    )

    assert engine.ids_da_quet() == {"a"}
    assert engine.ids_da_quet(chi_thanh_cong=False) == {"a", "b"}


def test_ids_da_quet_bo_source_id_rong(engine):
    engine.save_job(ScanResult(source_name="Rỗng", source_id=""), "youtube")
    engine.save_job(ScanResult(source_name="None", source_id=None), "youtube")
    engine.save_job(ScanResult(source_name="Hợp lệ", source_id="abc"), "youtube")

    assert engine.ids_da_quet() == {"abc"}


def test_chi_muc_duoc_tao(engine):
    with engine._db() as db:
        rows = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name IN (?, ?)",
            ("idx_jobs_source_id", "idx_matches_job_id"),
        ).fetchall()

    assert {row["name"] for row in rows} == {
        "idx_jobs_source_id",
        "idx_matches_job_id",
    }
