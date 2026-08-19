# -*- coding: utf-8 -*-
r"""cap_nhat.py — Tự cập nhật tool từ GitHub theo TAG phiên bản.

VÌ SAO THEO TAG CHỨ KHÔNG THEO NHÁNH `main`

Bạn vẫn phải làm việc trên `main` hằng ngày. Nếu máy người dùng bám `main` thì mọi
commit dở dang đều rơi xuống máy họ. Bám tag nghĩa là bạn quyết định lúc nào phát
hành: `git tag v2.2 && git push --tags`. Hỏng thì `git tag -d`/đẩy lại tag cũ, hoặc
người dùng chạy `CapNhat.bat --ban v2.1` để lùi.

BA NGUYÊN TẮC AN TOÀN — đừng phá khi sửa file này

1. **Không bao giờ làm mất việc của người dùng.** Cây làm việc bẩn (có sửa đổi chưa
   commit) thì DỪNG, không `checkout --force`, không `stash`. Người dùng có thể đã sửa
   tay một tham số; nuốt mất thay đổi đó tệ hơn nhiều so với chạy bản cũ thêm một hôm.
2. **Không bao giờ để tool không chạy được.** Mọi lỗi — thiếu git, mất mạng, khoá SSH
   sai, tag không tồn tại — đều phải trả về "bỏ qua" chứ không được ném ra ngoài.
   `ChayTool.bat` gọi hàm này TRƯỚC khi mở giao diện; hỏng ở đây mà chặn luôn tool là
   biến một bất tiện thành một sự cố.
3. **Không bao giờ đụng dữ liệu người dùng.** `data/`, `ketqua/`, `bin/`,
   `google_key.json`, `cau_hinh.json`, `watchlist.json` đều nằm trong `.gitignore` nên
   `git checkout` không chạm tới. Nếu thêm file dữ liệu mới, PHẢI thêm vào `.gitignore`
   trước — xem test `test_du_lieu_nguoi_dung_khong_bi_git_theo_doi`.

DÙNG

    python cap_nhat.py             # kiểm tra rồi cập nhật nếu có bản mới
    python cap_nhat.py --kiem-tra  # chỉ xem, không đụng gì
    python cap_nhat.py --ban v2.1  # về đúng một bản cụ thể (lùi phiên bản)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

GOC = os.path.dirname(os.path.abspath(__file__))

# Lệnh git có thể treo khi mạng chập chờn hoặc SSH chờ nhập passphrase. Người dùng
# đang đợi tool mở, không được bắt họ chờ vô hạn.
TIMEOUT_S = 45
TIMEOUT_MANG_S = 90


@dataclass
class KetQua:
    """Kết quả một lượt kiểm tra/cập nhật. Không bao giờ ném lỗi ra ngoài."""

    ok: bool = False              # có thực sự đổi sang bản mới không
    ban_cu: str = ""
    ban_moi: str = ""
    can_cai_lai_thu_vien: bool = False
    thong_bao: list = field(default_factory=list)

    def bao(self, s: str) -> "KetQua":
        self.thong_bao.append(s)
        return self


def _git(args: list, goc: str, timeout: int = TIMEOUT_S) -> tuple:
    """Chạy git, trả (thành_công, đầu_ra). Không bao giờ ném lỗi.

    `GIT_TERMINAL_PROMPT=0` và `GIT_SSH_COMMAND=... -o BatchMode=yes` để git thất bại
    NGAY thay vì treo chờ người dùng nhập mật khẩu — quan trọng với máy chạy tự động
    qua Task Scheduler, nơi không có ai ngồi trước màn hình.
    """
    # BẮT BUỘC kiểm thư mục trước. `subprocess.run(cwd=None)` chạy git ở thư mục hiện
    # hành của tiến trình — tức là trả lời về MỘT REPO KHÁC mà không báo lỗi gì. Lỗi
    # này đã xảy ra thật: `ban_hien_tai(None)` trả về HEAD của repo đang phát triển
    # thay vì repo được hỏi. Sai âm thầm kiểu đó nguy hiểm hơn hẳn một thông báo lỗi.
    if not goc or not os.path.isdir(goc):
        return False, f"Không có thư mục: {goc!r}"

    moi_truong = dict(os.environ)
    moi_truong["GIT_TERMINAL_PROMPT"] = "0"
    moi_truong.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    try:
        r = subprocess.run(
            ["git", *args], cwd=goc, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=moi_truong)
    except FileNotFoundError:
        # Chỉ đúng khi thiếu chính file git.exe: thư mục đã được kiểm ở trên.
        return False, "Chưa cài git trên máy này."
    except subprocess.TimeoutExpired:
        return False, f"Lệnh git quá {timeout} giây, có thể do mạng."
    except OSError as e:
        return False, f"Không chạy được git: {e}"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()
    return True, (r.stdout or "").strip()


def thu_muc_repo(goc: str = GOC) -> Optional[str]:
    """Thư mục gốc của repo git chứa dự án.

    Cần hàm này vì repo nằm ở thư mục CHA (`Tool_Quet/`) còn mã nguồn nằm trong
    `TimClipPro/`; chạy git ngay tại thư mục dự án sẽ sai gốc.
    """
    ok, ra = _git(["rev-parse", "--show-toplevel"], goc)
    return os.path.abspath(ra) if ok and ra else None


def cay_lam_viec_sach(repo: str) -> tuple:
    """(sạch?, mô tả). Bẩn nghĩa là có sửa đổi chưa commit — không được cập nhật đè."""
    ok, ra = _git(["status", "--porcelain", "--untracked-files=no"], repo)
    if not ok:
        return False, ra
    if ra:
        so = len(ra.splitlines())
        return False, f"{so} file đang có thay đổi chưa lưu vào git"
    return True, ""


def ban_hien_tai(repo: str) -> str:
    """Tên tag đang dùng; không ở đúng tag nào thì trả mã commit ngắn."""
    ok, ra = _git(["describe", "--tags", "--exact-match"], repo)
    if ok and ra:
        return ra
    ok, ra = _git(["rev-parse", "--short", "HEAD"], repo)
    return ra if ok else "(không rõ)"


def ban_moi_nhat(repo: str) -> str:
    """Tag mới nhất đã biết ở local. Gọi `lay_tag_moi()` trước để có dữ liệu mới."""
    ok, ra = _git(["tag", "--sort=-v:refname"], repo)
    if not ok or not ra:
        return ""
    return ra.splitlines()[0].strip()


def lay_tag_moi(repo: str) -> tuple:
    """Tải danh sách tag mới từ GitHub. Trả (thành_công, mô_tả_lỗi)."""
    ok, ra = _git(["fetch", "--tags", "--quiet"], repo, timeout=TIMEOUT_MANG_S)
    return ok, "" if ok else ra


def la_ban_moi_hon(repo: str, hien_tai: str, dich: str) -> bool:
    """`dich` có thực sự MỚI HƠN bản đang dùng không?

    Rào chắn cho MÁY DEV. Trên máy của bạn, `main` gần như luôn đi trước tag mới nhất
    (ví dụ: HEAD ở commit 1682ce6 trong khi tag mới nhất là v2.1). Không có kiểm tra
    này thì mở tool trên chính máy dev sẽ *lùi* về v2.1 và ném bạn vào detached HEAD —
    mất chỗ đang làm việc mà không hề báo.

    Cách xác định: bản đích mới hơn khi và chỉ khi commit hiện tại là TỔ TIÊN của nó.
    """
    ok, _ = _git(["merge-base", "--is-ancestor", hien_tai, dich], repo)
    return ok


def _requirements_doi(repo: str, tu: str, den: str) -> bool:
    """Giữa hai bản, file requirements có đổi không?

    Nếu có mà không cài lại thì máy đích chạy mã mới bằng thư viện cũ — lỗi kiểu này
    rất khó chẩn đoán vì nó hiện ra ở chỗ chẳng liên quan.
    """
    ok, ra = _git(
        ["diff", "--name-only", f"{tu}..{den}", "--",
         "TimClipPro/requirements.txt", "TimClipPro/constraints.txt",
         "requirements.txt", "constraints.txt"], repo)
    return bool(ok and ra.strip())


def cap_nhat(goc: str = GOC, ban_muon: str = "", chi_kiem_tra: bool = False) -> KetQua:
    """Kiểm tra và (nếu cần) chuyển sang bản mới. KHÔNG BAO GIỜ ném lỗi ra ngoài."""
    kq = KetQua()

    repo = thu_muc_repo(goc)
    if not repo:
        return kq.bao("Chưa cài git hoặc thư mục này không nằm trong repo — bỏ qua "
                      "bước cập nhật, tool vẫn chạy bình thường.")

    kq.ban_cu = ban_hien_tai(repo)

    lay_ok, loi_lay = lay_tag_moi(repo)
    if not lay_ok:
        kq.bao(f"Không lấy được bản mới từ GitHub ({loi_lay[:120]}). "
               f"Chạy tiếp bản đang có: {kq.ban_cu}.")
        return kq

    dich = ban_muon or ban_moi_nhat(repo)
    if not dich:
        return kq.bao("Trên GitHub chưa có tag phiên bản nào — bỏ qua.")
    kq.ban_moi = dich

    if dich == kq.ban_cu:
        return kq.bao(f"Đang dùng bản mới nhất: {kq.ban_cu}.")

    # `--ban` là yêu cầu tường minh của người dùng (thường để LÙI bản) nên được phép
    # đi ngược; còn cập nhật tự động thì tuyệt đối chỉ tiến, không lùi.
    if not ban_muon and not la_ban_moi_hon(repo, kq.ban_cu, dich):
        kq.ban_moi = ""
        return kq.bao(
            f"Bản đang chạy ({kq.ban_cu}) đã đi trước tag mới nhất ({dich}) — "
            "đây là máy phát triển, không tự lùi bản. Muốn về đúng tag thì chạy "
            f"CapNhat.bat --ban {dich}.")

    kq.bao(f"Có bản mới: {kq.ban_cu} → {dich}")
    if chi_kiem_tra:
        return kq

    # Rào chắn quan trọng nhất: không bao giờ nuốt mất thay đổi của người dùng.
    sach, mo_ta = cay_lam_viec_sach(repo)
    if not sach:
        return kq.bao(
            f"DỪNG cập nhật vì {mo_ta}. Thay đổi của bạn sẽ không bị mất. "
            "Lưu hoặc hoàn tác các thay đổi đó rồi chạy lại CapNhat.bat.")

    can_cai = _requirements_doi(repo, kq.ban_cu, dich)

    ok, loi = _git(["checkout", "--quiet", dich], repo)
    if not ok:
        return kq.bao(f"Không chuyển được sang {dich}: {loi[:160]}. "
                      f"Vẫn đang ở bản {kq.ban_cu}.")

    kq.ok = True
    kq.can_cai_lai_thu_vien = can_cai
    kq.bao(f"Đã cập nhật lên {dich}.")
    if can_cai:
        kq.bao("Danh sách thư viện có thay đổi — cần cài lại (CapNhat.bat làm tự động).")
    return kq


def main() -> int:
    ap = argparse.ArgumentParser(description="Cập nhật TimClip Pro từ GitHub theo tag.")
    ap.add_argument("--kiem-tra", action="store_true",
                    help="Chỉ xem có bản mới không, không đổi gì")
    ap.add_argument("--ban", default="",
                    help="Chuyển về đúng một tag cụ thể, ví dụ v2.1 (dùng để lùi bản)")
    a = ap.parse_args()

    kq = cap_nhat(ban_muon=a.ban, chi_kiem_tra=a.kiem_tra)
    for dong in kq.thong_bao:
        print(dong)
    return ma_thoat(kq)


# Mã thoát để file .bat biết phải làm gì tiếp. Dùng số chứ không phải chuỗi vì `cmd`
# chỉ so sánh được errorlevel.
KHONG_DOI = 0
DA_DOI = 10           # đã đổi bản, thư viện giữ nguyên
DA_DOI_CAN_PIP = 11   # đã đổi bản VÀ danh sách thư viện có thay đổi


def ma_thoat(kq: KetQua) -> int:
    """Mã thoát tương ứng với kết quả.

    Vì sao .bat phải biết "đã đổi bản": `git checkout` có thể thay chính file .bat đang
    chạy, mà `cmd` đọc file lệnh theo VỊ TRÍ BYTE trong lúc thực thi — file đổi giữa
    chừng thì các dòng sau bị đọc lệch và chạy loạn. Nên sau khi cập nhật, .bat phải
    khởi động lại chính nó thay vì chạy tiếp bằng nội dung cũ đã lệch.
    """
    if not kq.ok:
        return KHONG_DOI
    return DA_DOI_CAN_PIP if kq.can_cai_lai_thu_vien else DA_DOI


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
