# Raid Question Bank

Approved bank for the AlphaBoss raid questions. The live backend uses this structure in `RAID_QUESTION_SEEDS` and seeds it idempotently by `prompt`.

Target distribution:

- Difficulty 1: 50 questions, A0-HSK1 recognition and survival vocabulary.
- Difficulty 2: 35 questions, HSK1-HSK2 short phrases and practical mini-dialogues.
- Difficulty 3: 15 questions, HSK3-HSK4-light contextual grammar.

Future group-based routing can reuse the same `difficulty` field.

```python
RAID_QUESTION_SEEDS = [
    {
        "prompt": "Сигнал перехвачен. Расшифруй: 出口 (chūkǒu) — что это?",
        "option_a": "Вход",
        "option_b": "Выход",
        "option_c": "Склад",
        "correct_option": "b",
        "explanation": "出口 — выход, точка эвакуации отряда.",
        "difficulty": 1
    },
    {
        "prompt": "Бот-охранник задаёт вопрос: 你叫什么名字？ Что он спрашивает?",
        "option_a": "Твой возраст",
        "option_b": "Твоё имя",
        "option_c": "Пароль доступа",
        "correct_option": "b",
        "explanation": "你叫什么名字？ — как тебя зовут?",
        "difficulty": 1
    },
    {
        "prompt": "Перехвачена команда цели: 现在几点？ Что запрашивает система?",
        "option_a": "Местоположение",
        "option_b": "Уровень угрозы",
        "option_c": "Текущее время",
        "correct_option": "c",
        "explanation": "现在几点？ — который сейчас час?",
        "difficulty": 1
    },
    {
        "prompt": "Агент передаёт счёт ресурсов: 我有五十分。 Сколько единиц?",
        "option_a": "15",
        "option_b": "50",
        "option_c": "500",
        "correct_option": "b",
        "explanation": "五十 (wǔshí) — пятьдесят.",
        "difficulty": 1
    },
    {
        "prompt": "Цель ведёт переговоры в кафе. Слышно: 你吃什么？ О чём речь?",
        "option_a": "Что ты пьёшь",
        "option_b": "Сколько платишь",
        "option_c": "Что ты будешь есть",
        "correct_option": "c",
        "explanation": "你吃什么？ — что ты будешь есть?",
        "difficulty": 1
    },
    {
        "prompt": "Тревожный сигнал системы: 危险！ Что это значит?",
        "option_a": "Опасность",
        "option_b": "Безопасно",
        "option_c": "Продолжать",
        "correct_option": "a",
        "explanation": "危险 (wēixiǎn) — опасность.",
        "difficulty": 1
    },
    {
        "prompt": "Навигатор передаёт: 左转。 Куда повернуть?",
        "option_a": "Направо",
        "option_b": "Назад",
        "option_c": "Налево",
        "correct_option": "c",
        "explanation": "左 (zuǒ) — лево. 左转 — повернуть налево.",
        "difficulty": 1
    },
    {
        "prompt": "Агент легендируется: 我是学生。 Кем он представляется?",
        "option_a": "Врачом",
        "option_b": "Студентом",
        "option_c": "Охранником",
        "correct_option": "b",
        "explanation": "学生 (xuésheng) — студент / ученик.",
        "difficulty": 1
    },
    {
        "prompt": "Шифрованный запрос ресурсов: 这是多少钱？ Что запрашивают?",
        "option_a": "Где находится объект?",
        "option_b": "Когда начало операции?",
        "option_c": "Сколько это стоит?",
        "correct_option": "c",
        "explanation": "这是多少钱？ — сколько это стоит?",
        "difficulty": 1
    },
    {
        "difficulty": 1,
        "prompt": "На двери базы написано 入口. Что это?",
        "option_a": "Вход",
        "option_b": "Выход",
        "option_c": "Касса",
        "correct_option": "a",
        "explanation": "入口 — вход."
    },
    {
        "difficulty": 1,
        "prompt": "Маршрут построен через 地铁. Какой транспорт нужен?",
        "option_a": "Автобус",
        "option_b": "Метро",
        "option_c": "Такси",
        "correct_option": "b",
        "explanation": "地铁 — метро."
    },
    {
        "difficulty": 1,
        "prompt": "В отчёте указано 宿舍. Куда возвращается отряд?",
        "option_a": "В общежитие",
        "option_b": "В библиотеку",
        "option_c": "В магазин",
        "correct_option": "a",
        "explanation": "宿舍 — общежитие."
    },
    {
        "difficulty": 1,
        "prompt": "На карте отмечено 食堂. Что там находится?",
        "option_a": "Больница",
        "option_b": "Столовая",
        "option_c": "Станция метро",
        "correct_option": "b",
        "explanation": "食堂 — столовая."
    },
    {
        "difficulty": 1,
        "prompt": "Сканер нашёл 图书馆. Что это за место?",
        "option_a": "Спортзал",
        "option_b": "Кафе",
        "option_c": "Библиотека",
        "correct_option": "c",
        "explanation": "图书馆 — библиотека."
    },
    {
        "difficulty": 1,
        "prompt": "В экстренном маршруте стоит 医院. Что это?",
        "option_a": "Больница",
        "option_b": "Магазин",
        "option_c": "Почта",
        "correct_option": "a",
        "explanation": "医院 — больница / медпункт."
    },
    {
        "difficulty": 1,
        "prompt": "Оператор ищет 洗手间. Что ему нужно?",
        "option_a": "Столовая",
        "option_b": "Туалет",
        "option_c": "Банк",
        "correct_option": "b",
        "explanation": "洗手间 — туалет."
    },
    {
        "difficulty": 1,
        "prompt": "В сообщении: 我想喝水。 Что хочет агент?",
        "option_a": "Спать",
        "option_b": "Есть рис",
        "option_c": "Пить воду",
        "correct_option": "c",
        "explanation": "喝水 — пить воду."
    },
    {
        "difficulty": 1,
        "prompt": "Код питания: 米饭. Что заказано?",
        "option_a": "Рис",
        "option_b": "Лапша",
        "option_c": "Суп",
        "correct_option": "a",
        "explanation": "米饭 — варёный рис."
    },
    {
        "difficulty": 1,
        "prompt": "В меню найдено 面条. Что это?",
        "option_a": "Чай",
        "option_b": "Лапша",
        "option_c": "Фрукты",
        "correct_option": "b",
        "explanation": "面条 — лапша."
    },
    {
        "difficulty": 1,
        "prompt": "Система отмечает 鸡肉. Что это за еда?",
        "option_a": "Рыба",
        "option_b": "Говядина",
        "option_c": "Курица",
        "correct_option": "c",
        "explanation": "鸡肉 — куриное мясо."
    },
    {
        "difficulty": 1,
        "prompt": "Агент просит 不辣. Какой вкус ему нужен?",
        "option_a": "Не остро",
        "option_b": "Очень сладко",
        "option_c": "Очень холодно",
        "correct_option": "a",
        "explanation": "不辣 — не остро."
    },
    {
        "difficulty": 1,
        "prompt": "В погодном канале: 今天很热. Какая погода?",
        "option_a": "Холодно",
        "option_b": "Жарко",
        "option_c": "Ветрено",
        "correct_option": "b",
        "explanation": "很热 — очень жарко."
    },
    {
        "difficulty": 1,
        "prompt": "Отряд получил сигнал 冷. Что это значит?",
        "option_a": "Далеко",
        "option_b": "Дорого",
        "option_c": "Холодно",
        "correct_option": "c",
        "explanation": "冷 — холодный / холодно."
    },
    {
        "difficulty": 1,
        "prompt": "Команда говорит 今天. О каком дне речь?",
        "option_a": "Сегодня",
        "option_b": "Завтра",
        "option_c": "Вчера",
        "correct_option": "a",
        "explanation": "今天 — сегодня."
    },
    {
        "difficulty": 1,
        "prompt": "План операции на 明天. Когда это?",
        "option_a": "Вчера",
        "option_b": "Сегодня",
        "option_c": "Завтра",
        "correct_option": "c",
        "explanation": "明天 — завтра."
    },
    {
        "difficulty": 1,
        "prompt": "В журнале стоит 昨天. Когда это было?",
        "option_a": "Завтра",
        "option_b": "Вчера",
        "option_c": "Через неделю",
        "correct_option": "b",
        "explanation": "昨天 — вчера."
    },
    {
        "difficulty": 1,
        "prompt": "Навигатор показывает 右边. Где цель?",
        "option_a": "Справа",
        "option_b": "Слева",
        "option_c": "Позади",
        "correct_option": "a",
        "explanation": "右边 — справа."
    },
    {
        "difficulty": 1,
        "prompt": "Дрон пишет 前面. Где объект?",
        "option_a": "Сзади",
        "option_b": "Впереди",
        "option_c": "Внизу",
        "correct_option": "b",
        "explanation": "前面 — впереди."
    },
    {
        "difficulty": 1,
        "prompt": "На карте отмечено 后面. Где это?",
        "option_a": "Внутри",
        "option_b": "Справа",
        "option_c": "Сзади",
        "correct_option": "c",
        "explanation": "后面 — сзади / позади."
    },
    {
        "difficulty": 1,
        "prompt": "Оператор просит 一点儿. Сколько это?",
        "option_a": "Немного",
        "option_b": "Очень много",
        "option_c": "Нисколько",
        "correct_option": "a",
        "explanation": "一点儿 — немного."
    },
    {
        "difficulty": 1,
        "prompt": "Союзник пишет 谢谢. Что он говорит?",
        "option_a": "Извините",
        "option_b": "Спасибо",
        "option_c": "До свидания",
        "correct_option": "b",
        "explanation": "谢谢 — спасибо."
    },
    {
        "difficulty": 1,
        "prompt": "После ошибки агент говорит 对不起. Что это значит?",
        "option_a": "Пожалуйста",
        "option_b": "Не за что",
        "option_c": "Извините",
        "correct_option": "c",
        "explanation": "对不起 — извините."
    },
    {
        "difficulty": 1,
        "prompt": "Канал успокоения: 没关系. Как перевести?",
        "option_a": "Ничего страшного",
        "option_b": "Очень дорого",
        "option_c": "Слишком поздно",
        "correct_option": "a",
        "explanation": "没关系 — ничего страшного / всё в порядке."
    },
    {
        "difficulty": 1,
        "prompt": "Охранник говорит 请等一下. Что нужно сделать?",
        "option_a": "Бежать быстрее",
        "option_b": "Немного подождать",
        "option_c": "Купить билет",
        "correct_option": "b",
        "explanation": "请等一下 — пожалуйста, подождите немного."
    },
    {
        "difficulty": 1,
        "prompt": "Агент докладывает: 我听不懂. Что произошло?",
        "option_a": "Он всё понял",
        "option_b": "Он хочет есть",
        "option_c": "Он не понял на слух",
        "correct_option": "c",
        "explanation": "我听不懂 — я не понимаю на слух."
    },
    {
        "difficulty": 1,
        "prompt": "В инвентаре потерян 手机. Что ищем?",
        "option_a": "Телефон",
        "option_b": "Паспорт",
        "option_c": "Карту",
        "correct_option": "a",
        "explanation": "手机 — мобильный телефон."
    },
    {
        "difficulty": 2,
        "prompt": "Охранник спрашивает: 你去哪儿？ Какой ответ логичный?",
        "option_a": "我去宿舍。",
        "option_b": "三十块。",
        "option_c": "很好吃。",
        "correct_option": "a",
        "explanation": "你去哪儿？ — куда ты идёшь? 我去宿舍 — я иду в общежитие."
    },
    {
        "difficulty": 2,
        "prompt": "Бариста спрашивает: 你想喝什么？ Что ответить?",
        "option_a": "我去学校。",
        "option_b": "我想喝水。",
        "option_c": "现在八点。",
        "correct_option": "b",
        "explanation": "Вопрос о напитке: что ты хочешь пить?"
    },
    {
        "difficulty": 2,
        "prompt": "Система проверяет язык: 你会说中文吗？ Как ответить «немного умею»?",
        "option_a": "二十块。",
        "option_b": "往右走。",
        "option_c": "会一点儿。",
        "correct_option": "c",
        "explanation": "会一点儿 — умею немного."
    },
    {
        "difficulty": 2,
        "prompt": "Связь шумит. Как попросить повторить ещё раз?",
        "option_a": "请再说一遍。",
        "option_b": "请打开门。",
        "option_c": "请给我水。",
        "correct_option": "a",
        "explanation": "请再说一遍 — пожалуйста, повторите ещё раз."
    },
    {
        "difficulty": 2,
        "prompt": "Нужно спросить дорогу. Какая фраза подходит?",
        "option_a": "我很好吃。",
        "option_b": "请问，怎么走？",
        "option_c": "今天星期五。",
        "correct_option": "b",
        "explanation": "请问，怎么走？ — подскажите, как пройти?"
    },
    {
        "difficulty": 2,
        "prompt": "Агент пишет: 我迷路了. Что случилось?",
        "option_a": "Он заблудился",
        "option_b": "Он купил воду",
        "option_c": "Он пришёл вовремя",
        "correct_option": "a",
        "explanation": "迷路 — заблудиться."
    },
    {
        "difficulty": 2,
        "prompt": "Фраза: 请问，地铁站在哪儿？ Что ищет человек?",
        "option_a": "Больницу",
        "option_b": "Столовую",
        "option_c": "Станцию метро",
        "correct_option": "c",
        "explanation": "地铁站 — станция метро; 在哪儿 — где находится?"
    },
    {
        "difficulty": 2,
        "prompt": "Координатор спрашивает: 我们几点集合？ Что он хочет узнать?",
        "option_a": "Во сколько сбор",
        "option_b": "Сколько стоит еда",
        "option_c": "Где телефон",
        "correct_option": "a",
        "explanation": "几点集合？ — во сколько собираемся?"
    },
    {
        "difficulty": 2,
        "prompt": "Команда получила приказ: 七点半集合. Когда сбор?",
        "option_a": "В 7:00",
        "option_b": "В 7:30",
        "option_c": "В 8:30",
        "correct_option": "b",
        "explanation": "半 — половина; 七点半 — 7:30."
    },
    {
        "difficulty": 2,
        "prompt": "В протоколе дисциплины: 不要迟到. Что нельзя делать?",
        "option_a": "Покупать воду",
        "option_b": "Говорить громко",
        "option_c": "Опаздывать",
        "correct_option": "c",
        "explanation": "迟到 — опаздывать; 不要 — не надо."
    },
    {
        "difficulty": 2,
        "prompt": "Расписание: 先吃饭，然后上课. Что сначала?",
        "option_a": "Поесть",
        "option_b": "Пойти на урок",
        "option_c": "Вернуться в общежитие",
        "correct_option": "a",
        "explanation": "先 — сначала; 然后 — потом."
    },
    {
        "difficulty": 2,
        "prompt": "Агент докладывает: 我没有带护照. Чего у него нет с собой?",
        "option_a": "Телефона",
        "option_b": "Паспорта",
        "option_c": "Зонта",
        "correct_option": "b",
        "explanation": "没有带 — не взял с собой; 护照 — паспорт."
    },
    {
        "difficulty": 2,
        "prompt": "В магазине нужно торговаться. Какая фраза подходит?",
        "option_a": "可以便宜一点吗？",
        "option_b": "我迷路了。",
        "option_c": "请保持安静。",
        "correct_option": "a",
        "explanation": "可以便宜一点吗？ — можно немного дешевле?"
    },
    {
        "difficulty": 2,
        "prompt": "Заказ в киоске: 我要一瓶水. Что хочет агент?",
        "option_a": "Одну миску риса",
        "option_b": "Один билет",
        "option_c": "Одну бутылку воды",
        "correct_option": "c",
        "explanation": "一瓶水 — одна бутылка воды."
    },
    {
        "difficulty": 2,
        "prompt": "Покупатель говорит: 这个太贵了. Что он имеет в виду?",
        "option_a": "Это слишком дорого",
        "option_b": "Это очень вкусно",
        "option_c": "Это слишком далеко",
        "correct_option": "a",
        "explanation": "太贵了 — слишком дорого."
    },
    {
        "difficulty": 2,
        "prompt": "Нужна помощь. Какая фраза правильная?",
        "option_a": "我不吃牛肉。",
        "option_b": "请帮我一下。",
        "option_c": "天气很好。",
        "correct_option": "b",
        "explanation": "请帮我一下 — пожалуйста, помогите мне."
    },
    {
        "difficulty": 2,
        "prompt": "Союзник пишет: 我马上来. Когда он придёт?",
        "option_a": "Завтра",
        "option_b": "Уже ушёл",
        "option_c": "Сейчас / скоро",
        "correct_option": "c",
        "explanation": "马上 — сейчас, немедленно, очень скоро."
    },
    {
        "difficulty": 2,
        "prompt": "На улице жара. Какая фраза логична?",
        "option_a": "今天很热，多喝水。",
        "option_b": "今天很热，别带水。",
        "option_c": "今天很热，快睡觉。",
        "correct_option": "a",
        "explanation": "多喝水 — пей больше воды; при жаре это логично."
    },
    {
        "difficulty": 2,
        "prompt": "Прогноз: 如果下雨，带伞. Что нужно сделать, если пойдёт дождь?",
        "option_a": "Купить лапшу",
        "option_b": "Взять зонт",
        "option_c": "Сесть в метро",
        "correct_option": "b",
        "explanation": "如果 — если; 带伞 — взять зонт."
    },
    {
        "difficulty": 2,
        "prompt": "Маршрут: 我坐地铁去学校. Как агент едет в школу?",
        "option_a": "На метро",
        "option_b": "Пешком",
        "option_c": "На такси",
        "correct_option": "a",
        "explanation": "坐地铁 — ехать на метро."
    },
    {
        "difficulty": 2,
        "prompt": "Навигатор говорит: 往右走. Куда идти?",
        "option_a": "Прямо",
        "option_b": "Назад",
        "option_c": "Направо",
        "correct_option": "c",
        "explanation": "往右走 — идти направо."
    },
    {
        "difficulty": 2,
        "prompt": "Команда: 在前面的路口左转. Где повернуть налево?",
        "option_a": "У перекрёстка впереди",
        "option_b": "В комнате",
        "option_c": "На кассе",
        "correct_option": "a",
        "explanation": "前面的路口 — перекрёсток впереди; 左转 — повернуть налево."
    },
    {
        "difficulty": 2,
        "prompt": "В ресторане нужна карта блюд. Какая фраза подходит?",
        "option_a": "请给我地图。",
        "option_b": "请给我菜单。",
        "option_c": "请给我车票。",
        "correct_option": "b",
        "explanation": "菜单 — меню."
    },
    {
        "difficulty": 2,
        "prompt": "Агент предупреждает: 我不吃牛肉. Что он не ест?",
        "option_a": "Курицу",
        "option_b": "Рис",
        "option_c": "Говядину",
        "correct_option": "c",
        "explanation": "牛肉 — говядина."
    },
    {
        "difficulty": 3,
        "prompt": "В отчёте: 因为堵车，所以迟到了. Почему агент опоздал?",
        "option_a": "Из-за пробки",
        "option_b": "Из-за дождя",
        "option_c": "Из-за экзамена",
        "correct_option": "a",
        "explanation": "因为...所以... — потому что..., поэтому...; 堵车 — пробка."
    },
    {
        "difficulty": 3,
        "prompt": "Фраза после длинного дня: 虽然很累，但是很开心. Какой смысл?",
        "option_a": "Не устал и не рад",
        "option_b": "Хотя устал, но доволен",
        "option_c": "Потому что устал, ушёл",
        "correct_option": "b",
        "explanation": "虽然...但是... — хотя..., но..."
    },
    {
        "difficulty": 3,
        "prompt": "Протокол безопасности: 如果迷路了，就问老师. Что делать, если заблудился?",
        "option_a": "Спросить учителя",
        "option_b": "Купить билет",
        "option_c": "Закрыть дверь",
        "correct_option": "a",
        "explanation": "如果...就... — если..., то...; 问老师 — спросить учителя."
    },
    {
        "difficulty": 3,
        "prompt": "Агент пишет: 我把手机放在宿舍了. Где он оставил телефон?",
        "option_a": "В метро",
        "option_b": "В столовой",
        "option_c": "В общежитии",
        "correct_option": "c",
        "explanation": "把手机放在宿舍了 — положил/оставил телефон в общежитии."
    },
    {
        "difficulty": 3,
        "prompt": "Сравнение погоды: 北京比上海冷一点. Что говорится о Пекине?",
        "option_a": "Пекин немного холоднее Шанхая",
        "option_b": "Пекин намного дороже Шанхая",
        "option_c": "Пекин дальше Шанхая",
        "correct_option": "a",
        "explanation": "A 比 B + прилагательное — A более..., чем B; 冷一点 — немного холоднее."
    },
    {
        "difficulty": 3,
        "prompt": "После недели стажировки: 我们越来越熟悉北京了. Что происходит?",
        "option_a": "Мы всё меньше понимаем Пекин",
        "option_b": "Мы всё лучше узнаём Пекин",
        "option_c": "Мы уезжаем из Пекина",
        "correct_option": "b",
        "explanation": "越来越... — всё более и более...; 熟悉 — быть знакомым."
    },
    {
        "difficulty": 3,
        "prompt": "Маршрутный лог: 除了地铁以外，还可以坐公交. Что ещё можно сделать кроме метро?",
        "option_a": "Пойти в библиотеку",
        "option_b": "Купить воду",
        "option_c": "Поехать на автобусе",
        "correct_option": "c",
        "explanation": "除了...以外，还... — кроме..., ещё...; 坐公交 — ехать на автобусе."
    },
    {
        "difficulty": 3,
        "prompt": "Правило рейда: 只要按时集合，就不会扣分. При каком условии не снимут баллы?",
        "option_a": "Если прийти на сбор вовремя",
        "option_b": "Если купить чай",
        "option_c": "Если молчать весь день",
        "correct_option": "a",
        "explanation": "只要...就... — если только..., то...; 按时集合 — собраться вовремя."
    },
    {
        "difficulty": 3,
        "prompt": "Разведчик 一边走一边看地图. Что он делает?",
        "option_a": "Сначала спит, потом идёт",
        "option_b": "Идёт и одновременно смотрит карту",
        "option_c": "Смотрит меню и покупает воду",
        "correct_option": "b",
        "explanation": "一边...一边... — делать два действия одновременно."
    },
    {
        "difficulty": 3,
        "prompt": "Инструкция метро: 先刷卡，然后进站. Что сделать первым?",
        "option_a": "Выйти со станции",
        "option_b": "Спросить учителя",
        "option_c": "Приложить/провести карту",
        "correct_option": "c",
        "explanation": "先 — сначала; 刷卡 — провести/приложить карту."
    },
    {
        "difficulty": 3,
        "prompt": "Канал связи: 他正在跟老师讨论路线. Что он сейчас обсуждает с учителем?",
        "option_a": "Маршрут",
        "option_b": "Цену лапши",
        "option_c": "Погоду завтра",
        "correct_option": "a",
        "explanation": "正在 — действие происходит сейчас; 路线 — маршрут."
    },
    {
        "difficulty": 3,
        "prompt": "Оценка дистанции: 这个地方离宿舍不太远. Что известно о месте?",
        "option_a": "Оно очень дорогое",
        "option_b": "Оно не очень далеко от общежития",
        "option_c": "Оно закрыто",
        "correct_option": "b",
        "explanation": "离...远 — далеко от...; 不太远 — не очень далеко."
    },
    {
        "difficulty": 1,
        "prompt": "Сканер маршрута показывает 火车站. Что это за место?",
        "option_a": "Вокзал",
        "option_b": "Парк",
        "option_c": "Аптека",
        "correct_option": "a",
        "explanation": "火车站 — железнодорожный вокзал."
    },
    {
        "difficulty": 1,
        "prompt": "На карте операции отмечен 机场. Куда ведёт маршрут?",
        "option_a": "В аэропорт",
        "option_b": "В магазин",
        "option_c": "В столовую",
        "correct_option": "a",
        "explanation": "机场 — аэропорт."
    },
    {
        "difficulty": 1,
        "prompt": "Дрон нашёл 公园 рядом с базой. Что это?",
        "option_a": "Парк",
        "option_b": "Банк",
        "option_c": "Класс",
        "correct_option": "a",
        "explanation": "公园 — парк."
    },
    {
        "difficulty": 1,
        "prompt": "Отряд идёт в 超市. Что там можно сделать?",
        "option_a": "Купить продукты",
        "option_b": "Сдать экзамен",
        "option_c": "Постирать вещи",
        "correct_option": "a",
        "explanation": "超市 — супермаркет."
    },
    {
        "difficulty": 1,
        "prompt": "В экстренном маршруте указана 药店. Что это?",
        "option_a": "Аптека",
        "option_b": "Библиотека",
        "option_c": "Стадион",
        "correct_option": "a",
        "explanation": "药店 — аптека."
    },
    {
        "difficulty": 1,
        "prompt": "Координатор говорит 老师. О ком речь?",
        "option_a": "Об учителе",
        "option_b": "О студенте",
        "option_c": "О водителе",
        "correct_option": "a",
        "explanation": "老师 — учитель."
    },
    {
        "difficulty": 1,
        "prompt": "В списке группы написано 同学. Кто это?",
        "option_a": "Одноклассник / товарищ по учёбе",
        "option_b": "Охранник",
        "option_c": "Продавец",
        "correct_option": "a",
        "explanation": "同学 — одноклассник, сокурсник, товарищ по учёбе."
    },
    {
        "difficulty": 1,
        "prompt": "Система сообщает 早上集合. Когда сбор?",
        "option_a": "Утром",
        "option_b": "Вечером",
        "option_c": "Ночью",
        "correct_option": "a",
        "explanation": "早上 — утро."
    },
    {
        "difficulty": 1,
        "prompt": "В расписании стоит 晚上. Какое время суток?",
        "option_a": "Утро",
        "option_b": "Вечер",
        "option_c": "Полдень",
        "correct_option": "b",
        "explanation": "晚上 — вечер."
    },
    {
        "difficulty": 1,
        "prompt": "Протокол дня: 星期一. Какой это день?",
        "option_a": "Понедельник",
        "option_b": "Пятница",
        "option_c": "Воскресенье",
        "correct_option": "a",
        "explanation": "星期一 — понедельник."
    },
    {
        "difficulty": 1,
        "prompt": "Сигнал времени: 一点. Сколько времени?",
        "option_a": "Один час",
        "option_b": "Два часа",
        "option_c": "Полчаса",
        "correct_option": "a",
        "explanation": "一点 — один час."
    },
    {
        "difficulty": 1,
        "prompt": "Встреча назначена на 两点半. Когда это?",
        "option_a": "2:30",
        "option_b": "1:30",
        "option_c": "12:00",
        "correct_option": "a",
        "explanation": "两点半 — половина третьего, 2:30."
    },
    {
        "difficulty": 1,
        "prompt": "Охранник спрашивает 多少人？ Что он хочет узнать?",
        "option_a": "Сколько человек",
        "option_b": "Сколько денег",
        "option_c": "Куда идти",
        "correct_option": "a",
        "explanation": "多少人？ — сколько человек?"
    },
    {
        "difficulty": 1,
        "prompt": "Перед просьбой агент добавляет 请. Что это значит?",
        "option_a": "Пожалуйста",
        "option_b": "Опасно",
        "option_c": "Слишком дорого",
        "correct_option": "a",
        "explanation": "请 — пожалуйста; вежливый маркер просьбы."
    },
    {
        "difficulty": 2,
        "prompt": "Агент говорит: 我想买一张地铁票. Что он хочет купить?",
        "option_a": "Билет на метро",
        "option_b": "Бутылку воды",
        "option_c": "Карту города",
        "correct_option": "a",
        "explanation": "买一张地铁票 — купить один билет на метро."
    },
    {
        "difficulty": 2,
        "prompt": "Фраза для ориентации: 请问，洗手间在哪儿？ Что ищет человек?",
        "option_a": "Туалет",
        "option_b": "Выход",
        "option_c": "Столовую",
        "correct_option": "a",
        "explanation": "洗手间在哪儿？ — где туалет?"
    },
    {
        "difficulty": 2,
        "prompt": "Расписание группы: 我们明天上午八点集合. Когда сбор?",
        "option_a": "Завтра утром в 8",
        "option_b": "Сегодня вечером в 8",
        "option_c": "Вчера утром в 8",
        "correct_option": "a",
        "explanation": "明天上午八点集合 — завтра утром в 8 сбор."
    },
    {
        "difficulty": 2,
        "prompt": "Инструкция поддержки: 如果你累了，就休息一下. Что советуют сделать, если устал?",
        "option_a": "Немного отдохнуть",
        "option_b": "Бежать быстрее",
        "option_c": "Купить билет",
        "correct_option": "a",
        "explanation": "如果...就... — если..., то...; 休息一下 — немного отдохнуть."
    },
    {
        "difficulty": 2,
        "prompt": "Агент предупреждает: 我不太会说中文. Что он сообщает?",
        "option_a": "Он не очень хорошо говорит по-китайски",
        "option_b": "Он не любит китайскую еду",
        "option_c": "Он потерял телефон",
        "correct_option": "a",
        "explanation": "不太会说中文 — не очень умею говорить по-китайски."
    },
    {
        "difficulty": 2,
        "prompt": "В столовой агент говорит: 这个菜有点儿辣. Что не так с блюдом?",
        "option_a": "Немного острое",
        "option_b": "Очень холодное",
        "option_c": "Слишком дешёвое",
        "correct_option": "a",
        "explanation": "有点儿辣 — немного острое."
    },
    {
        "difficulty": 2,
        "prompt": "Маршрутный запрос: 从宿舍到教室怎么走？ Что хотят узнать?",
        "option_a": "Как пройти от общежития до аудитории",
        "option_b": "Сколько стоит обед",
        "option_c": "Где купить воду",
        "correct_option": "a",
        "explanation": "从...到...怎么走？ — как пройти от ... до ...?"
    },
    {
        "difficulty": 2,
        "prompt": "Отчёт разведчика: 我昨天去了图书馆. Где он был вчера?",
        "option_a": "В библиотеке",
        "option_b": "В больнице",
        "option_c": "В аэропорту",
        "correct_option": "a",
        "explanation": "昨天去了图书馆 — вчера ходил в библиотеку."
    },
    {
        "difficulty": 2,
        "prompt": "В кафе агент просит: 请给我一杯热水. Что ему нужно?",
        "option_a": "Стакан горячей воды",
        "option_b": "Холодная лапша",
        "option_c": "Билет на автобус",
        "correct_option": "a",
        "explanation": "一杯热水 — один стакан горячей воды."
    },
    {
        "difficulty": 2,
        "prompt": "План экскурсии: 我们坐公交车去博物馆. Как едет группа?",
        "option_a": "На автобусе",
        "option_b": "На метро",
        "option_c": "Пешком",
        "correct_option": "a",
        "explanation": "坐公交车 — ехать на автобусе; 博物馆 — музей."
    },
    {
        "difficulty": 2,
        "prompt": "Командный канал: 老师说不要迟到. Что сказал учитель?",
        "option_a": "Не опаздывать",
        "option_b": "Не пить воду",
        "option_c": "Не покупать билеты",
        "correct_option": "a",
        "explanation": "不要迟到 — не опаздывать."
    },
    {
        "difficulty": 3,
        "prompt": "Оперативный отчёт: 因为下雨，所以我们改坐地铁. Почему группа пересела на метро?",
        "option_a": "Из-за дождя",
        "option_b": "Из-за жары",
        "option_c": "Из-за пробки",
        "correct_option": "a",
        "explanation": "因为...所以... — потому что..., поэтому...; 下雨 — идёт дождь."
    },
    {
        "difficulty": 3,
        "prompt": "Агент пишет: 他把钥匙放在房间里了. Что он сделал с ключом?",
        "option_a": "Оставил/положил ключ в комнате",
        "option_b": "Купил новый ключ",
        "option_c": "Отдал ключ учителю",
        "correct_option": "a",
        "explanation": "把钥匙放在房间里 — положил ключ в комнате."
    },
    {
        "difficulty": 3,
        "prompt": "Фраза стажировки: 虽然中文有点难，但是我越来越喜欢. Какой смысл?",
        "option_a": "Хотя китайский немного сложный, он нравится всё больше",
        "option_b": "Китайский лёгкий, но не нравится",
        "option_c": "Китайский закончился вчера",
        "correct_option": "a",
        "explanation": "虽然...但是... — хотя..., но...; 越来越喜欢 — нравится всё больше."
    }
]
```
