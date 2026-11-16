import os
import tempfile
import threading

import flet as ft
import yt_dlp


def get_download_folder():
    android_dir = "/storage/emulated/0/Download"
    if os.path.exists(android_dir) and os.access(android_dir, os.W_OK):
        return android_dir
    home_dir = os.path.expanduser("~")
    win_dir = os.path.join(home_dir, "Downloads")
    if os.path.exists(win_dir):
        return win_dir
    return tempfile.gettempdir()


def get_cookie_path():
    return os.path.join(tempfile.gettempdir(), "yt_cookies.txt")


def get_format_string(quality_choice):
    if quality_choice == "360p":
        return "18/best[height<=360][ext=mp4]/best[height<=360]/best"
    if quality_choice == "720p":
        return "22/best[height<=720][ext=mp4]/best[ext=mp4]/best"
    if quality_choice == "audio":
        return "140/bestaudio[ext=m4a]/bestaudio/best"
    return "best[ext=mp4]/best"


def create_button(label, on_click_fn):
    btn_cls = getattr(
        ft,
        "ElevatedButton",
        getattr(ft, "FilledButton", getattr(ft, "Button", None)),
    )
    return btn_cls(
        content=ft.Text(label),
        on_click=on_click_fn,
    )


def create_option(key_val, text_val):
    if hasattr(ft, "DropdownOption"):
        return ft.DropdownOption(key=key_val, text=text_val)
    return ft.dropdown.Option(key=key_val, text=text_val)


def main(page: ft.Page):
    page.title = "دانلودر سریع یوتیوب"
    page.theme_mode = ft.ThemeMode.DARK
    page.rtl = True
    page.padding = 20
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    title_text = ft.Text(
        value="دانلودر سریع یوتیوب",
        size=24,
        weight=ft.FontWeight.BOLD,
    )

    url_input = ft.TextField(
        label="لینک ویدیو یا Shorts یوتیوب",
        expand=True,
    )

    cookie_input = ft.TextField(
        label="متن کوکی Netscape (اختیاری برای رفع ارور ربات)",
        multiline=True,
        min_lines=1,
        max_lines=3,
        width=320,
    )

    status_text = ft.Text(
        value="آماده برای دانلود",
        size=14,
        text_align=ft.TextAlign.CENTER,
    )

    def paste_link(e):
        try:
            clip_text = page.get_clipboard()
            if clip_text and isinstance(clip_text, str):
                url_input.value = clip_text.strip()
                page.update()
        except Exception:
            pass

    def save_cookie_text(e):
        raw_cookie = cookie_input.value
        if not raw_cookie or not raw_cookie.strip():
            status_text.value = "کادر کوکی خالی است."
            page.update()
            return
        try:
            c_path = get_cookie_path()
            header = "# Netscape HTTP Cookie File\n"
            content = raw_cookie.strip()
            if not content.startswith("# Netscape"):
                content = header + content
            with open(c_path, "w", encoding="utf-8") as f_obj:
                f_obj.write(content + "\n")
            status_text.value = "کوکی با موفقیت ذخیره شد!"
        except Exception as err:
            status_text.value = f"خطا در ذخیره کوکی: {err}"
        page.update()

    paste_btn = create_button("Paste", paste_link)
    cookie_btn = create_button("ذخیره کوکی", save_cookie_text)

    url_row = ft.Row(
        controls=[url_input, paste_btn],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    quality_dropdown = ft.Dropdown(
        label="انتخاب کیفیت دانلود",
        value="360p",
        width=320,
        options=[
            create_option("360p", "کیفیت کم حجم (360p)"),
            create_option("720p", "کیفیت متوسط (720p)"),
            create_option("best", "بهترین کیفیت ممکن"),
            create_option("audio", "فقط صدا (M4A)"),
        ],
    )

    progress_bar = ft.ProgressBar(
        width=320,
        value=0,
        visible=False,
    )

    def progress_hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get(
                "total_bytes_estimate"
            )
            downloaded = d.get("downloaded_bytes", 0)
            if total and total > 0:
                ratio = downloaded / total
                progress_bar.value = ratio
                percent = int(ratio * 100)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                msg = (
                    f"در حال دانلود: {percent}% "
                    f"({mb_done:.1f} از {mb_total:.1f} مگابایت)"
                )
                status_text.value = msg
                page.update()
        elif d.get("status") == "finished":
            progress_bar.value = 1.0
            status_text.value = "در حال نهایی‌سازی فایل..."
            page.update()

    def download_worker(video_url, quality_val):
        save_dir = get_download_folder()
        out_template = os.path.join(
            save_dir,
            "%(title).50s.%(ext)s",
        )
        fmt_str = get_format_string(quality_val)

        ydl_opts = {
            "format": fmt_str,
            "outtmpl": out_template,
            "noplaylist": True,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "progress_hooks": [progress_hook],
            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "tv_embedded",
                        "android_vr",
                        "mweb",
                    ],
                }
            },
        }

        c_path = get_cookie_path()
        if os.path.exists(c_path):
            ydl_opts["cookiefile"] = c_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            progress_bar.visible = False
            status_text.value = (
                f"دانلود با موفقیت انجام شد!\n"
                f"محل ذخیره: {save_dir}"
            )
        except Exception as err:
            progress_bar.visible = False
            status_text.value = f"خطا: {err}"
        finally:
            download_btn.disabled = False
            page.update()

    def start_download(e):
        raw_url = url_input.value
        if not raw_url or not raw_url.strip():
            status_text.value = "لطفاً ابتدا لینک ویدیو را وارد کنید."
            page.update()
            return

        clean_url = raw_url.strip().split("?")[0]
        if "watch" in raw_url:
            clean_url = raw_url.strip()

        download_btn.disabled = True
        progress_bar.visible = True
        progress_bar.value = None
        status_text.value = "در حال استخراج حجم و مشخصات ویدیو..."
        page.update()

        worker = threading.Thread(
            target=download_worker,
            args=(clean_url, quality_dropdown.value),
            daemon=True,
        )
        worker.start()

    download_btn = create_button("شروع دانلود", start_download)

    page.add(
        title_text,
        url_row,
        quality_dropdown,
        cookie_input,
        cookie_btn,
        download_btn,
        progress_bar,
        status_text,
    )


if __name__ == "__main__":
    if hasattr(ft, "app"):
        ft.app(target=main)
    else:
        ft.run(main)
