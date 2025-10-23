import os
import time
import argparse
from datetime import datetime
from pathlib import Path
import win32gui
import win32con
import mss
import numpy as np
from PIL import Image

#!/usr/bin/env python3
"""
capture_window_timelapse.py

Windows向け: 指定したウインドウを定期的にキャプチャしてローカル保存するタイムラプススクリプト。

依存:
    pip install mss pillow pywin32 numpy

使い方例:
    python capture_window_timelapse.py --title "メモ帳" --interval 1.0 --out ./timelapse --format png --duration 60
"""


def list_windows():
    if not win32gui:
        print("win32gui が利用できません (Windows専用機能)。")
        return

    def _enum(hwnd, results):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            results.append((hwnd, win32gui.GetWindowText(hwnd)))

    results = []
    win32gui.EnumWindows(_enum, results)
    for hwnd, title in results:
        print(f"{hwnd}: {title}")


def find_window_rect_by_title(substring):
    if not win32gui:
        return None
    matches = []

    def _enum(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if substring.lower() in title.lower():
                results.append((hwnd, title))

    results = []
    win32gui.EnumWindows(_enum, results)
    if not results:
        return None
    hwnd, title = results[0]
    # ウィンドウ矩形を取得 (left, top, right, bottom)
    rect = win32gui.GetWindowRect(hwnd)
    # ウィンドウを前面に出す（任意）
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    return rect


def capture_region_to_image(bbox):
    # bbox: (left, top, right, bottom)
    left, top, right, bottom = bbox
    width = max(1, right - left)
    height = max(1, bottom - top)
    with mss.mss() as sct:
        sct_img = sct.grab({"left": left, "top": top, "width": width, "height": height})
        arr = np.array(sct_img)  # BGRA
        # convert BGRA -> RGB
        rgb = arr[..., :3][..., ::-1]
        img = Image.fromarray(rgb)
        return img


def ensure_outdir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def main():
    p = argparse.ArgumentParser(
        description="ウインドウを定期キャプチャしてローカル保存するタイムラプススクリプト"
    )
    p.add_argument(
        "--title", "-t", help="ウインドウタイトルの一部 (大文字小文字を区別しない)"
    )
    p.add_argument(
        "--interval", "-i", type=float, default=10.0, help="キャプチャ間隔(秒)"
    )
    p.add_argument("--out", "-o", default="./captures", help="出力フォルダ")
    p.add_argument(
        "--format", "-f", choices=["png", "jpg"], default="png", help="保存形式"
    )
    p.add_argument(
        "--duration", "-d", type=float, default=0.0, help="総撮影時間(秒)。0で無制限"
    )
    p.add_argument(
        "--max-frames", type=int, default=0, help="最大フレーム数。0で無制限"
    )
    p.add_argument(
        "--list", action="store_true", help="利用可能なウインドウ一覧を表示して終了"
    )
    args = p.parse_args()

    outdir = ensure_outdir(Path(args.out))

    if args.list:
        list_windows()
        return

    bbox = None
    if args.title:
        rect = find_window_rect_by_title(args.title)
        if rect is None:
            print(f"ウインドウタイトルに一致するものが見つかりません: {args.title}")
            return
        bbox = rect
    else:
        # ウインドウタイトル未指定 -> 全画面をキャプチャ
        with mss.mss() as sct:
            mon = sct.monitors[0]  # 全体
            bbox = (
                mon["left"],
                mon["top"],
                mon["left"] + mon["width"],
                mon["top"] + mon["height"],
            )

    start = time.time()
    frames = 0
    print("キャプチャ開始. Ctrl+C で停止.")
    try:
        while True:
            now = time.time()
            if args.duration > 0 and (now - start) >= args.duration:
                break
            if args.max_frames > 0 and frames >= args.max_frames:
                break

            img = capture_region_to_image(bbox)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = outdir / f"capture_{ts}_{frames:06d}.{args.format}"
            if args.format == "png":
                img.save(filename, "PNG")
            else:
                img.save(filename, "JPEG", quality=90)
            frames += 1
            elapsed = time.time() - now
            sleep_time = max(0.0, args.interval - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("中断されました。")
    print(f"保存完了: {frames} 枚 -> {outdir}")


if __name__ == "__main__":
    main()
