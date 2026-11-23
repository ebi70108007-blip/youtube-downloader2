import os
import re
import tempfile
import threading
import time
from urllib.parse import urlparse

import certifi
import flet as ft
import yt_dlp

SAFE_FMT_RE = re.compile(r"^[a-zA-Z0-9_+.\-/]+$")
HTTP_CHUNK_BYTES = 10 * 1024 * 1024
BUFFER_BYTES = 128 * 1024
UI_UPDATE_INTERVAL = 0.35
DEFAULT_HOME = "https://m.youtube.com"


def configure_ssl():
    try:
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:
        pass


def is_safe_http_url(url):
    try:
        parsed = urlparse((url or "").strip())
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )
    except Exception:
        return False


def normalize_url(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return DEFAULT_HOME
    lower = text.lower()
    blocked = (
        "javascript:",
        "file:",
        "data:",
        "content:",
        "intent:",
    )
    if lower.startswith(blocked):
        return DEFAULT_HOME
    if lower.startswith(("http://", "https://")):
        return text if is_safe_http_url(text) else DEFAULT_HOME
    if "." in text and " " not in text:
        candidate = f"https://{text}"
        if is_safe_http_url(candidate):
            return candidate
    query = text.replace(" ", "+")
    return f"https://www.google.com/search?q={query}"


def resolve_writable_dir():
    candidates = []
    android_pub = "/storage/emulated/0/Download"
    if os.path.exists(android_pub):
        candidates.append(android_pub)
    home_dir = os.path.expanduser("~")
    win_dir = os.path.join(home_dir, "Downloads")
    if os.path.exists(win_dir):
        candidates.append(win_dir)
    candidates.append(home_dir)
    candidates.append(tempfile.gettempdir())

    for folder in candidates:
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".dl_write_test.tmp")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
            return folder
        except Exception:
            continue
    return tempfile.gettempdir()


def format_speed(speed_bps):
    if not speed_bps or speed_bps <= 0:
        return ""
    if speed_bps >= 1024 * 1024:
        return f" | {speed_bps / (1024 * 1024):.1f} MB/s"
    return f" | {speed_bps / 1024:.0f} KB/s"


def create_button(label, on_click_fn):
    btn_cls = getattr(
        ft,
        "ElevatedButton",
        getattr(ft, "FilledButton", getattr(ft, "Button", None)),
    )
    return btn_cls(
        content=ft.Text(label, size=12),
        on_click=on_click_fn,
    )


def create_option(key_val, text_val):
    if hasattr(ft, "DropdownOption"):
        return ft.DropdownOption(key=key_val, text=text_val)
    return ft.dropdown.Option(key=key_val, text=text_val)


def build_format_selector(selected_fmt):
    if selected_fmt == "best":
        return "best[ext=mp4]/best"
    if selected_fmt == "audio":
        return "bestaudio[ext=m4a]/bestaudio/best"
    if selected_fmt and SAFE_FMT_RE.match(selected_fmt):
        return f"{selected_fmt}/best[ext=mp4]/best"
    return "best[ext=mp4]/best"


def get_ydl_base_opts():
    return {
        "noplaylist": True,
        "nocheckcertificate": False,
        "geo_bypass": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 8,
        "http_chunk_size": HTTP_CHUNK_BYTES,
        "buffersize": BUFFER_BYTES,
        "socket_timeout": 20,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 3,
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "android_vr",
                    "ios",
                    "tv_embedded",
                ],
            }
        },
    }


def extract_quality_options(info):
    options = [
        create_option("best", "بهترین کیفیت موجود (خودکار)"),
    ]
    found = {}
    formats = info.get("formats") or []

    for fmt in formats:
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        height = fmt.get("height")
        fmt_id = fmt.get("format_id")
        if not fmt_id or not height:
            continue
        if vcodec == "none" or acodec == "none":
            continue
        if height in found:
            continue
        ext = fmt.get("ext", "mp4")
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        size_txt = ""
        if size:
            mb_val = size / (1024 * 1024)
            size_txt = f" - {mb_val:.1f} MB"
        found[height] = (
            str(fmt_id),
            f"{height}p ({ext}){size_txt}",
        )

    for height in sorted(found.keys(), reverse=True):
        fmt_id, label = found[height]
        options.append(create_option(fmt_id, label))

    options.append(create_option("audio", "فقط صدا (M4A/MP3)"))
    return options


def main(page: ft.Page):
    configure_ssl()
    page.title = "مرورگر و دانلودر سریع"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 8
    page.spacing = 6

    state = {"url": DEFAULT_HOME}
    busy_lock = threading.Lock()
    progress_state = {"last_ui": 0.0}

    url_input = ft.TextField(
        value=state["url"],
        hint_text="آدرس سایت یا جستجو...",
        expand=True,
        dense=True,
        text_size=13,
    )

    status_text = ft.Text(
        value="وارد صفحه ویدیو شوید و «بررسی کیفیت» را بزنید.",
        size=12,
        text_align=ft.TextAlign.CENTER,
        rtl=True,
    )

    progress_bar = ft.ProgressBar(
        value=0,
        visible=False,
    )

    quality_dropdown = ft.Dropdown(
        label="کیفیت",
        value="best",
        expand=True,
        dense=True,
        options=[
            create_option("best", "بهترین کیفیت موجود (خودکار)"),
            create_option("audio", "فقط صدا (M4A/MP3)"),
        ],
    )

    def on_nav_change(e):
        new_url = getattr(e, "data", None)
        if isinstance(new_url, str) and is_safe_http_url(new_url):
            state["url"] = new_url
            url_input.value = new_url
            page.update()

    if hasattr(ft, "WebView"):
        browser_view = ft.WebView(
            url=state["url"],
            expand=True,
            on_page_started=on_nav_change,
            on_page_ended=on_nav_change,
        )
    else:
        browser_view = ft.Column(
            controls=[
                ft.Text(
                    "مرورگر داخلی در نسخه اندروید فعال است. "
                    "در ویندوز لینک را در نوار بالا بزنید.",
                    text_align=ft.TextAlign.CENTER,
                    rtl=True,
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def navigate_to(target_url):
        clean = normalize_url(target_url)
        state["url"] = clean
        url_input.value = clean
        if hasattr(browser_view, "url"):
            browser_view.url = clean
        page.update()

    def on_go_click(e):
        navigate_to(url_input.value or "")

    def on_back_click(e):
        if hasattr(browser_view, "go_back"):
            try:
                browser_view.go_back()
            except Exception:
                pass

    def on_reload_click(e):
        if hasattr(browser_view, "reload"):
            try:
                browser_view.reload()
            except Exception:
                pass

    url_input.on_submit = on_go_click

    nav_row = ft.Row(
        controls=[
            create_button("◀", on_back_click),
            create_button("↻", on_reload_click),
            url_input,
            create_button("برو", on_go_click),
        ],
        spacing=4,
    )

    quick_row = ft.Row(
        controls=[
            create_button(
                "YouTube",
                lambda e: navigate_to("https://m.youtube.com"),
            ),
            create_button(
                "Aparat",
                lambda e: navigate_to("https://www.aparat.com"),
            ),
            create_button(
                "Google",
                lambda e: navigate_to("https://www.google.com"),
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=6,
    )

    def set_controls_busy(is_busy):
        check_btn.disabled = is_busy
        dl_btn.disabled = is_busy
        progress_bar.visible = is_busy
        if is_busy:
            progress_bar.value = None

    def progress_hook(d):
        status = d.get("status")
        if status == "downloading":
            now = time.monotonic()
            if now - progress_state["last_ui"] < UI_UPDATE_INTERVAL:
                return
            progress_state["last_ui"] = now
            total = d.get("total_bytes") or d.get(
                "total_bytes_estimate"
            )
            done = d.get("downloaded_bytes", 0)
            spd = format_speed(d.get("speed"))
            if total and total > 0:
                ratio = min(done / total, 1.0)
                progress_bar.value = ratio
                pct = int(ratio * 100)
                mb_done = done / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                status_text.value = (
                    f"دانلود: {pct}% "
                    f"({mb_done:.1f}/{mb_tot:.1f} MB){spd}"
                )
            else:
                mb_done = done / (1024 * 1024)
                status_text.value = (
                    f"دانلود شده: {mb_done:.1f} MB{spd}"
                )
            page.update()
        elif status == "finished":
            progress_bar.value = 1.0
            status_text.value = "در حال نهایی‌سازی فایل..."
            page.update()

    def analyze_worker(video_url):
        opts = get_ydl_base_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            new_opts = extract_quality_options(info)
            quality_dropdown.options = new_opts
            quality_dropdown.value = "best"
            title = (info.get("title") or "ویدیو")[:35]
            status_text.value = (
                f"یافت شد: {title} | کیفیت را انتخاب و دانلود کنید."
            )
        except Exception as err:
            short_err = str(err)[:90]
            status_text.value = f"خطا در بررسی لینک: {short_err}"
        finally:
            set_controls_busy(False)
            busy_lock.release()
            page.update()

    def on_check_click(e):
        target = (url_input.value or state["url"]).strip()
        if not is_safe_http_url(target):
            status_text.value = "لینک معتبر http یا https وارد کنید."
            page.update()
            return
        if not busy_lock.acquire(blocking=False):
            return

        set_controls_busy(True)
        status_text.value = "در حال استخراج کیفیت‌های ویدیو..."
        page.update()

        worker = threading.Thread(
            target=analyze_worker,
            args=(target,),
            daemon=True,
        )
        worker.start()

    def download_worker(video_url, selected_fmt):
        try:
            save_dir = resolve_writable_dir()
            opts = get_ydl_base_opts()
            opts["format"] = build_format_selector(selected_fmt)
            opts["outtmpl"] = os.path.join(
                save_dir,
                "%(title).50s.%(ext)s",
            )
            opts["progress_hooks"] = [progress_hook]
            progress_state["last_ui"] = 0.0

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([video_url])
            status_text.value = f"دانلود انجام شد! مسیر:\n{save_dir}"
        except Exception as err:
            short_err = str(err)[:90]
            status_text.value = f"خطا در دانلود: {short_err}"
        finally:
            set_controls_busy(False)
            busy_lock.release()
            page.update()

    def on_download_click(e):
        target = (url_input.value or state["url"]).strip()
        if not is_safe_http_url(target):
            status_text.value = "لینک معتبر http یا https وارد کنید."
            page.update()
            return
        if not busy_lock.acquire(blocking=False):
            return

        fmt_choice = quality_dropdown.value or "best"
        set_controls_busy(True)
        status_text.value = "در حال اتصال با حداکثر سرعت..."
        page.update()

        worker = threading.Thread(
            target=download_worker,
            args=(target, fmt_choice),
            daemon=True,
        )
        worker.start()

    check_btn = create_button("بررسی کیفیت", on_check_click)
    dl_btn = create_button("دانلود", on_download_click)

    dl_row = ft.Row(
        controls=[
            check_btn,
            quality_dropdown,
            dl_btn,
        ],
        spacing=6,
    )

    page.add(
        nav_row,
        quick_row,
        browser_view,
        dl_row,
        progress_bar,
        status_text,
    )


if __name__ == "__main__":
    if hasattr(ft, "app"):
        ft.app(target=main)
    else:
        ft.run(main)
