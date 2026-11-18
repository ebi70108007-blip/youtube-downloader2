import os
import tempfile
import threading

import flet as ft
from pytubefix import YouTube


def get_download_folder():
    android_dir = "/storage/emulated/0/Download"
    if os.path.exists(android_dir) and os.access(android_dir, os.W_OK):
        return android_dir
    home_dir = os.path.expanduser("~")
    win_dir = os.path.join(home_dir, "Downloads")
    if os.path.exists(win_dir):
        return win_dir
    return tempfile.gettempdir()


def clean_youtube_url(raw_url):
    url = raw_url.strip()
    if "/shorts/" in url:
        video_id = url.split("/shorts/")[1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


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


def pick_stream(yt_obj, quality_val):
    if quality_val == "audio":
        return yt_obj.streams.get_audio_only()
    if quality_val == "720p":
        return (
            yt_obj.streams.filter(res="720p", progressive=True).first()
            or yt_obj.streams.get_highest_resolution()
        )
    return (
        yt_obj.streams.filter(res="360p", progressive=True).first()
        or yt_obj.streams.get_lowest_resolution()
    )


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

    paste_btn = create_button("Paste", paste_link)

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
            create_option("audio", "فقط صوت (MP3/M4A)"),
        ],
    )

    progress_bar = ft.ProgressBar(
        width=320,
        value=0,
        visible=False,
    )

    def download_worker(video_url, quality_val):
        save_dir = get_download_folder()
        clients = [
            "WEB",
            "MWEB",
            "IOS",
            "ANDROID_VR",
            "WEB_EMBED",
            "TV_EMBED",
        ]
        last_error = None
        success = False

        for client_name in clients:
            try:
                status_text.value = (
                    f"تلاش برای اتصال با کلاینت {client_name}..."
                )
                page.update()

                yt = YouTube(video_url, client=client_name)
                stream = pick_stream(yt, quality_val)
                if not stream:
                    stream = yt.streams.get_highest_resolution()

                status_text.value = (
                    f"در حال دانلود ({client_name}): "
                    f"{yt.title[:25]}..."
                )
                page.update()

                stream.download(output_path=save_dir)
                success = True
                break
            except Exception as err:
                last_error = err
                continue

        progress_bar.visible = False
        if success:
            status_text.value = (
                f"دانلود با موفقیت انجام شد!\n"
                f"محل ذخیره: {save_dir}"
            )
        else:
            status_text.value = f"خطا در دانلود: {last_error}"

        download_btn.disabled = False
        page.update()

    def start_download(e):
        raw_url = url_input.value
        if not raw_url or not raw_url.strip():
            status_text.value = "لطفاً ابتدا لینک ویدیو را وارد کنید."
            page.update()
            return

        clean_url = clean_youtube_url(raw_url)
        download_btn.disabled = True
        progress_bar.visible = True
        progress_bar.value = None
        status_text.value = "در حال اتصال به یوتیوب..."
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
        download_btn,
        progress_bar,
        status_text,
    )


if __name__ == "__main__":
    if hasattr(ft, "app"):
        ft.app(target=main)
    else:
        ft.run(main)
