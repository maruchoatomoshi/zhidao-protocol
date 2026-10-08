"""Контактный лист ключевых кадров out/keys/*.png -> out/contact.png (для проверки ролика глазами)."""
import glob, sys
from PIL import Image, ImageDraw
files = sorted(glob.glob("out/keys/*.png"))
cols = int(sys.argv[1]) if len(sys.argv) > 1 else 6
tw, th = 360, 640
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize((tw, th))
    ImageDraw.Draw(im).text((8, 8), f.split("\\")[-1].split("/")[-1], fill=(255, 255, 0))
    sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
sheet.save("out/contact.png")
print(len(files), sheet.size)
