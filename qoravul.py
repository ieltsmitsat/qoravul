from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ChatPermissions
from aiogram.filters import Command
from datetime import datetime, timedelta
import asyncio
import json
import os
import re

# Bot tokenini kiriting
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("BOT_TOKEN environment variable o'rnatilmagan!")

# Bot va dispatcher ob'ektlarini yaratamiz
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Haqoratli so'zlar ro'yxatini JSON fayldan yuklash
try:
    with open("haqoratli_sozlar.json", "r", encoding="utf-8") as file:
        data = json.load(file)
    HATEFUL_WORDS = data["hate_words"]
    print(f"Haqoratli so'zlar yuklandi: {HATEFUL_WORDS}")
except FileNotFoundError:
    HATEFUL_WORDS = []
    print("Haqoratli so'zlar JSON fayli topilmadi.")
except json.JSONDecodeError as e:
    print(f"JSON faylni o'qishda xatolik: {e}")
    HATEFUL_WORDS = []

# Reklama aniqlash uchun regex patternlar
ad_patterns = [
    r"(https?://\S+)",  # URL (http yoki https)
    r"(www\.\S+)",  # URL (www)
    r"(telegram\.(me|org)/\S+)",  # Telegram havolalari
    r"\b(pul topish|tez boyish|kredit|online biznes|promo code|bonus)\b",  # Reklama so'zlari
    r"@\w+",  # @username formatidagi kanal yoki foydalanuvchi nomlari
    r"\b[^\s]+\.(uz|com|net|org|info|ru|hyz)(/[^\s]*)?\b"  # Domenlar va ularning qo'shimchalari
]

# /start buyrug'i
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("Salom, botimizga xush kelibsiz!")

# /rules va /help buyruqlari
@dp.message(Command("rules"))
async def send_rules(message: types.Message):
    await message.reply(
        "Guruh qoidalari:\n1. Haqoratli so'z ishlatmaslik.\n2. Reklama yubormaslik.\n3. Qoida buzganlar ban qilinadi."
    )

@dp.message(Command("help"))
async def send_help(message: types.Message):
    await message.reply(
        "Bot buyruqlari:\n/start - Botni ishga tushirish.\n/rules - Guruh qoidalarini ko'rish.\n/help - Yordam olish."
    )

# Join/Leave xabarlarni boshqarish
@dp.message(F.chat.type.in_({"group", "supergroup"}) & (F.new_chat_members | F.left_chat_member))
async def handle_join_leave_messages(message: types.Message):
    try:
        if message.new_chat_members:  # Yangi foydalanuvchilar qo'shilsa
            await bot.delete_message(message.chat.id, message.message_id)
            print(f"Yangi foydalanuvchi qo'shilishi xabari o'chirildi: {message.new_chat_members}")
        elif message.left_chat_member:  # Foydalanuvchi chiqib ketsa
            await bot.delete_message(message.chat.id, message.message_id)
            print(f"Foydalanuvchi chiqib ketishi xabari o'chirildi: {message.left_chat_member}")
    except Exception as e:
        print(f"Join/Leave xabarini o'chirishda xatolik: {e}")

async def is_admin_user(message: types.Message) -> bool:
    # 1. Guruh nomidan yozilgan xabar (Anonim admin)
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True

    # 2. Telegram tizim botlari orqali (Anonim admin yoki kanal posti)
    # 1087968824 - @GroupAnonymousBot
    # 136817688 - @Channel_Bot
    # 777000 - Telegram Service
    if message.from_user and message.from_user.id in (1087968824, 136817688, 777000):
        return True

    # 3. Agar foydalanuvchi ob'ekti bo'lmasa (kanal posti)
    if not message.from_user:
        return True

    # 4. Foydalanuvchi admin yoki creator ekanligini tekshirish
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ["administrator", "creator"]:
            return True
    except Exception as e:
        print(f"get_chat_member tekshirishda xatolik: {e}")

    # 5. Qo'shimcha tekshiruv: guruh adminlari ro'yxatidan izlash
    try:
        admins = await bot.get_chat_administrators(message.chat.id)
        if any(admin.user.id == message.from_user.id for admin in admins):
            return True
    except Exception as e:
        print(f"get_chat_administrators tekshirishda xatolik: {e}")

    return False

# Reklama va haqoratli xabarlarni boshqarish
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def filter_messages(message: types.Message):
    # Foydalanuvchi admin ekanligini tekshirish
    if await is_admin_user(message):
        sender_info = message.from_user.id if message.from_user else (message.sender_chat.id if message.sender_chat else 'Anonim')
        print(f"Admin tomonidan yuborilgan xabar o'tkazib yuborildi (Sender: {sender_info}): {message.text or message.caption}")
        return

    text_lower = (message.text or message.caption or "").lower()

    # Haqoratli so'zlarni aniqlash
    for hateful_word in HATEFUL_WORDS:
        pattern = r"(?:\b|[^a-zA-Z0-9_])" + re.escape(hateful_word) + r"(?:\b|[^a-zA-Z0-9_])"
        if re.search(pattern, text_lower):
            try:
                await bot.delete_message(message.chat.id, message.message_id)
                if message.from_user:
                    await bot.restrict_chat_member(
                        chat_id=message.chat.id,
                        user_id=message.from_user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=datetime.now() + timedelta(minutes=1),
                    )
                warn = await message.answer("Haqoratli so'zlar uchun vaqtinchalik ban berildi!")
                print(f"Haqoratli so'z topildi va xabar o'chirildi: {hateful_word}")
                await asyncio.sleep(5)
                try:
                    await bot.delete_message(message.chat.id, warn.message_id)
                except Exception:
                    pass
            except Exception as e:
                print(f"Haqoratli so'zlarni qayta ishlashda xatolik: {e}")
            return

    # Reklama aniqlash
    for pattern in ad_patterns:
        if re.search(pattern, text_lower):
            try:
                await bot.delete_message(message.chat.id, message.message_id)
                warn = await message.answer(
                    "Reklama yoki kanal havolalari yuborish taqiqlangan. Qoidalarni buzmaslikni so'raymiz!"
                )
                print(f"Reklama topildi va xabar o'chirildi (Sender: {message.from_user.id if message.from_user else 'noma\'lum'}).")
                await asyncio.sleep(5)
                try:
                    await bot.delete_message(message.chat.id, warn.message_id)
                except Exception:
                    pass
            except Exception as e:
                print(f"Reklama xabarini qayta ishlashda xatolik: {e}")
            return

# Botni ishga tushirish funksiyasi
async def main():
    print("Bot ishga tushmoqda...")
    await dp.start_polling(bot, allowed_updates=["message"])

if __name__ == "__main__":
    asyncio.run(main())
