import os
import re
import threading
import flet as ft
import yt_dlp


def clean_ansi(text):
    if not text:
        return ""
    return re.sub(r"\x1b\[[0-9;]*m", "", str(text)).strip()


def get_save_path():
    android_dir = "/storage/emulated/0/Download"
    if os.path.exists(android_dir):
        return android_dir
    os.makedirs("downloads", exist_ok=True)
    return "downloads"


def get_format_str(choice):
    formats = {
        "best": "best[ext=mp4]/best",
        "720": "best[height<=720][ext=mp4]/best[height<=720]",
        "480": "best[height<=480][ext=mp4]/best[height<=480]",
        "360": "best[height<=360][ext=mp4]/best[height<=360]",
        "audio": "bestaudio[ext=m4a]/bestaudio",
    }
    return formats.get(choice, "best[ext=mp4]/best")


def format_size(bytes_val):
    if not bytes_val:
        return "نامشخص"
    mb_val = bytes_val / (1024 * 1024)
    return f"{mb_val:.1f} MB"


def make_button(label, handler):
    btn_cls = getattr(ft, "Button", None) or getattr(ft, "ElevatedButton")
    return btn_cls(label, on_click=handler)


def make_option(key, text):
    opt_cls = getattr(ft, "DropdownOption", None)
    if opt_cls:
        return opt_cls(key=key, text=text)
    return ft.dropdown.Option(key, text)


def main(page: ft.Page):
    page.title = "YouTube Downloader"
    page.rtl = True
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.padding = 20

    url_input = ft.TextField(
        label="لینک ویدیو یا Shorts یوتیوب",
        expand=True,
    )

    def paste_url(e):
        if hasattr(page, "get_clipboard"):
            clip = page.get_clipboard()
            if clip:
                url_input.value = clip
                page.update()

    paste_btn = make_button("Paste", paste_url)
    url_row = ft.Row([url_input, paste_btn])

    quality_dd = ft.Dropdown(
        label="انتخاب کیفیت دانلود",
        value="720",
        options=[
            make_option("best", "بهترین کیفیت (MP4)"),
            make_option("720", "کیفیت خوب (720p)"),
            make_option("480", "کیفیت متوسط (480p)"),
            make_option("360", "کیفیت کم‌حجم (360p)"),
            make_option("audio", "فقط فایل صوتی (M4A)"),
        ],
    )

    title_info = ft.Text("", size=13, weight=ft.FontWeight.BOLD)
    info_text = ft.Text("حجم و زمان پس از شروع نمایش داده می‌شود", size=13)
    status_text = ft.Text("آماده دانلود", size=14)
    progress_bar = ft.ProgressBar(value=0, visible=False)

    def progress_hook(d):
        if d["status"] == "downloading":
            t_bytes = d.get("total_bytes")
            t_est = d.get("total_bytes_estimate")
            total = t_bytes or t_est or 0
            downloaded = d.get("downloaded_bytes", 0)

            if total > 0:
                progress_bar.value = downloaded / total
                size_str = format_size(total)
            else:
                size_str = "در حال محاسبه"

            eta = clean_ansi(d.get("_eta_str", "---"))
            speed = clean_ansi(d.get("_speed_str", "---"))
            pct = clean_ansi(d.get("_percent_str", "0%"))

            info_text.value = f"حجم فایل: {size_str} | زمان باقی‌مانده: {eta}"
            status_text.value = f"پیشرفت: {pct} | سرعت: {speed}"
            page.update()

        elif d["status"] == "finished":
            status_text.value = "در حال نهایی‌سازی و ذخیره فایل..."
            page.update()

    def download_task(url, fmt_choice):
        try:
            save_dir = get_save_path()
            fmt_str = get_format_str(fmt_choice)

            ydl_opts = {
                "format": fmt_str,
                "outtmpl": f"{save_dir}/%(title)s.%(ext)s",
                "progress_hooks": [progress_hook],
                "concurrent_fragment_downloads": 8,
                "buffersize": 1024 * 128,
                "http_chunk_size": 10485760,
                "retries": 15,
                "fragment_retries": 15,
                "nocheckcertificate": True,
                "quiet": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    vid_title = info.get("title", "ویدیو")
                    sz = info.get("filesize") or info.get("filesize_approx")
                    size_txt = format_size(sz)
                    title_info.value = f"عنوان: {vid_title[:40]}"
                    info_text.value = f"حجم اولیه: {size_txt} | شروع دریافت..."
                    page.update()

                ydl.download([url])

            status_text.value = "دانلود با موفقیت در پوشه ذخیره شد!"
        except Exception as exc:
            err_msg = str(exc)[:65]
            status_text.value = f"خطا: {err_msg}"
        finally:
            progress_bar.visible = False
            download_btn.disabled = False
            page.update()

    def on_download_click(e):
        url = (url_input.value or "").strip()
        if not url:
            status_text.value = "لطفاً ابتدا لینک را وارد کنید."
            page.update()
            return

        download_btn.disabled = True
        progress_bar.value = None
        progress_bar.visible = True
        title_info.value = ""
        info_text.value = "در حال استخراج حجم و مشخصات ویدیو..."
        status_text.value = "در حال اتصال به یوتیوب..."
        page.update()

        args = (url, quality_dd.value)
        worker = threading.Thread(
            target=download_task, args=args, daemon=True
        )
        worker.start()

    download_btn = make_button("شروع دانلود", on_download_click)

    app_title = ft.Text(
        "دانلودر سریع یوتیوب", size=22, weight=ft.FontWeight.BOLD
    )

    page.add(
        app_title,
        url_row,
        quality_dd,
        download_btn,
        progress_bar,
        title_info,
        info_text,
        status_text,
    )


if __name__ == "__main__":
    run_fn = getattr(ft, "run", None) or getattr(ft, "app")
    run_fn(main)
