"""
GDank Bot — Telegram Bot untuk prediksi stok gudang
"""
import os
import logging
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler,
    ContextTypes, filters, ConversationHandler,
)

import worker_client  as wc
import fastapi_client as fc

load_dotenv()

logging.basicConfig(
    format  = "%(asctime)s | %(levelname)s | %(message)s",
    level   = logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("BOT_TOKEN")
STARS_PRICE = int(os.getenv("STARS_PRICE", "100"))

# ── State ConversationHandler ──
(
    WAIT_FILE,
    WAIT_PRODUCT_CHOICE,
    WAIT_POLA_CHOICE,
) = range(3)

# ── Simpan session per user (in-memory) ──
# { telegram_id: {"session_id": ..., "products": [...], ...} }
USER_SESSIONS: dict = {}


# ════════════════════════════════════════
# HELPER
# ════════════════════════════════════════

async def is_active(telegram_id: int) -> bool:
    """Cek apakah user sudah bayar."""
    result = await wc.check_user(telegram_id)
    return result.get("is_active", False)


def session(uid: int) -> dict:
    if uid not in USER_SESSIONS:
        USER_SESSIONS[uid] = {}
    return USER_SESSIONS[uid]


def format_report(report: dict) -> str:
    """Format laporan prediksi menjadi teks Telegram."""
    lines = [
        f"📦 *{report['product_id']} — {report['product_name']}*",
        f"Kategori: {report['kategori']} · {report['tipe']}",
        f"",
        f"{'No':<3} {'Bulan':<10} {'Aktual':>7} {'Prediksi':>9} {'Status'}",
        "─" * 42,
    ]
    for row in report["rows"]:
        emo = "✅" if row["status"] == "Akurat" else ("⚠️" if row["status"] == "Cukup" else "❌")
        lines.append(
            f"{row['no']:<3} {row['bulan']:<10} {row['aktual']:>7} {row['prediksi']:>9} {emo}"
        )
    lines += [
        "─" * 42,
        f"MAE  : *{report['mae']} pcs*",
        f"MAPE : *{report['mape']}%*",
        f"Tren : {report['kecenderungan']}",
    ]
    return "\n".join(lines)


def format_forecast(f: dict) -> str:
    """Format hasil forecast masa depan."""
    fc_data = f["forecast"]
    lines = [
        f"🔮 *Prediksi Stok Masa Depan*",
        f"",
        f"Produk      : *{f['product_id']}* — {f['product_name']}",
        f"Data terakhir: {fc_data['last_data']}",
    ]
    if fc_data.get("skip_month"):
        lines.append(f"Dilewati    : {fc_data['skip_month']} _(laporan belum masuk)_")
    lines += [
        f"",
        f"📅 Target    : *{fc_data['target_month']}*",
        f"📦 Prediksi  : *{fc_data['prediksi_pcs']} pcs*",
        f"",
        f"_{fc_data['keterangan']}_",
    ]
    return "\n".join(lines)


# ════════════════════════════════════════
# COMMAND HANDLERS
# ════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    tg_id    = user.id
    username = user.username or ""
    fullname = user.full_name or ""

    # Daftarkan user jika belum ada
    await wc.register_user(tg_id, username, fullname)

    # Cek status
    active = await is_active(tg_id)

    if active:
        await update.message.reply_text(
            f"👋 Halo *{fullname}*! Selamat datang di GDank.\n\n"
            f"Gunakan perintah:\n"
            f"• /upload — upload dataset untuk training\n"
            f"• /forecast — lihat prediksi stok\n"
            f"• /help — bantuan",
            parse_mode="Markdown",
        )
    else:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⭐ Beli via Telegram Stars", callback_data="buy_stars"),
            InlineKeyboardButton("💳 Bayar Manual",           callback_data="buy_manual"),
        ]])
        await update.message.reply_text(
            f"👋 Halo *{fullname}*!\n\n"
            f"GDank adalah bot prediksi stok gudang berbasis AI.\n\n"
            f"🔒 Akun kamu belum aktif. Beli lisensi untuk mulai:",
            parse_mode="Markdown",
            reply_markup=kb,
        )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Panduan GDank Bot*\n\n"
        "1️⃣ /upload — kirim file dataset (CSV/Excel/Parquet/JSON)\n"
        "2️⃣ Bot akan otomatis training model\n"
        "3️⃣ /forecast — pilih produk & lihat prediksi\n\n"
        "Format dataset yang didukung:\n"
        "CSV · Excel · Parquet · JSON\n\n"
        "Kolom wajib: Date, Product\\_ID, Quantity",
        parse_mode="Markdown",
    )


# ════════════════════════════════════════
# PEMBAYARAN — TELEGRAM STARS
# ════════════════════════════════════════

async def cb_buy_stars(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await ctx.bot.send_invoice(
        chat_id      = query.message.chat_id,
        title        = "GDank — Lisensi Seumur Hidup",
        description  = "Akses penuh ke bot prediksi stok GDank. Bayar sekali, pakai selamanya.",
        payload      = f"gdank_license_{query.from_user.id}",
        currency     = "XTR",           # XTR = Telegram Stars
        prices       = [LabeledPrice("Lisensi GDank", STARS_PRICE)],
        provider_token= "",             # kosong untuk Stars
    )


async def cb_buy_manual(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    await query.message.reply_text(
        f"💳 *Pembayaran Manual*\n\n"
        f"Kirim bukti pembayaran ke admin dengan menyertakan:\n"
        f"• Telegram ID kamu: `{tg_id}`\n"
        f"• Screenshot bukti transfer\n\n"
        f"Admin akan mengaktifkan akunmu dalam 1x24 jam.",
        parse_mode="Markdown",
    )


async def pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Telegram Stars — konfirmasi pembayaran."""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def payment_success(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Telegram Stars — setelah pembayaran berhasil."""
    tg_id = update.effective_user.id

    # Aktifkan user di D1
    result = await wc.activate_stars(tg_id)

    if result.get("status") == "success":
        await update.message.reply_text(
            "🎉 *Pembayaran berhasil!* Akun kamu sudah aktif.\n\n"
            "Ketik /upload untuk mulai upload dataset.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "⚠️ Pembayaran diterima tapi gagal aktivasi otomatis.\n"
            "Hubungi admin dengan Telegram ID kamu.",
        )


# ════════════════════════════════════════
# UPLOAD & TRAINING
# ════════════════════════════════════════

async def cmd_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await is_active(tg_id):
        await update.message.reply_text(
            "🔒 Akun belum aktif. Ketik /start untuk membeli lisensi."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📂 Kirim file dataset kamu.\n\n"
        "Format: CSV · Excel (.xlsx) · Parquet · JSON\n"
        "Kolom wajib: Date, Product\\_ID, Quantity",
        parse_mode="Markdown",
    )
    return WAIT_FILE


async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    doc   = update.message.document

    if not doc:
        await update.message.reply_text("❌ Harap kirim file, bukan teks.")
        return WAIT_FILE

    # Cek ekstensi
    filename = doc.file_name or "dataset.csv"
    ext      = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ["csv", "xlsx", "xls", "parquet", "json"]:
        await update.message.reply_text(
            f"❌ Format `.{ext}` tidak didukung.\n"
            f"Gunakan: CSV · Excel · Parquet · JSON"
        )
        return WAIT_FILE

    # Download file
    msg = await update.message.reply_text("⬇️ Mengunduh file...")
    tg_file    = await ctx.bot.get_file(doc.file_id)
    file_bytes = await tg_file.download_as_bytearray()

    # Upload ke FastAPI
    await msg.edit_text("🔄 Mengupload dataset ke server...")
    try:
        result = await fc.upload_dataset(bytes(file_bytes), filename)
    except Exception as e:
        await msg.edit_text(f"❌ Gagal upload: {e}")
        return ConversationHandler.END

    if result.get("status") != "success":
        await msg.edit_text(
            f"❌ Dataset tidak valid:\n{result.get('message', 'Unknown error')}\n\n"
            f"💡 {result.get('suggestion', '')}"
        )
        return ConversationHandler.END

    session_id = result["session_id"]
    info       = result["validation"]["info"]
    session(tg_id)["session_id"] = session_id

    await msg.edit_text(
        f"✅ *Dataset berhasil diupload!*\n\n"
        f"📊 {info['total_rows']:,} baris · "
        f"{info['total_products']:,} produk · "
        f"{info['total_months']} bulan\n"
        f"📅 {info['date_range']}\n\n"
        f"⚙️ Memulai training model...\n"
        f"_(proses ini membutuhkan beberapa menit)_",
        parse_mode="Markdown",
    )

    # Training
    try:
        train_result = await fc.train(session_id)
    except Exception as e:
        await msg.edit_text(f"❌ Training gagal: {e}")
        return ConversationHandler.END

    if train_result.get("status") != "success":
        await msg.edit_text(f"❌ Training gagal: {train_result.get('message')}")
        return ConversationHandler.END

    metrics      = train_result["metrics"]
    top_products = train_result.get("top_products", [])
    session(tg_id)["top_products"] = top_products

    await msg.edit_text(
        f"🎉 *Training selesai!*\n\n"
        f"📈 Hasil evaluasi:\n"
        f"• MAE  : `{metrics['mae']} pcs`\n"
        f"• RMSE : `{metrics['rmse']} pcs`\n"
        f"• MAPE : `{metrics['mape']}%`\n\n"
        f"Ketik /forecast untuk melihat prediksi stok.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ════════════════════════════════════════
# FORECAST
# ════════════════════════════════════════

async def cmd_forecast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id

    if not await is_active(tg_id):
        await update.message.reply_text("🔒 Akun belum aktif. Ketik /start.")
        return ConversationHandler.END

    sess = session(tg_id)
    if not sess.get("session_id"):
        await update.message.reply_text(
            "⚠️ Belum ada dataset. Ketik /upload terlebih dahulu."
        )
        return ConversationHandler.END

    # Ambil daftar produk
    try:
        prod_result = await fc.get_products(sess["session_id"])
        products    = prod_result.get("products", [])[:10]  # max 10
    except Exception:
        products = []

    sess["products"] = products

    if not products:
        await update.message.reply_text("⚠️ Tidak ada produk ditemukan di dataset.")
        return ConversationHandler.END

    # Buat keyboard produk
    kb_rows = []
    for p in products:
        label = f"{p['Product_ID']} — {p['Product_Name']} ({p['total_quantity']} pcs)"
        kb_rows.append([InlineKeyboardButton(label, callback_data=f"prod_{p['Product_ID']}")])
    kb_rows.append([InlineKeyboardButton("📊 Top 5 Semua", callback_data="prod_all")])

    await update.message.reply_text(
        "🔮 *Pilih produk yang ingin diprediksi:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb_rows),
    )
    return WAIT_PRODUCT_CHOICE


async def cb_product_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    tg_id  = query.from_user.id
    data   = query.data  # "prod_XXXX" atau "prod_all"
    await query.answer()

    product_id = None if data == "prod_all" else data.replace("prod_", "")
    session(tg_id)["product_id"] = product_id

    # Pilih pola
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⏭ N+2 (laporan belum masuk)", callback_data="pola_skip"),
        InlineKeyboardButton("✅ N+1 (data sudah ada)",      callback_data="pola_direct"),
    ]])
    await query.message.reply_text(
        "📅 *Pilih pola prediksi:*\n\n"
        "• *N+2* — laporan bulan ini belum masuk, prediksi 2 bulan ke depan\n"
        "• *N+1* — data sudah tersedia, prediksi bulan depan langsung",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return WAIT_POLA_CHOICE


async def cb_pola_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    tg_id  = query.from_user.id
    data   = query.data
    await query.answer()

    skip_n1    = (data == "pola_skip")
    sess       = session(tg_id)
    session_id = sess.get("session_id")
    product_id = sess.get("product_id")

    msg = await query.message.reply_text("🔄 Mengambil hasil prediksi...")

    try:
        result = await fc.forecast(session_id, product_id, skip_n1)
    except Exception as e:
        await msg.edit_text(f"❌ Gagal mengambil prediksi: {e}")
        return ConversationHandler.END

    if result.get("status") != "success":
        await msg.edit_text(f"❌ {result.get('message', 'Gagal')}")
        return ConversationHandler.END

    results = result.get("results", [])
    await msg.delete()

    for r in results:
        if r.get("error"):
            await query.message.reply_text(f"⚠️ {r['error']}")
            continue

        # Laporan backtesting
        report_text = format_report(r["report"])
        await query.message.reply_text(
            f"`{report_text}`",
            parse_mode="Markdown",
        )

        # Forecast masa depan
        try:
            fc_result = await fc.forecast(session_id, r["product_id"], skip_n1)
            if fc_result.get("status") == "success" and fc_result["results"]:
                forecast_text = format_forecast(fc_result["results"][0])
                await query.message.reply_text(forecast_text, parse_mode="Markdown")
        except Exception:
            pass

    return ConversationHandler.END


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Upload conversation
    upload_conv = ConversationHandler(
        entry_points = [CommandHandler("upload", cmd_upload)],
        states       = {
            WAIT_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
        },
        fallbacks    = [],
    )

    # Forecast conversation
    forecast_conv = ConversationHandler(
        entry_points = [CommandHandler("forecast", cmd_forecast)],
        states       = {
            WAIT_PRODUCT_CHOICE: [CallbackQueryHandler(cb_product_choice, pattern="^prod_")],
            WAIT_POLA_CHOICE    : [CallbackQueryHandler(cb_pola_choice,    pattern="^pola_")],
        },
        fallbacks    = [],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(upload_conv)
    app.add_handler(forecast_conv)

    # Pembayaran Stars
    app.add_handler(CallbackQueryHandler(cb_buy_stars,  pattern="^buy_stars$"))
    app.add_handler(CallbackQueryHandler(cb_buy_manual, pattern="^buy_manual$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

    logger.info("🤖 GDank Bot berjalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
