#!/usr/bin/env python3
"""
BIOS Logo 一鍵替換工具 v3
==========================
⚠️  警告：修改 BIOS 有磚機風險！使用前請務必備份！作者不負任何責任。
適用於 Linux + flashrom + UEFIExtract（自動從原始碼編譯）

使用方式：
    sudo python3 bios_logo_replace.py --logo your_logo.png
    sudo python3 bios_logo_replace.py --logo your_logo.png --skip-flash

前置依賴安裝：
    sudo apt install flashrom imagemagick cmake g++ git
"""

import argparse
import os
import subprocess
import sys
import shutil
from pathlib import Path

# ─── 常數設定 ─────────────────────────────────────────────────────────────────
UEFI_TOOL_REPO   = "https://github.com/LongSoft/UEFITool.git"
UEFI_TOOL_TAG    = "A72"                    # 最新穩定版
UEFI_TOOL_DIR    = "UEFITool_src"
UEFI_EXTRACT_BIN = "./UEFIExtract"

LOGO_GUID        = "7BB28B99-61BB-11D5-9A5D-0090273FC14D"
BACKUP_FILE      = "original_bios.bin"
MODIFIED_FILE    = "modified_bios.bin"
NEW_LOGO_BMP      = "new_logo.jpg"


# ─── 工具函式 ─────────────────────────────────────────────────────────────────
def run(cmd: list, check=True, capture=False, cwd=None) -> subprocess.CompletedProcess:
    print(f"  ▶ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        cmd, check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True, cwd=cwd,
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        print(f"\n❌ 指令失敗 (returncode={result.returncode})")
        if stderr: print(f"   stderr: {stderr}")
        if stdout: print(f"   stdout: {stdout}")
        sys.exit(1)
    return result


def check_root():
    if os.geteuid() != 0:
        print("❌ 請用 sudo 執行：sudo python3 bios_logo_replace.py ...")
        sys.exit(1)


def require_tool(name: str, install_hint: str = ""):
    if not shutil.which(name):
        print(f"❌ 找不到工具：{name}")
        if install_hint:
            print(f"   請執行：{install_hint}")
        sys.exit(1)


# ─── 步驟函式 ─────────────────────────────────────────────────────────────────
def step_build_uefitool():
    """
    從原始碼編譯 UEFIExtract（Linux 沒有預編譯 binary）。
    需要：git, cmake, g++
    """
    print("\n[步驟 1] 編譯 UEFIExtract NE（Linux 無預編譯版，需自行編譯）")

    if Path(UEFI_EXTRACT_BIN).exists():
        print(f"  ✔ {UEFI_EXTRACT_BIN} 已存在，略過編譯。")
        return

    # 確認編譯工具存在
    for tool, hint in [
        ("git",   "sudo apt install git"),
        ("cmake", "sudo apt install cmake"),
        ("g++",   "sudo apt install g++"),
    ]:
        require_tool(tool, hint)

    # Clone 指定 tag
    src_dir = Path(UEFI_TOOL_DIR)
    if src_dir.exists():
        shutil.rmtree(src_dir)

    print(f"  Clone UEFITool {UEFI_TOOL_TAG}...")
    run(["git", "clone", "--depth=1", "--branch", UEFI_TOOL_TAG, UEFI_TOOL_REPO, str(src_dir)])

    # 建立 build 目錄並 cmake + make
    build_dir = src_dir / "build_extract"
    build_dir.mkdir()

    extract_src = (src_dir / "UEFIExtract").resolve()
    print("  cmake...")
    run(["cmake", str(extract_src)], cwd=str(build_dir))

    cpu_count = os.cpu_count() or 2
    print(f"  make -j{cpu_count}...")
    run(["make", f"-j{cpu_count}"], cwd=str(build_dir))

    # 找到編譯後的 binary（cmake 輸出為小寫 uefiextract）
    built = list(build_dir.rglob("uefiextract")) or list(build_dir.rglob("UEFIExtract"))
    if not built:
        print("❌ 編譯完成但找不到 UEFIExtract binary。")
        sys.exit(1)

    shutil.copy(built[0], UEFI_EXTRACT_BIN)
    os.chmod(UEFI_EXTRACT_BIN, 0o755)
    print(f"  ✔ 編譯完成：{UEFI_EXTRACT_BIN}")


def step_backup_bios():
    print("\n[步驟 2] 備份現有 BIOS")
    if Path(BACKUP_FILE).exists():
        ans = input(f"  ⚠  '{BACKUP_FILE}' 已存在，是否重新備份？[y/N] ").strip().lower()
        if ans != "y":
            print("  ✔ 沿用現有備份。")
            return
    run(["flashrom", "--programmer", "internal", "-r", BACKUP_FILE])
    size_mb = Path(BACKUP_FILE).stat().st_size // 1024 // 1024
    print(f"  ✔ BIOS 已備份至 {BACKUP_FILE}（{size_mb} MB）")


def step_extract_and_find_logo() -> Path:
    print(f"\n[步驟 3] 解包 BIOS 並搜尋 Logo GUID: {LOGO_GUID}")

    dump_dir = Path(BACKUP_FILE + ".dump")
    if dump_dir.exists():
        shutil.rmtree(dump_dir)

    run([UEFI_EXTRACT_BIN, BACKUP_FILE, "all"])

    if not dump_dir.exists():
        print(f"❌ 解包失敗，找不到 {dump_dir}")
        sys.exit(1)

    guid_lower = LOGO_GUID.lower()
    body_candidates = []

    # 搜尋方法 1：路徑名稱含有 GUID
    for p in dump_dir.rglob("body.bin"):
        if guid_lower in str(p).lower():
            body_candidates.append(p)

    # 搜尋方法 2：info.txt 內容含有 GUID
    if not body_candidates:
        for info_file in dump_dir.rglob("info.txt"):
            if guid_lower in info_file.read_text(errors="ignore").lower():
                candidate = info_file.parent / "body.bin"
                if candidate.exists():
                    body_candidates.append(candidate)

    if not body_candidates:
        print(f"❌ 找不到 GUID {LOGO_GUID} 的 section。")
        print("   請手動用 UEFITool GUI 找到正確 GUID，修改腳本頂部的 LOGO_GUID。")
        _print_sample_guids(dump_dir)
        sys.exit(1)

    body_path = body_candidates[0]
    print(f"  ✔ 找到 Logo body：{body_path}（{body_path.stat().st_size} bytes）")
    return body_path


def _print_sample_guids(dump_dir: Path):
    print("\n   BIOS 中找到的部分 GUID（前 20 個）：")
    count = 0
    seen = set()
    for info_file in dump_dir.rglob("info.txt"):
        for line in info_file.read_text(errors="ignore").splitlines():
            s = line.strip()
            if len(s) == 36 and s.count("-") == 4 and s not in seen:
                seen.add(s)
                print(f"     {s}")
                count += 1
                if count >= 20:
                    return


def detect_image_ext(data: bytes) -> str:
    """根據 magic bytes 判斷圖片格式，回傳副檔名（含點）。"""
    if data[:2] == b'BM':
        return ".bmp"
    if data[:3] == b'\xff\xd8\xff':
        return ".jpg"
    if data[:4] == b'\x89PNG':
        return ".png"
    return None


def find_real_logo(body_path: Path) -> tuple:
    """
    UEFI 有多層包裝：body.bin 可能只是壓縮容器。
    往子目錄遞迴搜尋，找到真正包含圖片 magic bytes 的檔案。
    同時也嘗試 unc_data.bin（解壓縮資料），並跳過前幾個 bytes 的 section header。
    回傳 (真實圖片 bytes, 副檔名)。
    """
    search_dir = body_path.parent

    candidates = []
    # 搜尋此目錄及所有子目錄的 body.bin 和 unc_data.bin
    for fname in ["unc_data.bin", "body.bin"]:
        for p in search_dir.rglob(fname):
            candidates.append(p)

    for p in candidates:
        raw = p.read_bytes()
        # 直接嘗試
        ext = detect_image_ext(raw)
        if ext:
            return raw, ext
        # UEFI section header 通常是 4 bytes，跳過後試試
        for skip in [4, 8, 16, 24]:
            if len(raw) > skip:
                ext = detect_image_ext(raw[skip:])
                if ext:
                    return raw[skip:], ext

    # 都找不到，回傳原始 body.bin
    raw = body_path.read_bytes()
    return raw, ".bin"


def step_get_logo_size(body_path: Path) -> tuple:
    print("\n[步驟 4] 讀取原始 Logo 尺寸")
    img_data, ext = find_real_logo(body_path)
    print(f"  偵測到格式：{ext}")

    if ext == ".bin":
        print("❌ 無法識別圖片格式，請用 --width / --height 手動指定尺寸。")
        sys.exit(1)

    tmp = Path(f"_tmp_logo_check{ext}")
    tmp.write_bytes(img_data)
    result = run(["identify", "-format", "%wx%h", str(tmp)], capture=True)
    tmp.unlink(missing_ok=True)
    size_str = result.stdout.strip()
    try:
        w, h = map(int, size_str.split("x"))
    except ValueError:
        print(f"❌ 無法解析尺寸：'{size_str}'，請用 --width / --height 手動指定。")
        sys.exit(1)
    print(f"  ✔ 原始 Logo 尺寸：{w} x {h}")
    return w, h


def step_convert_logo(input_logo: str, width: int, height: int, target_size: int):
    """
    輸出 JPEG，並用二分搜尋找到最接近 target_size 的品質值。
    BIOS 內的 Logo 是壓縮格式，大小必須盡量接近原始，否則 patch 後可能無法開機。
    """
    print(f"\n[步驟 5] 轉換新 Logo → {width}x{height} JPEG（目標大小：{target_size} bytes）")

    lo, hi = 1, 95
    best_quality = 50
    best_diff = float('inf')

    for _ in range(10):  # 最多 10 次二分
        mid = (lo + hi) // 2
        tmp = Path("_quality_test.jpg")
        run([
            "convert", input_logo,
            "-resize", f"{width}x{height}!",
            "-quality", str(mid),
            str(tmp),
        ], check=False)
        if not tmp.exists():
            break
        size = tmp.stat().st_size
        diff = abs(size - target_size)
        if diff < best_diff:
            best_diff = diff
            best_quality = mid
        if size > target_size:
            hi = mid - 1
        elif size < target_size:
            lo = mid + 1
        else:
            break
        tmp.unlink(missing_ok=True)

    # 用最佳品質輸出正式檔案
    run([
        "convert", input_logo,
        "-resize", f"{width}x{height}!",
        "-quality", str(best_quality),
        NEW_LOGO_BMP,
    ])
    final_size = Path(NEW_LOGO_BMP).stat().st_size
    print(f"  ✔ 轉換完成：{NEW_LOGO_BMP}（{final_size} bytes，品質={best_quality}，差距={abs(final_size-target_size)} bytes）")
    if abs(final_size - target_size) > target_size * 0.1:
        print(f"  ⚠  大小差距超過 10%（原始 {target_size} bytes vs 新 {final_size} bytes）")
        print(f"     刷入後 Logo 可能顯示異常，但不會磚機（BIOS 通常會 fallback 預設 Logo）。")


def step_patch_bios(body_path: Path):
    print("\n[步驟 6] Binary patch BIOS")

    # 取得真正的圖片 bytes（跳過 UEFI section header）
    img_data, ext = find_real_logo(body_path)
    new_body  = Path(NEW_LOGO_BMP).read_bytes()
    bios_data = Path(BACKUP_FILE).read_bytes()

    # 先嘗試找原始圖片 bytes
    original_body = img_data
    offset = bios_data.find(original_body)

    # 找不到就 fallback 用完整 body.bin
    if offset == -1:
        original_body = body_path.read_bytes()
        offset = bios_data.find(original_body)

    if offset == -1:
        print("❌ 在 BIOS bytes 中找不到原始 Logo，無法 patch。")
        print("   請改用 UEFITool GUI 手動替換。")
        sys.exit(1)

    print(f"  ✔ 找到原始 Logo：offset 0x{offset:08X}")
    print(f"  原始大小：{len(original_body)} bytes  |  新 Logo：{len(new_body)} bytes")

    if len(new_body) != len(original_body):
        diff = abs(len(new_body) - len(original_body))
        print(f"\n  ⚠  大小不一致，差距 {diff} bytes！BIOS section 大小必須完全相同，否則可能磚機！")
        ans = input("  強制 patch（padding/截斷）？（強烈不建議）[y/N] ").strip().lower()
        if ans != "y":
            print("  已取消。請重新調整圖片讓 BMP 大小等於原始大小。")
            sys.exit(0)
        if len(new_body) < len(original_body):
            new_body = new_body + b'\x00' * (len(original_body) - len(new_body))
        else:
            new_body = new_body[:len(original_body)]

    patched = bios_data[:offset] + new_body + bios_data[offset + len(original_body):]
    Path(MODIFIED_FILE).write_bytes(patched)
    print(f"  ✔ 修改後 BIOS 已儲存至 {MODIFIED_FILE}")


def step_cleanup(logo_path: str):
    """清理暫存檔案，只保留備份 BIOS 和原始 Logo。"""
    print("\n[清理] 移除暫存檔案")
    to_remove = [
        Path(MODIFIED_FILE),
        Path(NEW_LOGO_BMP),
        Path("_quality_test.jpg"),
        Path("_tmp_logo_check.jpg"),
        Path("_tmp_logo_check.bmp"),

        Path(BACKUP_FILE + ".dump"),
        Path(UEFI_TOOL_DIR),
    ]
    for p in to_remove:
        if p is None:
            continue
        try:
            if p.is_dir():
                shutil.rmtree(p)
                print(f"  🗑  刪除目錄：{p}")
            elif p.exists():
                p.unlink()
                print(f"  🗑  刪除檔案：{p}")
        except Exception as e:
            print(f"  ⚠  無法刪除 {p}：{e}")
    print(f"  ✔ 保留：{BACKUP_FILE}（BIOS 備份）")
    print(f"  ✔ 保留：{logo_path}（原始 Logo）")


def step_flash_bios():
    print("\n[步驟 7] 刷入修改後的 BIOS")
    print(f"  備份保留在：{BACKUP_FILE}（出問題可用此還原）")
    ans = input("  ⚠  確定要刷入？[y/N] ").strip().lower()
    if ans != "y":
        print(f"  已取消。手動刷入：sudo flashrom --programmer internal -w {MODIFIED_FILE}")
        sys.exit(0)
    run(["flashrom", "--programmer", "internal", "-w", MODIFIED_FILE])
    print("  ✔ 刷入完成！請重新開機確認。")


# ─── 主程式 ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BIOS Logo 一鍵替換工具 v3")
    parser.add_argument("--logo",       required=True, help="新 Logo PNG 路徑")
    parser.add_argument("--width",      type=int,      help="手動指定寬度（略過自動偵測）")
    parser.add_argument("--height",     type=int,      help="手動指定高度（略過自動偵測）")
    parser.add_argument("--skip-flash", action="store_true", help="只產生 modified_bios.bin，不刷入")
    args = parser.parse_args()

    print("=" * 60)
    print("  BIOS Logo 一鍵替換工具 v3")
    print("  ⚠  修改 BIOS 有風險！請確保已充分了解流程！")
    print("=" * 60)

    check_root()
    require_tool("flashrom", "sudo apt install flashrom")
    require_tool("convert",  "sudo apt install imagemagick")
    require_tool("identify", "sudo apt install imagemagick")

    if not Path(args.logo).exists():
        print(f"❌ 找不到 Logo 檔案：{args.logo}")
        sys.exit(1)

    step_build_uefitool()
    step_backup_bios()
    body_path = step_extract_and_find_logo()

    if args.width and args.height:
        width, height = args.width, args.height
        print(f"\n[步驟 4] 使用手動指定尺寸：{width} x {height}")
    else:
        width, height = step_get_logo_size(body_path)

    # 計算原始 Logo 的真實大小（從 unc_data.bin 跳過 4 bytes header）
    img_data, img_ext = find_real_logo(body_path)
    target_size = len(img_data)
    print(f"  原始 Logo 大小：{target_size} bytes（格式：{img_ext}）")

    step_convert_logo(args.logo, width, height, target_size=target_size)
    step_patch_bios(body_path)

    if args.skip_flash:
        print(f"\n✅ 完成！（略過刷入）")
        print(f"   修改後 BIOS：{MODIFIED_FILE}")
        print(f"   手動刷入：sudo flashrom --programmer internal -w {MODIFIED_FILE}")
        ans = input("\n  是否清理暫存檔案？（保留備份和你的 Logo）[Y/n] ").strip().lower()
        if ans != "n":
            step_cleanup(args.logo)
    else:
        step_flash_bios()
        print("\n✅ 全部完成！")
        ans = input("\n  是否清理暫存檔案？（保留備份和你的 Logo）[Y/n] ").strip().lower()
        if ans != "n":
            step_cleanup(args.logo)


if __name__ == "__main__":
    main()
