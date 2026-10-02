# -*- coding: utf-8 -*-
"""Test tham số subframe shifts mà không chạy audfprint hay xử lý audio thật."""

from kho_gia import ghi_kho, ghi_kho_tu_lenh


def _chuan_bi_lenh(engine, tmp_path, monkeypatch):
    thu_muc = tmp_path / "clips"
    thu_muc.mkdir()
    (thu_muc / "clip.wav").write_bytes(b"fake audio")
    engine.add_kho("Kho shifts", str(thu_muc))
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    cac_lenh = []

    def run_stream(lenh, on_line=None, **kwargs):
        cac_lenh.append(lenh)
        if on_line:
            if "match" in lenh:
                on_line("Analyzed #1")
            else:
                on_line("ingesting #1: clip.wav...")
                ghi_kho_tu_lenh(lenh)
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    return thu_muc, cac_lenh


def test_shifts_0_khong_truyen_co(engine, tmp_path, monkeypatch):
    thu_muc, cac_lenh = _chuan_bi_lenh(engine, tmp_path, monkeypatch)
    engine.config.shifts_kho = 0
    engine.config.shifts_quet = 0

    engine.build_database(str(thu_muc), "new")
    engine._match_chunks(["chunk.wav"])

    assert len(cac_lenh) == 2
    assert all("--shifts" not in lenh for lenh in cac_lenh)


def test_shifts_4_co_trong_lenh(engine, tmp_path, monkeypatch):
    thu_muc, cac_lenh = _chuan_bi_lenh(engine, tmp_path, monkeypatch)
    engine.config.shifts_kho = 4
    engine.config.shifts_quet = 4

    engine.build_database(str(thu_muc), "new")
    engine._match_chunks(["chunk.wav"])

    assert len(cac_lenh) == 2
    for lenh in cac_lenh:
        vi_tri = lenh.index("--shifts")
        assert lenh[vi_tri + 1] == "4"
    assert engine.list_khos()[0]["shifts"] == 4


def test_shifts_am_duoc_kep_ve_0(engine, tmp_path, monkeypatch):
    thu_muc, cac_lenh = _chuan_bi_lenh(engine, tmp_path, monkeypatch)
    engine.config.shifts_kho = -2
    engine.config.shifts_quet = -3

    engine.build_database(str(thu_muc), "new")
    engine._match_chunks(["chunk.wav"])

    assert all("--shifts" not in lenh for lenh in cac_lenh)
    assert engine.list_khos()[0]["shifts"] == 0


def test_canh_bao_khi_kho_lech_shifts(engine, tmp_path, monkeypatch):
    thu_muc, _ = _chuan_bi_lenh(engine, tmp_path, monkeypatch)
    # Kho cũ không có khóa "shifts" phải được hiểu là shifts=0.
    ghi_kho(engine.db_file, [(str(tmp_path / "clip_cu.wav"), 7)])
    engine.config.shifts_kho = 4

    ket_qua = engine.build_database(str(thu_muc), "add")

    assert ket_qua["canh_bao"]
    assert "shifts=0" in ket_qua["canh_bao"][0]
    assert "shifts=4" in ket_qua["canh_bao"][0]
    assert "tạo lại kho từ đầu" in ket_qua["canh_bao"][0]
    # Không được che mất cảnh báo bằng cách gắn nhãn kho hỗn hợp là shifts=4.
    assert "shifts" not in engine.list_khos()[0]
