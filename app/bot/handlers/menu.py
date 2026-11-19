"""Persian-first Telegram commands and navigation."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job
from sqlalchemy import select

from app.bot.keyboards.main import language_keyboard, main_menu
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.domain.models import ProcessingJob, User

router = Router(name="menu")

_CATEGORY_REPLIES = {
    "📄 ابزارهای PDF": "یک فایل PDF بفرستید تا عملیات مناسب نمایش داده شود.",
    "📄 PDF Tools": "Send a PDF to see relevant available operations.",
    "🔄 تبدیل فایل": "فایل DOCX/XLSX/PPTX را برای تبدیل به PDF ارسال کنید (LibreOffice لازم است).",
    "🔄 Convert Files": "Send a DOCX/XLSX/PPTX file to convert it to PDF (LibreOffice required).",
    "✏️ ویرایش PDF": "واترمارک تصویری و چرخش صفحه در دسترس است؛ ویرایش متن اصلی پشتیبانی نمی‌شود.",
    "✏️ Edit PDF": (
        "Visual watermarks and page rotation are available; editing original text is not supported."
    ),
    "🗂 سازمان‌دهی PDF": "استخراج صفحه‌ها فعال است؛ ادغام چندفایلی در منوی تلگرام هنوز فعال نیست.",
    "🗂 Organize PDF": (
        "Page extraction is enabled; multi-file merge is not yet exposed in Telegram."
    ),
    "📉 فشرده‌سازی": (
        "یک PDF بفرستید و Compress را انتخاب کنید. بهینه‌سازی فعلی بدون افت کیفیت تصویر است."
    ),
    "📉 Compress PDF": (
        "Send a PDF and choose Compress. Current optimization preserves image resolution."
    ),
    "🔍 OCR و استخراج متن": "استخراج متن فوری است؛ OCR به OCRmyPDF و بسته‌زبان‌های نصب‌شده نیاز دارد.",
    "🔍 OCR & Extract": (
        "Text extraction is available; OCR requires OCRmyPDF and installed language packs."
    ),
    "🔐 امنیت": "PDF رمزدار رد می‌شود. محتوای فعال یا اسکریپت‌های تعبیه‌شده اجرا نمی‌شوند.",
    "🔐 Security": (
        "Encrypted PDFs are rejected. Embedded scripts or active content are never executed."
    ),
    "📝 ساخت PDF": "عکس JPEG/PNG/TIFF بفرستید تا به یک PDF تک‌صفحه‌ای تبدیل شود.",
    "📝 Create PDF": "Send a JPEG/PNG/TIFF image to convert it to a single-page PDF.",
    "🤖 دستیار هوشمند": "ماژول AI اختیاری است اما هنوز در گردش‌کار تلگرام فعال نشده است.",
    "🤖 AI Assistant": "The optional AI module is not yet exposed in the Telegram workflow.",
    "⚙️ تنظیمات": "برای تنظیم زبان از /settings استفاده کنید.",
    "⚙️ Settings": "Use /settings to change the interface language.",
    "📚 راهنما": "برای شروع PDF یا فایل پشتیبانی‌شده بفرستید. فرمان‌ها: /help و /history.",
    "📚 Help": "Send a PDF or supported file to begin. Commands: /help and /history.",
}


def _user_id(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


async def language_for(user_id: int) -> str:
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        return user.language if user else "fa"


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(message: Message) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return
    lang = await language_for(user_id)
    text = (
        "سلام! فایل PDF یا سند پشتیبانی‌شده بفرستید تا ابزارهای مناسب را پیشنهاد کنم.\n"
        "Hello! Send a PDF or supported document to see available actions."
    )
    await message.answer(text, reply_markup=main_menu(lang))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "برای شروع فایل ارسال کنید، سپس عملیات را از دکمه‌ها انتخاب کنید.\n"
        "Send a supported file, then choose an action from the buttons. "
        "Use /settings for language, /history for recent jobs, /cancel to abort an active job."
    )


@router.message(Command("settings"))
@router.message(Command("language"))
async def settings_command(message: Message) -> None:
    await message.answer("زبان / Language", reply_markup=language_keyboard())


@router.callback_query(lambda query: bool(query.data and query.data.startswith("lang:")))
async def set_language(query: CallbackQuery) -> None:
    data = query.data or ""
    language = data.split(":", 1)[1]
    if language not in {"fa", "en"}:
        await query.answer("Invalid language", show_alert=True)
        return
    async with SessionFactory() as session:
        user = await session.get(User, query.from_user.id)
        if user is None:
            session.add(User(id=query.from_user.id, language=language))
        else:
            user.language = language
        await session.commit()
    await query.answer("ذخیره شد" if language == "fa" else "Saved")
    if query.message:
        await query.message.answer(
            "زبان ذخیره شد. Language saved.", reply_markup=main_menu(language)
        )


@router.message(Command("history"))
async def history(message: Message) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return
    async with SessionFactory() as session:
        result = await session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.user_id == user_id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(10)
        )
        jobs = list(result.scalars())
    if not jobs:
        await message.answer("هنوز کاری ثبت نشده است. No jobs yet.")
        return
    lines = [f"{job.operation}: {job.status}" for job in jobs]
    await message.answer("📚 آخرین عملیات / Recent jobs\n" + "\n".join(lines))


@router.message(Command("privacy"))
async def privacy(message: Message) -> None:
    await message.answer(
        "فایل‌ها خصوصی ذخیره و پس از مدت تعیین‌شده حذف می‌شوند؛ فایل اصلی بازنویسی نمی‌شود. "
        "از بارگذاری اسناد محرمانه خودداری کنید.\n"
        "Files are stored privately and expire automatically; originals are never overwritten. "
        "Avoid uploading highly sensitive documents."
    )


@router.message(Command("about"))
async def about(message: Message) -> None:
    await message.answer(
        "Ultimate PDF Telegram Assistant — پردازش غیرهمزمان اسناد. "
        "کیفیت OCR و تبدیل به فایل، فونت و "
        "زبان‌های نصب‌شده بستگی دارد.\n"
        "Conversion/OCR quality depends on document quality, fonts, and installed language packs."
    )


@router.message(Command("cancel"))
async def cancel(message: Message) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return
    async with SessionFactory() as session:
        result = await session.execute(
            select(ProcessingJob)
            .where(
                ProcessingJob.user_id == user_id,
                ProcessingJob.status.in_(["queued", "running"]),
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            await message.answer("کار فعالی نیست. No active job to cancel.")
            return
        job_id = job.id
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        cancelled = await Job(job_id, pool).abort(timeout=2)
        requested = cancelled
    except TimeoutError:
        # Arq has received the abort request; worker shutdown may still be finishing.
        cancelled, requested = False, True
    except Exception:
        cancelled, requested = False, False
    finally:
        await pool.aclose()
    if requested:
        async with SessionFactory() as session:
            job = await session.get(ProcessingJob, job_id)
            if job and job.status in {"queued", "running"}:
                job.status = "cancelled" if cancelled else "cancelling"
                await session.commit()
        await message.answer("درخواست لغو ارسال شد. Cancellation requested.")
    else:
        await message.answer(
            "لغو ممکن نشد؛ ممکن است کار تمام شده باشد. "
            "Cancellation was not accepted; the job may have finished."
        )


@router.message(lambda message: message.text is not None)
async def menu_action(message: Message) -> None:
    text = message.text or ""
    response = _CATEGORY_REPLIES.get(text)
    if response:
        await message.answer(response)
    else:
        await message.answer(
            "برای شروع فایل PDF یا سند پشتیبانی‌شده بفرستید. Use /help for instructions."
        )
