# -*- coding: utf-8 -*-
"""Cookie là credential — không được lọt ra log dưới bất kỳ đường nào.

Bối cảnh 2026-08-18: ngay khi thêm hỗ trợ cookie, một vòng phản biện phát hiện đường
rò. ``YoutubeDLCookieJar.load()`` của yt-dlp gặp dòng cookies.txt sai định dạng thì gọi
``write_string()`` in NGUYÊN VĂN dòng đó ra ``sys.stderr`` — kèm giá trị
``__Secure-1PSID``, đủ để chiếm tài khoản. Cờ ``quiet``/``no_warnings`` KHÔNG chặn được
vì ``write_string`` ghi thẳng stderr chứ không qua logger.

Đích đến: ``cli.py watch --log`` gọi ``nhat_ky.mo_nhat_ky()``, hàm này đấu stderr vào
``ketqua/giamsat_*.log`` — file giữ 30 ngày, nằm chung thư mục với CSV mà người dùng
hay nén gửi đi khi nhờ hỗ trợ. Cả ``GiamSat.bat`` lẫn ``ChayMayPhu.bat`` đều chạy
đường này.

Hai lớp phòng vệ, test cả hai. Giá trị bí mật trong test là chuỗi giả, không có thật.
"""

import io

import nhat_ky
import pytest
import ytdlp_chung as y

BI_MAT = "FAKE_SECRET_KHONG_CO_THAT_12345"


def _cookie_hong(tmp_path):
    """Đúng lỗi hay gặp nhất: mở bằng Notepad rồi lưu lại, TAB thành dấu cách."""
    p = tmp_path / "cookies.txt"
    p.write_text(
        "# Netscape HTTP Cookie File\n"
        f".youtube.com TRUE / TRUE 9999999999 __Secure-1PSID {BI_MAT}\n",
        encoding="utf-8")
    return p


def _cookie_dung(tmp_path, ten="cookies_ok.txt"):
    p = tmp_path / ten
    p.write_text(
        "# Netscape HTTP Cookie File\n"
        + "\t".join([".youtube.com", "TRUE", "/", "TRUE", "9999999999",
                     "__Secure-1PSID", BI_MAT]) + "\n",
        encoding="utf-8")
    return p


# ------------------------------------------------ lớp 1: chặn từ đầu nguồn

def test_file_cookie_sai_dinh_dang_bi_chan_truoc_khi_toi_yt_dlp(tmp_path):
    with pytest.raises(y.LoiFileCookie):
        y.CauHinhMang(cookiefile=str(_cookie_hong(tmp_path))).tuy_chon()


def test_thong_bao_loi_chi_neu_so_dong_khong_neu_noi_dung(tmp_path):
    """Nếu thông báo kèm nội dung dòng thì chính nó lại là đường rò mới."""
    with pytest.raises(y.LoiFileCookie) as ei:
        y.kiem_tra_file_cookie(str(_cookie_hong(tmp_path)))
    tin = str(ei.value)
    assert BI_MAT not in tin
    assert "__Secure-1PSID" not in tin
    assert "dòng 2" in tin, "phải chỉ đúng dòng hỏng để người dùng sửa được"


def test_file_cookie_dung_dinh_dang_thi_di_qua(tmp_path):
    p = _cookie_dung(tmp_path)
    assert y.CauHinhMang(cookiefile=str(p)).tuy_chon()["cookiefile"] == str(p)


def test_file_cookie_khong_ton_tai_bao_loi_ro_rang(tmp_path):
    with pytest.raises(y.LoiFileCookie):
        y.kiem_tra_file_cookie(str(tmp_path / "khong-he-co.txt"))


def test_file_cookie_rong_bi_tu_choi(tmp_path):
    p = tmp_path / "rong.txt"
    p.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    with pytest.raises(y.LoiFileCookie):
        y.kiem_tra_file_cookie(str(p))


def test_khong_cau_hinh_cookie_thi_khong_kiem_gi(tmp_path):
    y.CauHinhMang().tuy_chon()          # không được ném lỗi
    y.kiem_tra_file_cookie("")


# ------------------------------------------------ lớp 2: che khi ghi nhật ký

def test_che_dong_canh_bao_cookie_cua_yt_dlp():
    tho = (f"WARNING: skipping cookie file entry due to invalid length 1: "
           f"'.youtube.com ... __Secure-1PSID {BI_MAT}'\n")
    assert BI_MAT not in nhat_ky.che_bi_mat(tho)


def test_che_theo_tung_dong_khong_nuot_thong_tin_chan_doan_khac():
    tho = (f"WARNING: skipping cookie file entry: '{BI_MAT}'\n"
           "[download] 12.3% of 45MB\n"
           "ERROR: HTTP Error 403: Forbidden\n")
    sach = nhat_ky.che_bi_mat(tho)
    assert BI_MAT not in sach
    assert "[download] 12.3% of 45MB" in sach
    assert "HTTP Error 403" in sach


def test_dong_binh_thuong_khong_bi_dong_cham():
    tho = "[download] 100% of 76.77MiB\nXONG: tải mới 12 video.\n"
    assert nhat_ky.che_bi_mat(tho) == tho


def test_ghi_song_song_khong_de_bi_mat_vao_file_log(tmp_path):
    """Chạy qua đúng lớp mà nhat_ky.mo_nhat_ky() cắm vào sys.stderr."""
    duong_dan = tmp_path / "giamsat.log"
    man_hinh = io.StringIO()
    with io.open(duong_dan, "w", encoding="utf-8") as f:
        ghi = nhat_ky._GhiSongSong(man_hinh, f)
        ghi.write(f"WARNING: skipping cookie file entry: '{BI_MAT}'\n")
        ghi.write("[download] 50%\n")
    noi_dung = duong_dan.read_text(encoding="utf-8")
    assert BI_MAT not in noi_dung
    assert BI_MAT not in man_hinh.getvalue(), "màn hình cũng không được hiện"
    assert "[download] 50%" in noi_dung


# ------------------------------------------------ chống rò qua cấu hình đã lưu

def test_chi_luu_duong_dan_khong_bao_gio_luu_noi_dung(tmp_path):
    """cau_hinh.lay_tu_config() serialize MỌI trường Config ra đĩa mà không có danh
    sách trắng — nên trường cookie phải là đường dẫn, tuyệt đối không phải nội dung."""
    import cau_hinh
    from engine import Config

    duong_dan = str(_cookie_dung(tmp_path))
    cfg = Config()
    cfg.ytdlp_cookiefile = duong_dan
    cau_hinh.ghi_cau_hinh(str(tmp_path), cau_hinh.lay_tu_config(cfg))
    tren_dia = (tmp_path / cau_hinh.TEN_FILE).read_text(encoding="utf-8")
    assert BI_MAT not in tren_dia, "nội dung cookie không bao giờ được xuống đĩa"
    assert "cookies_ok.txt" in tren_dia, "đường dẫn thì phải lưu, nếu không mất cấu hình"
