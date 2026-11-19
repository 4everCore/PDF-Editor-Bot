"""Persian-first menu and context-specific inline actions."""

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

LABELS = {
    "fa": [
        "📄 ابزارهای PDF",
        "🔄 تبدیل فایل",
        "✏️ ویرایش PDF",
        "🗂 سازمان‌دهی PDF",
        "📉 فشرده‌سازی",
        "🔍 OCR و استخراج متن",
        "🔐 امنیت",
        "📝 ساخت PDF",
        "🤖 دستیار هوشمند",
        "⚙️ تنظیمات",
        "📚 راهنما",
    ],
    "en": [
        "📄 PDF Tools",
        "🔄 Convert Files",
        "✏️ Edit PDF",
        "🗂 Organize PDF",
        "📉 Compress PDF",
        "🔍 OCR & Extract",
        "🔐 Security",
        "📝 Create PDF",
        "🤖 AI Assistant",
        "⚙️ Settings",
        "📚 Help",
    ],
}


def main_menu(language: str = "fa") -> ReplyKeyboardMarkup:
    labels = LABELS.get(language, LABELS["fa"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=labels[i]), KeyboardButton(text=labels[i + 1])]
            for i in range(0, 10, 2)
        ]
        + [[KeyboardButton(text=labels[10])]],
        resize_keyboard=True,
        is_persistent=True,
    )


def file_actions(
    file_id: str, language: str, is_pdf: bool = True, is_office: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    actions = (
        [
            ("compress", "📉 فشرده‌سازی" if language == "fa" else "📉 Compress"),
            ("extract_text", "📝 استخراج متن" if language == "fa" else "📝 Extract text"),
            ("render_png", "🖼 پیش‌نمایش صفحه اول" if language == "fa" else "🖼 Preview page 1"),
            ("ocr", "🔎 OCR قابل جستجو" if language == "fa" else "🔎 Searchable OCR"),
            ("watermark", "©️ واترمارک SAMPLE" if language == "fa" else "©️ Watermark SAMPLE"),
            ("rotate", "↻ چرخش ۹۰ درجه" if language == "fa" else "↻ Rotate 90°"),
        ]
        if is_pdf
        else [("office_to_pdf", "📄 تبدیل به PDF" if language == "fa" else "📄 Convert to PDF")]
        if is_office
        else [("image_to_pdf", "📄 تبدیل به PDF" if language == "fa" else "📄 Convert to PDF")]
    )
    for operation, title in actions:
        builder.button(text=title, callback_data=f"op:{file_id}:{operation}")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="فارسی", callback_data="lang:fa")
    builder.button(text="English", callback_data="lang:en")
    return builder.as_markup()
