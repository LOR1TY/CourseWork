# 🌸 Флора — версия для Flet 1.0.1

Тот же магазин, но код переписан под **Flet 1.0.1** (в 1.0 API изменился, и код для 0.28.3 в нём не запускается).

## Запуск на компьютере (PyCharm)
```
pip install -r requirements.txt        # ставит flet[all]==1.0.1
python main.py
```
Если раньше стоял Flet 0.28.3, лучше создать новое виртуальное окружение (File → Settings → Python Interpreter) или выполнить `pip install -U "flet[all]==1.0.1"`.
Проверить версию: `flet --version`.

## Запуск на телефоне (Android)
1. Установите/обновите приложение **Flet** из Google Play. Версия приложения на телефоне и пакет `flet` на компьютере должны быть из одной линии: если на телефоне 1.0.x, на компьютере нужен `flet==1.0.1` (или та же версия, что показывает приложение). Старый пакет 0.28.3 с новым приложением, и наоборот, не соединяются.
2. Телефон и компьютер — в **одной Wi-Fi сети** (не гостевой, без VPN).
3. В терминале PyCharm: `flet run --android` — в консоли появится QR-код.
4. Откройте на телефоне приложение «Камера», наведите на QR-код и нажмите на ссылку — «Флора» откроется в приложении Flet.
5. Если не соединяется: разрешите Python в брандмауэре Windows для «частных сетей» и перезапустите `flet run --android`.

## Сборка APK
```
flet build apk
```
Готовый файл — в `build/apk`. Приложение использует только стандартную библиотеку Python, поэтому дополнительных пакетов не нужно.

## Что изменилось по сравнению с версией для 0.28.3
| Было (0.28.3) | Стало (1.0.1) |
|---|---|
| `ft.app(target=main)` | `ft.run(main)` |
| `ElevatedButton("Текст")`, `TextButton("Текст")` | `Button(content="Текст")`, `TextButton(content="Текст")` |
| `page.open(dlg)` / `page.close(dlg)` | `page.show_dialog(dlg)` / `page.pop_dialog()` |
| `ft.padding.*`, `ft.border.all`, `ft.alignment.center` | `ft.Padding.*`, `ft.Border.all`, `ft.Alignment.CENTER` |
| `ft.ImageFit.COVER`, `Image(src_base64=...)` | `ft.BoxFit.COVER`, `Image(src=<bytes>)` |
| `ft.dropdown.Option`, `Dropdown(on_change=...)` | `ft.DropdownOption`, `Dropdown(on_select=...)` |
| фоновый `threading.Thread` для фото | `page.run_task(...)` + `asyncio.to_thread` (в 1.0 обработчики работают в одном потоке с интерфейсом) |
| кнопка-сердечко `IconButton(bgcolor=...)` | круглый `Container` с иконкой |
| ошибки в диалогах администратора — всплывающее сообщение | сообщение прямо в окне диалога |

Модули `db.py`, `photos.py`, `flowers_data.py` и тесты (`python -m unittest tests.test_db -v`) не менялись.
