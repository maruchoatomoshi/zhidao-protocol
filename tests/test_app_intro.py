"""Заставка при запуске (intro.js, intro.css, слои из tools/intro_layers.py).

Сам генератор слоёв требует OpenCV и в CI не запускается; здесь проверяется
то, что без него проверить можно: каждый слой, который ждёт разметка, лежит
на диске и размещён в сгенерированном intro-layers.css, картинки не качаются
до решения скрипта (data-src), а скрипт стоит в <head> без defer — иначе
приложение мелькнёт до заставки.
"""
import re
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "zhidao_v4/static/app"


class IntroTests(unittest.TestCase):
    def setUp(self):
        self.html = (APP / "index.html").read_text(encoding="utf-8")
        self.layers_css = (APP / "intro-layers.css").read_text(encoding="utf-8")

    def test_every_layer_exists_and_is_placed(self):
        layers = re.findall(r'<img class="intro-(\w+)" data-src="\./assets/intro/(\w+)\.webp"', self.html)
        self.assertEqual({name for name, _ in layers}, {"plate", "dragon", "pix", "text", "glass", "logo"})
        for name, file in layers:
            self.assertEqual(name, file)
            self.assertTrue((APP / f"assets/intro/{file}.webp").is_file(), file)
            self.assertIn(f".app-intro .intro-{name} {{", self.layers_css)
        self.assertIn("tools/intro_layers.py", self.layers_css)

    def test_images_wait_for_the_script(self):
        intro = self.html[self.html.index('id="appIntro"'):self.html.index("</div>\n  </div>", self.html.index('id="appIntro"'))]
        self.assertNotIn(" src=", intro)

    def test_script_decides_before_first_paint(self):
        head = self.html[:self.html.index("</head>")]
        tag = re.search(r'<script src="\./intro\.js\?v=\w+"[^>]*>', head)
        self.assertIsNotNone(tag)
        self.assertNotIn("defer", tag.group(0))
        self.assertLess(head.index("intro.js"), head.index("intro.css"))

    def test_springs_load_before_the_intro(self):
        # Заставка берёт пружины из motion-kit.js: он обязан стоять раньше
        # и тоже без defer, а его стили — последними, поверх соседей.
        head = self.html[:self.html.index("</head>")]
        kit = re.search(r'<script src="\./motion-kit\.js\?v=\w+"[^>]*>', head)
        self.assertIsNotNone(kit)
        self.assertNotIn("defer", kit.group(0))
        self.assertLess(head.index("motion-kit.js"), head.index("intro.js"))
        sheets = re.findall(r'<link rel="stylesheet" href="\./([\w-]+\.css)', head)
        self.assertEqual(sheets[-1], "motion-kit.css")


if __name__ == "__main__":
    unittest.main()
