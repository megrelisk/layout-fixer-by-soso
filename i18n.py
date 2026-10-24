"""Interface texts in Georgian, English and Russian.

t("key", name=value) returns the text in the current language. The language is
chosen in the tray menu and stored in settings ("ui_lang").
"""

LANGS = ("ka", "en", "ru")
NATIVE = {"ka": "ქართული", "en": "English", "ru": "Русский"}
DEFAULT = "ka"

_lang = DEFAULT


def set_lang(lang):
    global _lang
    _lang = lang if lang in LANGS else DEFAULT


def get_lang():
    return _lang


def t(key, **kw):
    entry = TEXTS[key]
    text = entry.get(_lang) or entry["en"]
    return text.format(**kw) if kw else text


TEXTS = {
    # --- tray
    "tray.title": {
        "ka": "LayoutFixer: EN / RU / KA\nPause/Break: გაუქმება ან ხელით გასწორება",
        "en": "LayoutFixer: EN / RU / KA\nPause/Break: undo or fix by hand",
        "ru": "LayoutFixer: EN / RU / KA\nPause/Break: отменить или исправить вручную",
    },
    "menu.help": {"ka": "შესაძლებლობები და ცხელი კლავიშები...",
                  "en": "Features and hotkeys...", "ru": "Возможности и горячие клавиши..."},
    "help.title": {"ka": "LayoutFixer: შესაძლებლობები", "en": "LayoutFixer: features",
                   "ru": "LayoutFixer: возможности"},
    "help.text": {
        "ka": "ავტომატური\n"
              "• განლაგების გასწორება სიტყვის დასრულებისას (ინტერვალი/Enter/Tab) და ადრე, 4 ასოს შემდეგ\n"
              "• შემთხვევითი Caps Lock-ის გასწორება (hELLO → Hello)\n"
              "• ბეჭდვითი შეცდომები; ეჭვიან სიტყვას წითელი ნიშანი ეძლევა\n"
              "• Enter ინახავს ასწორებად სიტყვას: წითელი ნიშანი; მეორე Enter აგზავნის უცვლელად\n"
              "• წაშლილი გასწორება → სიტყვა გამონაკლისებში, აღარ შეიცვლება\n"
              "• ჩემი სიტყვების დამახსოვრება; ავტოჩანაცვლება (autotext.txt)\n\n"
              "ცხელი კლავიშები (იცვლება: მენიუ → ცხელი კლავიშები)\n"
              "• {manual}: გასწორების გაუქმება ან სიტყვის გადაკეთება\n"
              "• {line}: მთელი ხაზის გადაკეთება\n"
              "• {selection}: მონიშნული ტექსტის გადაკეთება\n"
              "• {toggle_app}: გამორთვა/ჩართვა მიმდინარე პროგრამაში\n\n"
              "მენიუში: ხმა, ენა ხატულაზე და კურსორთან, პროგრამები სადაც გამორთულია, "
              "გამონაკლისები, სტატისტიკა, გაზიარება, განახლება",
        "en": "Automatic\n"
              "• Layout fix when a word ends (Space/Enter/Tab) and early, after 4 letters\n"
              "• Accidental Caps Lock fix (hELLO → Hello)\n"
              "• Typos; doubtful words get a red mark\n"
              "• Enter holds back a word that would be fixed: red mark; a second Enter sends it as is\n"
              "• Erased fix → the word goes to exceptions and is not fixed again\n"
              "• Learns your words; autotext (autotext.txt)\n\n"
              "Hotkeys (change: menu → Hotkeys)\n"
              "• {manual}: undo a fix or convert the word\n"
              "• {line}: convert the whole line\n"
              "• {selection}: convert the selected text\n"
              "• {toggle_app}: off/on in the current app\n\n"
              "In the menu: sound, language in the tray icon and at the cursor, apps where "
              "it is off, exceptions, statistics, sharing, update",
        "ru": "Автоматически\n"
              "• Исправление раскладки при завершении слова (пробел/Enter/Tab) и раньше, после 4 букв\n"
              "• Случайный Caps Lock (hELLO → Hello)\n"
              "• Опечатки; сомнительное слово получает красную метку\n"
              "• Enter задерживает слово, которое будет исправлено: красная метка; второй Enter отправит как есть\n"
              "• Стёртое исправление → слово в исключениях и больше не исправляется\n"
              "• Запоминает ваши слова; автозамена (autotext.txt)\n\n"
              "Горячие клавиши (меняются: меню → Горячие клавиши)\n"
              "• {manual}: отменить исправление или перевести слово\n"
              "• {line}: перевести всю строку\n"
              "• {selection}: перевести выделенный текст\n"
              "• {toggle_app}: выкл/вкл в текущей программе\n\n"
              "В меню: звук, язык на значке и у курсора, программы где отключено, "
              "исключения, статистика, «Поделиться опытом», обновление",
    },
    "menu.stats": {"ka": "სტატისტიკა...", "en": "Statistics...", "ru": "Статистика..."},
    "menu.reset_stats": {"ka": "სტატისტიკის განულება...", "en": "Reset statistics...",
                         "ru": "Обнулить статистику..."},
    "menu.enabled": {"ka": "განლაგების ავტომატური გასწორება",
                     "en": "Fix wrong keyboard layout",
                     "ru": "Автоисправление раскладки"},
    "menu.early": {"ka": "ადრეული გასწორება (4 ასოს შემდეგ)",
                   "en": "Fix early (after 4 letters)",
                   "ru": "Исправлять раньше (после 4 букв)"},
    "menu.caps": {"ka": "შემთხვევითი Caps Lock (hELLO → Hello)",
                  "en": "Accidental Caps Lock (hELLO → Hello)",
                  "ru": "Случайный Caps Lock (hELLO → Hello)"},
    "menu.spell": {"ka": "ბეჭდვითი შეცდომები (ტბილისი → თბილისი)",
                   "en": "Typos (teh → the)",
                   "ru": "Опечатки (првиет → привет)"},
    "menu.learn": {"ka": "ჩემი სიტყვების დამახსოვრება",
                   "en": "Learn my words",
                   "ru": "Запоминать мои слова"},
    "menu.badge": {"ka": "ენის მაჩვენებელი კურსორთან",
                   "en": "Show language at the cursor",
                   "ru": "Показывать язык у курсора"},
    "menu.sound": {"ka": "ხმოვანი სიგნალი გასწორებისას", "en": "Sound when something is fixed",
                   "ru": "Звук при исправлении"},
    "menu.tray_icon": {"ka": "ენა ხატულაზე (ტრეი)", "en": "Show language in the tray icon",
                       "ru": "Язык на значке в трее"},
    "menu.apps": {"ka": "პროგრამები, სადაც გამორთულია...", "en": "Apps where it is off...",
                  "ru": "Программы, где отключено..."},
    "menu.autotext": {"ka": "ავტოჩანაცვლება (აბრევიატურები)...", "en": "Autotext (abbreviations)...",
                      "ru": "Автозамена (аббревиатуры)..."},
    "menu.hotkeys": {"ka": "ცხელი კლავიშები...", "en": "Hotkeys...", "ru": "Горячие клавиши..."},
    "hotkeys.header": {
        "ka": "# ცხელი კლავიშები: მოქმედება = კლავიშები. შემდეგ: მენიუ → თავიდან წაკითხვა.\n"
              "# manual: გასწორების გაუქმება ან სიტყვის გადაკეთება; line: მთელი ხაზი;\n"
              "# selection: მონიშნული ტექსტი; toggle_app: გამორთვა/ჩართვა ამ პროგრამაში.\n"
              "# კლავიშები: ctrl, alt, shift, win + A-Z, 0-9, F1-F24, Pause, Break, Insert, Home...\n",
        "en": "# Hotkeys: action = keys. Then: menu -> Reload.\n"
              "# manual: undo a fix or convert the word; line: the whole line;\n"
              "# selection: the selected text; toggle_app: off/on in the current app.\n"
              "# Keys: ctrl, alt, shift, win + A-Z, 0-9, F1-F24, Pause, Break, Insert, Home...\n",
        "ru": "# Горячие клавиши: действие = клавиши. Потом: меню -> Перечитать.\n"
              "# manual: отмена исправления или конвертация слова; line: вся строка;\n"
              "# selection: выделенный текст; toggle_app: выкл/вкл в этой программе.\n"
              "# Клавиши: ctrl, alt, shift, win + A-Z, 0-9, F1-F24, Pause, Break, Insert, Home...\n",
    },
    "autotext.header": {
        "ka": "# ავტოჩანაცვლება: აბრევიატურა = ტექსტი (მაგ. \"mb = may be\").\n"
              "# მუშაობს სიტყვის დასრულებისას, ნებისმიერ განლაგებაში. შემდეგ: მენიუ → თავიდან წაკითხვა.\n",
        "en": "# Autotext: abbreviation = text (e.g. \"mb = may be\").\n"
              "# Works when a word is finished, in any layout. Then: menu -> Reload.\n",
        "ru": "# Автозамена: аббревиатура = текст (напр. \"мб = может быть\").\n"
              "# Работает при завершении слова, в любой раскладке. Потом: меню -> Перечитать.\n",
    },
    "apps.header": {
        "ka": "# პროგრამები, სადაც LayoutFixer არაფერს აკეთებს: ერთი სახელი ხაზზე (მაგ. game.exe).\n"
              "# ცხელი კლავიში toggle_app ამატებს/შლის მიმდინარე პროგრამას. შემდეგ: მენიუ → თავიდან წაკითხვა.\n",
        "en": "# Apps where LayoutFixer does nothing: one name per line (e.g. game.exe).\n"
              "# The toggle_app hotkey adds/removes the current app. Then: menu -> Reload.\n",
        "ru": "# Программы, где LayoutFixer ничего не делает: по имени на строку (напр. game.exe).\n"
              "# Горячая клавиша toggle_app добавляет/убирает текущую программу. Потом: меню -> Перечитать.\n",
    },
    "menu.autostart": {"ka": "Windows-თან ერთად ჩართვა", "en": "Start with Windows",
                       "ru": "Запускать вместе с Windows"},
    "menu.language": {"ka": "ენა / Language / Язык", "en": "ენა / Language / Язык",
                      "ru": "ენა / Language / Язык"},
    "menu.words": {"ka": "ჩემი სიტყვები...", "en": "My words...", "ru": "Мои слова..."},
    "menu.exceptions": {"ka": "გამონაკლისები (არ გასასწორებელი სიტყვები)...",
                        "en": "Exceptions (words never to fix)...",
                        "ru": "Исключения (слова, которые не исправлять)..."},
    "menu.reload": {"ka": "გამონაკლისების და განლაგებების თავიდან წაკითხვა",
                    "en": "Reload exceptions and layouts",
                    "ru": "Перечитать исключения и раскладки"},
    "menu.share": {"ka": "გამოცდილების გაზიარება პროექტისთვის...",
                   "en": "Share experience with the project...",
                   "ru": "Поделиться опытом с проектом..."},
    "menu.update": {"ka": "განახლება", "en": "Update", "ru": "Обновить"},
    "menu.update_busy": {"ka": "განახლება: იტვირთება...", "en": "Update: downloading...",
                         "ru": "Обновление: загрузка..."},
    "menu.update_ready": {"ka": "განახლება: ახალი ვერსია მზადაა!",
                          "en": "Update: a new version is ready!",
                          "ru": "Обновить: есть новая версия!"},
    "menu.quit": {"ka": "გასვლა", "en": "Exit", "ru": "Выход"},

    # --- dialogs
    "stats.title": {"ka": "LayoutFixer: სტატისტიკა", "en": "LayoutFixer: statistics",
                    "ru": "LayoutFixer: статистика"},
    "stats.reset_ask": {"ka": "განვაულო მთელი სტატისტიკა?", "en": "Reset all statistics?",
                        "ru": "Обнулить всю статистику?"},
    "update.exe_only": {"ka": "განახლება მუშაობს მხოლოდ LayoutFixer.exe-ში.",
                        "en": "Updating works only in LayoutFixer.exe.",
                        "ru": "Обновление работает только в LayoutFixer.exe."},
    "update.progress": {"ka": "LayoutFixer: განახლება {pct}%", "en": "LayoutFixer: updating {pct}%",
                        "ru": "LayoutFixer: обновление {pct}%"},
    "update.failed": {"ka": "განახლება ვერ მოხერხდა:\n{error}", "en": "Update failed:\n{error}",
                      "ru": "Не удалось обновить:\n{error}"},
    "update.failed_log": {"ka": "განახლება ვერ მოხერხდა. დეტალები: log.txt",
                          "en": "Update failed. Details: log.txt",
                          "ru": "Не удалось обновить. Подробности: log.txt"},
    "update.latest": {"ka": "უკვე ბოლო ვერსია გაქვთ.", "en": "You already have the latest version.",
                      "ru": "У вас уже последняя версия."},
    "update.notify": {"ka": "ხელმისაწვდომია ახალი ვერსია.\nმარჯვენა კლიკი ხატულაზე → განახლება",
                      "en": "A new version is available.\nRight-click the icon → Update",
                      "ru": "Вышла новая версия.\nПравый клик по иконке → Обновить"},
    "update.err.network": {"ka": "GitHub-თან კავშირი ვერ დამყარდა ({detail})",
                           "en": "could not reach GitHub ({detail})",
                           "ru": "не удалось связаться с GitHub ({detail})"},
    "update.err.no_exe": {"ka": "Release-ში LayoutFixer.exe არ არის",
                          "en": "the release has no LayoutFixer.exe",
                          "ru": "в релизе нет LayoutFixer.exe"},
    "update.err.download": {"ka": "ჩამოტვირთვა ვერ მოხერხდა ({detail})",
                            "en": "download failed ({detail})",
                            "ru": "не удалось скачать ({detail})"},
    "update.err.size": {"ka": "ფაილი ბოლომდე ვერ ჩამოიტვირთა ({detail})",
                        "en": "the file did not download completely ({detail})",
                        "ru": "файл скачался не полностью ({detail})"},
    "update.err.access": {"ka": "საქაღალდეში ჩაწერა არ არის ნებადართული ({detail}). "
                                "გადაიტანეთ LayoutFixer.exe, მაგალითად, C:\\Programs\\LayoutFixer-ში",
                          "en": "no permission to write to the folder ({detail}). "
                                "Move LayoutFixer.exe, e.g. to C:\\Programs\\LayoutFixer",
                          "ru": "нет прав на запись в папку ({detail}). "
                                "Перенесите LayoutFixer.exe, например в C:\\Programs\\LayoutFixer"},
    "update.err.hash": {"ka": "საკონტროლო ჯამი არ ემთხვევა, ფაილი დაზიანებულია",
                        "en": "checksum mismatch, the file is damaged",
                        "ru": "контрольная сумма не совпала, файл повреждён"},

    # --- statistics window
    "dur.s": {"ka": "{s} წმ", "en": "{s} s", "ru": "{s} с"},
    "dur.ms": {"ka": "{m} წთ {s} წმ", "en": "{m} min {s} s", "ru": "{m} мин {s} с"},
    "dur.m": {"ka": "{m} წთ", "en": "{m} min", "ru": "{m} мин"},
    "dur.hm": {"ka": "{h} სთ {m} წთ", "en": "{h} h {m} min", "ru": "{h} ч {m} мин"},
    "dur.h": {"ka": "{h} სთ", "en": "{h} h", "ru": "{h} ч"},
    "stats.today": {"ka": "დღეს", "en": "Today", "ru": "Сегодня"},
    "stats.week": {"ka": "7 დღეში", "en": "Last 7 days", "ru": "За 7 дней"},
    "stats.month": {"ka": "30 დღეში", "en": "Last 30 days", "ru": "За 30 дней"},
    "stats.all": {"ka": "სულ", "en": "All time", "ru": "Всего"},
    "stats.line": {"ka": "{title}: {n} გასწორება, დაზოგილია {time}",
                   "en": "{title}: {n} fixes, saved {time}",
                   "ru": "{title}: {n} исправл., сэкономлено {time}"},
    "stats.kinds": {"ka": "    განლაგება {layout} (მათ შორის ადრეული {early}), Caps Lock {caps}, "
                          "ხელით (Pause) {manual}, გაუქმებული {undo}",
                    "en": "    layout {layout} (early {early}), Caps Lock {caps}, "
                          "by hand (Pause) {manual}, undone {undo}",
                    "ru": "    раскладка {layout} (из них рано {early}), Caps Lock {caps}, "
                          "вручную (Pause) {manual}, отменено {undo}"},
    "stats.kinds2": {"ka": "    შეცდომები: თავისით გასწორდა {spell}, არჩეულია ვარიანტებიდან {suggest}",
                     "en": "    typos: fixed right away {spell}, picked from suggestions {suggest}",
                     "ru": "    опечатки: исправлено сразу {spell}, выбрано из подсказок {suggest}"},
    "stats.pairs": {"ka": "აკრეფილი → უნდა ყოფილიყო:", "en": "Typed in → meant:",
                    "ru": "Было набрано → должно быть:"},
    "stats.top": {"ka": "ყველაზე ხშირად სწორდებოდა: {words}",
                  "en": "Fixed most often: {words}",
                  "ru": "Чаще всего исправлялись: {words}"},
    "stats.learned": {"ka": "ნასწავლი სიტყვები: {n}", "en": "Learned words: {n}",
                      "ru": "Выученные слова: {n}"},
    "stats.speed": {"ka": "თქვენი აკრეფის სიჩქარე: დაახლოებით {cpm} სიმბოლო წუთში.",
                    "en": "Your typing speed: about {cpm} characters per minute.",
                    "ru": "Ваша скорость набора: около {cpm} знаков в минуту."},
    "stats.method": {"ka": "დრო მიახლოებით ითვლება: შეცდომის შემჩნევა, სიტყვის წაშლა,\n"
                           "განლაგების გადართვა და თავიდან აკრეფა თქვენი სიჩქარით.",
                     "en": "Time is a rough estimate: noticing the mistake, erasing the word,\n"
                           "switching the layout and retyping it at your speed.",
                     "ru": "Время считается грубо: заметить ошибку, стереть слово,\n"
                           "переключить раскладку и набрать заново с вашей скоростью."},
    "stats.since": {"ka": "სტატისტიკა ითვლება {day}-დან.", "en": "Counting since {day}.",
                    "ru": "Статистика ведётся с {day}."},
    "stats.short": {"ka": "დღეს დაზოგილია {today}, სულ {total}",
                    "en": "Saved today {today}, total {total}",
                    "ru": "Сэкономлено сегодня {today}, всего {total}"},

    # --- personal words
    "words.header": {
        "ka": "# ჩემი სიტყვები: პროგრამა მათ სწორად თვლის და არ ასწორებს.\n"
              "# ერთი სიტყვა თითო ხაზზე: ენა, ჰარი, სიტყვა (მაგ. \"ka სოსო\").\n"
              "# წაშალეთ ხაზი, თუ სიტყვა აღარ გინდათ. შემდეგ: მენიუ → თავიდან წაკითხვა.\n",
        "en": "# My words: the program treats them as correct and never fixes them.\n"
              "# One per line: language, space, word (e.g. \"en Soso\").\n"
              "# Delete a line to forget a word, then: menu → Reload.\n",
        "ru": "# Мои слова: программа считает их правильными и не исправляет.\n"
              "# По одному в строке: язык, пробел, слово (например \"ru Сосо\").\n"
              "# Удалите строку, чтобы забыть слово, затем: меню → Перечитать.\n",
    },

    # --- sharing experience
    "share.ask": {
        "ka": "შეიქმნა ანგარიში, რომელიც პროექტს დაეხმარება პროგრამის გაუმჯობესებაში "
              "ყველასთვის. ის Notepad-ში გაიხსნა, გადახედეთ.\n\n"
              "ანგარიშში არ არის თქვენი ტექსტი: მხოლოდ რიცხვები და ცალკეული სიტყვები, "
              "რომლებიც პროგრამამ არასწორად გაასწორა, დატოვეთ ან ისწავლა. "
              "შეგიძლიათ Notepad-ში წაშალოთ, რისი გაზიარებაც არ გსურთ, და შეინახოთ.\n\n"
              "გავხსნა GitHub, რომ ანგარიში გაგზავნოთ?",
        "en": "A report was created that helps the project improve the program for "
              "everyone. It is open in Notepad, please look through it.\n\n"
              "It contains none of your text: only counts and single words the program "
              "fixed wrongly, you kept, or it learned. You can delete anything you do not "
              "want to share in Notepad and save.\n\n"
              "Open GitHub to send it?",
        "ru": "Создан отчёт, который поможет проекту улучшить программу для всех. "
              "Он открыт в Блокноте, просмотрите его.\n\n"
              "В нём нет вашего текста: только числа и отдельные слова, которые программа "
              "исправила неправильно, которые вы оставили или которые она выучила. "
              "Можно удалить в Блокноте всё, чем не хотите делиться, и сохранить.\n\n"
              "Открыть GitHub, чтобы отправить его?",
    },
    "share.issue_title": {"ka": "გამოცდილების ანგარიში", "en": "Experience report",
                          "ru": "Отчёт об опыте"},
    "share.issue_body": {
        "ka": "გადმოათრიეთ აქ ფაილი {file}\n(ის გახსნილია Notepad-ში, საქაღალდე: {folder})\n\n{summary}",
        "en": "Drag the file {file} here\n(it is open in Notepad, folder: {folder})\n\n{summary}",
        "ru": "Перетащите сюда файл {file}\n(он открыт в Блокноте, папка: {folder})\n\n{summary}",
    },
    "share.nothing": {"ka": "ჯერ გასაზიარებელი არაფერია. ცოტა ხნით გამოიყენეთ პროგრამა.",
                      "en": "Nothing to share yet. Use the program for a while first.",
                      "ru": "Пока нечем делиться. Попользуйтесь программой немного."},
}
