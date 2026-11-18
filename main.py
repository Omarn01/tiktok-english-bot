import os
import json
import random
import time
import asyncio
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from google import genai
from google.genai import types
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip
from tiktok_uploader.upload import upload_video

# Получаем ключи из переменных окружения GitHub Secrets
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TIKTOK_SESSION_ID = os.environ["TIKTOK_SESSION_ID"]

client = genai.Client(api_key=GEMINI_API_KEY)


def generate_content():
    mode = random.choice(["words", "idiom"])

    if mode == "words":
        level = random.choice(["A2", "B1", "B2", "C1"])
        prompt = f"""
        Generate 10 useful English words for level {level} with Russian translations.
        Return ONLY valid JSON without markdown formatting:
        {{
            "mode": "words",
            "title": "10 слов уровня {level}",
            "items": [
                {{"en": "word", "ru": "перевод"}}
            ],
            "tts_text": "Here are 10 English words for level {level}. " + all 10 English words separated by commas,
            "bg_prompt": "minimalist aesthetic dark moody workspace or cozy library background, vertical 9:16, no text, photorealistic, soft lighting",
            "caption": "10 полезных английских слов уровня {level} 📚 Сохраняй, чтобы не потерять! #английский #учиманглийский #english #vocabulary"
        }}
        """
    else:
        prompt = """
        Generate 1 popular English idiom or phrasal verb (B1-C1 level) with Russian translation and 2 realistic example sentences with Russian translations.
        Return ONLY valid JSON without markdown formatting:
        {
            "mode": "idiom",
            "title": "Фраза дня 🔥",
            "idiom": "English idiom",
            "translation": "Перевод фразы",
            "examples": [
                {"en": "Example 1", "ru": "Перевод 1"},
                {"en": "Example 2", "ru": "Перевод 2"}
            ],
            "tts_text": "Idiom of the day: [idiom]. For example: [Example 1]. Or: [Example 2].",
            "bg_prompt": "cinematic atmospheric street or aesthetic coffee shop scene, dark moody tones, vertical 9:16, no text, photorealistic",
            "caption": "Полезная английская идиома с примерами 🚀 #английскийязык #идиомы #englishidioms #learnenglish"
        }
        """

    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model="gemini-hydrogen",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Ошибка запроса к Gemini (попытка {attempt + 1}/5): {e}")
            if attempt == 4:
                raise
            time.sleep(15)


def generate_background(bg_prompt):
    try:
        result = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=bg_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                output_mime_type="image/jpeg",
            ),
        )
        for generated_image in result.generated_images:
            img = Image.open(BytesIO(generated_image.image.image_bytes))
            return img.resize((1080, 1920))
    except Exception as e:
        print(f"Ошибка генерации фона ({e}), создаем градиентный фон.")
        img = Image.new("RGB", (1080, 1920), color=(25, 28, 36))
        return img


def create_card_image(data, bg_img, output_path="card.png"):
    # Затемняем фон для читаемости текста
    enhancer = ImageEnhance.Brightness(bg_img)
    img = enhancer.enhance(0.45).convert("RGBA")

    # Рисуем полупрозрачную плашку по центру
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    draw_overlay.rounded_rectangle(
        [(60, 220), (1020, 1680)],
        radius=40,
        fill=(15, 17, 23, 210),
        outline=(255, 255, 255, 60),
        width=3,
    )
    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype("font.ttf", 58)
    main_font = ImageFont.truetype("font.ttf", 44)
    sub_font = ImageFont.truetype("font.ttf", 36)

    # Заголовок
    draw.text((110, 270), data["title"], font=title_font, fill=(255, 215, 0))
    y = 380

    if data["mode"] == "words":
        for idx, item in enumerate(data["items"], 1):
            line = f"{idx}. {item['en']} — {item['ru']}"
            wrapped = textwrap.wrap(line, width=34)
            for w_line in wrapped:
                draw.text((110, y), w_line, font=main_font, fill=(255, 255, 255))
                y += 54
            y += 28
    else:
        # Отрисовка идиомы
        for w_line in textwrap.wrap(data["idiom"], width=26):
            draw.text((110, y), w_line, font=title_font, fill=(100, 220, 255))
            y += 68
        y += 10
        for w_line in textwrap.wrap(data["translation"], width=32):
            draw.text((110, y), w_line, font=main_font, fill=(200, 200, 200))
            y += 54

        y += 60
        draw.text((110, y), "Примеры:", font=main_font, fill=(255, 215, 0))
        y += 70

        for ex in data["examples"]:
            for w_line in textwrap.wrap(f"• {ex['en']}", width=34):
                draw.text((110, y), w_line, font=main_font, fill=(255, 255, 255))
                y += 52
            for w_line in textwrap.wrap(f"  ({ex['ru']})", width=38):
                draw.text((110, y), w_line, font=sub_font, fill=(170, 175, 185))
                y += 46
            y += 40

    img.save(output_path)


async def generate_audio(text, output_path="voice.mp3"):
    # Голос en-US-AndrewNeural звучит очень естественно
    communicate = edge_tts.Communicate(text, "en-US-AndrewNeural")
    await communicate.save(output_path)


def build_video(image_path, audio_path, video_path="output.mp4"):
    audio = AudioFileClip(audio_path)
    duration = max(audio.duration + 1.5, 6.0)  # минимум 6 секунд
    clip = ImageClip(image_path).set_duration(duration)
    clip = clip.set_audio(audio)
    clip.write_videofile(video_path, fps=24, codec="libx264", audio_codec="aac")


def main():
    print("1. Генерируем контент...")
    data = generate_content()

    print("2. Генерируем фон...")
    bg = generate_background(data["bg_prompt"])

    print("3. Собираем карточку...")
    create_card_image(data, bg, "card.png")

    print("4. Генерируем озвучку...")
    asyncio.run(generate_audio(data["tts_text"], "voice.mp3"))

    print("5. Рендерим видео...")
    build_video("card.png", "voice.mp3", "output.mp4")

    print("6. Загружаем в TikTok...")
    # Сохраняем sessionid во временный файл cookies.txt в формате Netscape
    with open("cookies.txt", "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(
            f".tiktok.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{TIKTOK_SESSION_ID}\n"
        )

    upload_video(
        "output.mp4",
        description=data["caption"],
        cookies="cookies.txt",
        headless=True,
    )
    print("Готово! Видео опубликовано.")


if __name__ == "__main__":
    main()
