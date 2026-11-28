# -*- coding: utf-8 -*-
"""Флора — приложение цветочного магазина (Python + Flet).

Работает на компьютере (Windows / macOS / Linux) и на Android из одного кода.
Запуск:  python main.py
"""
import asyncio
import base64
import os
from datetime import datetime, timedelta
from pathlib import Path

import flet as ft

import db
import photos
from flowers_data import CATEGORIES, CATEGORY_EMOJI

SHOP_NAME = "Флора"
SHOP_INFO = "Цветочный магазин «Флора» · ул. Цветочная, 1 · ежедневно 9:00–20:00"
PINK = ft.Colors.PINK_400
RED = ft.Colors.RED_600
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
STATUS_COLORS = {
    "Новый": ft.Colors.BLUE_600,
    "В работе": ft.Colors.ORANGE_700,
    "Готов": ft.Colors.GREEN_600,
    "Завершён": ft.Colors.GREY_600,
    "Отменён": ft.Colors.RED_500,
}
NEXT_STATUS = {
    "Новый": ("В работе", "Взять в работу"),
    "В работе": ("Готов", "Заказ готов"),
    "Готов": ("Завершён", "Выдан / доставлен"),
}
# прозрачный пиксель-заглушка (пока фото не найдено)
BLANK_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def storage_dir():
    env = os.environ.get("FLET_APP_STORAGE_DATA")  # на Android — папка приложения
    base = Path(env) if env else Path(__file__).resolve().parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def fmt_dt(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
    except Exception:
        return s


def chip(text, color):
    return ft.Container(
        content=ft.Text(text, size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
        bgcolor=color, padding=ft.Padding.symmetric(horizontal=8, vertical=2), border_radius=10,
    )


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.user = None
        self.cart = {}          # {flower_id: qty}
        self.imgs = {}          # {flower_id: [Image, ...]} — чтобы подставить фото, когда они найдутся
        self.q, self.cat, self.sort = "", "Все", "name"
        self.tab = 0
        self.admin_status = "Все"
        self.admin_q = ""
        self.promo_applied = ""
        self.reset_form()

        page.title = SHOP_NAME
        page.theme = ft.Theme(color_scheme_seed=ft.Colors.PINK)
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        try:
            page.window.width = 1000
            page.window.height = 780
            page.window.min_width = 360
            page.window.min_height = 600
        except Exception:
            pass

        self.show_login()
        page.run_task(self.load_photos)

    # ------------------------------------------------------------ утилиты
    def pw(self):
        return self.page.width or 400

    def dw(self):
        return int(min(460, self.pw() - 80))

    def snack(self, text, error=False):
        self.page.show_dialog(ft.SnackBar(content=ft.Text(text), bgcolor=RED if error else None))

    def dialog(self, title, content, actions):
        dlg = ft.AlertDialog(modal=True, title=ft.Text(title), content=content, actions=actions,
                             actions_alignment=ft.MainAxisAlignment.END)
        self.page.show_dialog(dlg)
        return dlg

    def close(self, dlg):
        self.page.pop_dialog()

    def reset_form(self):
        phone = self.user["phone"] if self.user else ""
        self.f = {"method": "Самовывоз", "address": "", "date": None, "time": None,
                  "phone": phone, "comment": "", "promo": ""}
        self.promo_applied = ""

    # ------------------------------------------------------------ фотографии
    async def load_photos(self):
        """Ищет ссылки на фото в интернете. Сетевой запрос уходит в отдельный поток,
        чтобы не блокировать интерфейс (во Flet 1.0 всё остальное работает в одном потоке)."""
        try:
            missing = [f for f in db.list_flowers() if not f["photo_url"]]
            if not missing:
                return
            urls = await asyncio.to_thread(photos.fetch_photo_urls, [f["wiki"] for f in missing])
            for f in missing:
                u = urls.get(f["wiki"])
                if u:
                    db.set_photo_url(f["id"], u)
            self.refresh_images()
        except Exception as e:  # нет интернета — останутся значки-заглушки
            print("Не удалось загрузить фото:", e)

    def refresh_images(self):
        for fid, imgs in list(self.imgs.items()):
            fl = db.get_flower(fid)
            if not fl or not fl["photo_url"]:
                continue
            for img in imgs:
                try:
                    img.src = fl["photo_url"]
                    img.visible = True
                except Exception:
                    pass
        try:
            self.page.update()
        except Exception:
            pass

    def photo(self, fl, height, width=None, radius=12, extra=None):
        """Фото цветка: под ним — значок-заглушка, поверх — картинка из интернета."""
        tint = ft.Container(
            content=ft.Text(CATEGORY_EMOJI.get(fl["category"], "🌸"), size=max(16, int(height * 0.4))),
            alignment=ft.Alignment.CENTER, bgcolor=ft.Colors.with_opacity(0.12, PINK),
            left=0, top=0, right=0, bottom=0,
        )
        if fl["photo_url"]:
            img = ft.Image(src=fl["photo_url"], fit=ft.BoxFit.COVER, left=0, top=0, right=0, bottom=0)
        else:
            img = ft.Image(src=BLANK_PNG, fit=ft.BoxFit.COVER, visible=False,
                           left=0, top=0, right=0, bottom=0)
        self.imgs.setdefault(fl["id"], []).append(img)
        return ft.Container(
            height=height, width=width, border_radius=radius, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Stack(controls=[tint, img] + (extra or []), expand=True),
        )

    # ------------------------------------------------------------ вход / регистрация
    def show_login(self):
        p = self.page
        p.controls.clear()
        p.appbar = None
        p.navigation_bar = None
        self.user = None
        self.cart = {}
        self.reset_form()
        mode = {"reg": False}

        name = ft.TextField(label="Ваше имя", visible=False, prefix_icon=ft.Icons.BADGE)
        phone = ft.TextField(label="Телефон", visible=False, prefix_icon=ft.Icons.PHONE,
                             keyboard_type=ft.KeyboardType.PHONE)
        login = ft.TextField(label="Логин", prefix_icon=ft.Icons.PERSON)
        pwd = ft.TextField(label="Пароль", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK)
        err = ft.Text("", color=RED, size=13)
        btn = ft.Button(content="Войти", icon=ft.Icons.LOGIN, height=48, bgcolor=PINK, color=ft.Colors.WHITE)
        switch = ft.TextButton(content="Нет аккаунта? Зарегистрироваться")

        def refresh():
            r = mode["reg"]
            name.visible = phone.visible = r
            btn.content = "Зарегистрироваться" if r else "Войти"
            switch.content = "Уже есть аккаунт? Войти" if r else "Нет аккаунта? Зарегистрироваться"
            err.value = ""
            p.update()

        def toggle(e):
            mode["reg"] = not mode["reg"]
            refresh()

        def submit(e):
            try:
                if mode["reg"]:
                    user = db.create_user(login.value or "", pwd.value or "", name.value or "", phone.value or "")
                else:
                    user = db.authenticate(login.value or "", pwd.value or "")
                    if not user:
                        raise ValueError("Неверный логин или пароль")
            except ValueError as ex:
                err.value = str(ex)
                p.update()
                return
            self.user = user
            self.reset_form()
            self.show_main()

        btn.on_click = submit
        switch.on_click = toggle
        pwd.on_submit = submit

        w = int(min(380, self.pw() - 40))
        card = ft.Column(controls=[
                ft.Text("🌸", size=64),
                ft.Text(SHOP_NAME, size=34, weight=ft.FontWeight.BOLD, color=PINK),
                ft.Text("Свежие цветы с доставкой и самовывозом", size=14, color=ft.Colors.GREY_700,
                        text_align=ft.TextAlign.CENTER),
                ft.Container(height=10),
                name, phone, login, pwd, err, btn, switch,
                ft.Text("Администратор: admin / admin123", size=12, color=ft.Colors.GREY_500),
            ],
            width=w, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10,
        )
        p.add(ft.SafeArea(content=ft.Container(
            content=ft.Column(controls=[card], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.CENTER,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.Alignment.CENTER, expand=True, padding=20), expand=True))
        p.update()

    # ------------------------------------------------------------ каркас после входа
    def show_main(self):
        p = self.page
        p.controls.clear()
        self.tab = 0
        self.admin_status = "Все"
        if self.user["role"] == "admin":
            dests = [("Заказы", ft.Icons.RECEIPT_LONG), ("Цветы", ft.Icons.INVENTORY_2),
                     ("Статистика", ft.Icons.BAR_CHART), ("Профиль", ft.Icons.PERSON)]
        else:
            dests = [("Каталог", ft.Icons.LOCAL_FLORIST), ("Избранное", ft.Icons.FAVORITE),
                     ("Корзина", ft.Icons.SHOPPING_CART), ("Заказы", ft.Icons.RECEIPT_LONG),
                     ("Профиль", ft.Icons.PERSON)]
        self.titles = [d[0] for d in dests]
        self.nav = ft.NavigationBar(
            destinations=[ft.NavigationBarDestination(icon=i, label=l) for l, i in dests],
            selected_index=0, on_change=lambda e: self.go(e.control.selected_index),
        )
        p.navigation_bar = self.nav
        self.body = ft.Container(expand=True, padding=ft.Padding.symmetric(horizontal=12))
        p.add(self.body)
        self.go(0)

    def go(self, i):
        self.tab = i
        admin = self.user["role"] == "admin"
        views = (
            [self.view_admin_orders, self.view_admin_flowers, self.view_admin_stats, self.view_profile]
            if admin else
            [lambda: self.view_catalog(False), lambda: self.view_catalog(True), self.view_cart,
             self.view_my_orders, self.view_profile]
        )
        self.page.appbar = ft.AppBar(
            title=ft.Text(("🌸 " + SHOP_NAME + " · " if not admin else "🌸 Админ · ") + self.titles[i],
                          weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.with_opacity(0.10, PINK), center_title=False)
        self.body.content = views[i]()
        self.nav.selected_index = i
        self.update_cart_badge()
        self.page.update()

    def update_cart_badge(self):
        if self.user and self.user["role"] != "admin":
            n = sum(self.cart.values())
            self.nav.destinations[2].label = "Корзина (%d)" % n if n else "Корзина"
            try:
                self.nav.update()
            except Exception:
                pass

    # ------------------------------------------------------------ каталог
    def view_catalog(self, fav_only):
        self.imgs.clear()
        uid = self.user["id"]
        grid = ft.GridView(expand=True, max_extent=210, child_aspect_ratio=0.66, spacing=10, run_spacing=10,
                           padding=ft.Padding.only(bottom=12))
        empty = ft.Text("Ничего не найдено", color=ft.Colors.GREY_600, visible=False)

        def fill(update=True):
            favs = db.fav_ids(uid)
            items = db.list_flowers(self.q, self.cat, self.sort, uid if fav_only else None)
            grid.controls = [self.card(fl, fl["id"] in favs, on_fav) for fl in items]
            empty.value = ("В избранном пока пусто — нажмите ♥ на понравившемся цветке"
                           if fav_only and not (self.q or self.cat != "Все") else "Ничего не найдено")
            empty.visible = not items
            if update:
                self.page.update()

        def on_fav(fid, ctrl):
            now_fav = db.toggle_fav(uid, fid)
            if fav_only:
                fill()
            else:
                ctrl.content.icon = ft.Icons.FAVORITE if now_fav else ft.Icons.FAVORITE_BORDER
                ctrl.update()

        def on_search(e):
            self.q = e.control.value or ""
            fill()

        def on_cat(e):
            self.cat = e.control.value
            fill()

        def on_sort(e):
            self.sort = e.control.value
            fill()

        search = ft.TextField(label="Поиск цветка", prefix_icon=ft.Icons.SEARCH, value=self.q, dense=True,
                              on_change=on_search)
        cat = ft.Dropdown(label="Категория", value=self.cat, dense=True, expand=True, on_select=on_cat,
                          options=[ft.DropdownOption(key="Все", text="Все")] + [ft.DropdownOption(key=c, text=c) for c in CATEGORIES])
        sort = ft.Dropdown(label="Сортировка", value=self.sort, dense=True, expand=True, on_select=on_sort,
                           options=[ft.DropdownOption("name", "По названию"),
                                    ft.DropdownOption("price_asc", "Сначала дешёвые"),
                                    ft.DropdownOption("price_desc", "Сначала дорогие"),
                                    ft.DropdownOption("stock", "Сначала в наличии")])
        fill(update=False)
        return ft.Column(controls=[ft.Container(height=4), search, ft.Row(controls=[cat, sort], spacing=8), empty, grid],
                         expand=True, spacing=8)

    def card(self, fl, is_fav, on_fav):
        out = fl["stock"] <= 0
        heart = ft.Container(
            content=ft.Icon(icon=ft.Icons.FAVORITE if is_fav else ft.Icons.FAVORITE_BORDER, color=PINK, size=20),
            width=34, height=34, border_radius=17, alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE),
            on_click=lambda e, fid=fl["id"]: on_fav(fid, e.control))
        heart_box = ft.Container(content=heart, right=2, top=2)
        if out:
            stock = ft.Text("Нет в наличии", size=12, color=RED, weight=ft.FontWeight.BOLD)
        else:
            stock = ft.Text("В наличии: %d шт." % fl["stock"], size=12,
                            color=ft.Colors.GREEN_700 if fl["stock"] > 5 else ft.Colors.ORANGE_800)
        return ft.Container(
            content=ft.Column(controls=[
                    self.photo(fl, 125, radius=10, extra=[heart_box]),
                    ft.Text(fl["name"], size=14, weight=ft.FontWeight.BOLD, max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(fl["category"], size=11, color=ft.Colors.GREY_600),
                    ft.Text("%d ₽" % fl["price"], size=18, weight=ft.FontWeight.BOLD, color=PINK),
                    stock,
                ],
                spacing=3, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=8, border_radius=14, ink=True, opacity=0.65 if out else 1,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            on_click=lambda e, fid=fl["id"]: self.open_detail(fid),
        )

    def info_row(self, icon, label, value):
        return ft.Row(controls=[ft.Icon(icon=icon, size=20, color=PINK),
             ft.Column(controls=[ft.Text(label, size=11, color=ft.Colors.GREY_600),
                        ft.Text(value or "—", size=14)], spacing=0, expand=True)],
            vertical_alignment=ft.CrossAxisAlignment.START, spacing=10)

    def open_detail(self, fid):
        fl = db.get_flower(fid)
        in_cart = self.cart.get(fid, 0)
        avail = fl["stock"] - in_cart
        qty = {"v": 1}
        qty_txt = ft.Text("1", size=18, weight=ft.FontWeight.BOLD)

        def change(d):
            qty["v"] = max(1, min(avail, qty["v"] + d))
            qty_txt.value = str(qty["v"])
            qty_txt.update()

        if fl["stock"] <= 0:
            status = chip("Нет в наличии", RED)
        elif avail <= 0:
            status = chip("Весь остаток уже в корзине", ft.Colors.ORANGE_700)
        else:
            status = chip("В наличии: %d шт." % fl["stock"], ft.Colors.GREEN_600)

        stepper = ft.Row(controls=[ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, on_click=lambda e: change(-1)), qty_txt,
             ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda e: change(1))],
            alignment=ft.MainAxisAlignment.CENTER, visible=avail > 0)

        w = self.dw()
        content = ft.Container(
            width=w, height=int(min(560, (self.page.height or 700) * 0.62)),
            content=ft.Column(controls=[
                    self.photo(fl, 200, radius=12),
                    ft.Text(fl["latin"], italic=True, color=ft.Colors.GREY_700),
                    ft.Row(controls=[chip(fl["category"], ft.Colors.PINK_300), status], wrap=True),
                    ft.Text("%d ₽" % fl["price"], size=26, weight=ft.FontWeight.BOLD, color=PINK),
                    ft.Text("Средняя цена за стебель / горшок / ветку", size=11, color=ft.Colors.GREY_600),
                    ft.Divider(),
                    self.info_row(ft.Icons.GRASS, "Почва", fl["soil"]),
                    self.info_row(ft.Icons.ECO, "Чем подкармливать", fl["feeding"]),
                    self.info_row(ft.Icons.CALENDAR_MONTH, "Период цветения", fl["bloom"]),
                    self.info_row(ft.Icons.HEIGHT, "Высота растения", fl["height"]),
                    self.info_row(ft.Icons.WB_SUNNY, "Освещение", fl["light"]),
                    self.info_row(ft.Icons.WATER_DROP, "Полив", fl["watering"]),
                    self.info_row(ft.Icons.LOCAL_FLORIST, "Сколько стоит в вазе", fl["vase"]),
                    self.info_row(ft.Icons.FAVORITE, "Что символизирует", fl["meaning"]),
                    self.info_row(ft.Icons.LIGHTBULB, "Интересный факт", fl["fact"]),
                    ft.Text("Фото: Wikipedia / Wikimedia Commons", size=10, color=ft.Colors.GREY_500),
                    stepper,
                ],
                scroll=ft.ScrollMode.AUTO, spacing=8),
        )

        def add(e):
            self.cart[fid] = in_cart + qty["v"]
            self.close(dlg)
            self.update_cart_badge()
            self.snack("«%s» × %d добавлено в корзину" % (fl["name"], qty["v"]))

        actions = [ft.TextButton(content="Закрыть", on_click=lambda e: self.close(dlg))]
        actions.append(ft.Button(content="В корзину", icon=ft.Icons.ADD_SHOPPING_CART, on_click=add,
                                         disabled=avail <= 0, bgcolor=PINK, color=ft.Colors.WHITE))
        dlg = self.dialog(fl["name"], content, actions)

    # ------------------------------------------------------------ корзина и оформление
    def cart_sum(self):
        s = 0
        for fid, q in self.cart.items():
            s += db.get_flower(fid)["price"] * q
        return s

    def cart_change(self, fid, delta):
        fl = db.get_flower(fid)
        new = self.cart.get(fid, 0) + delta
        if new <= 0:
            self.cart.pop(fid, None)
        elif new > fl["stock"]:
            self.snack("В наличии только %d шт." % fl["stock"], error=True)
            return
        else:
            self.cart[fid] = new
        self.go(2)

    def date_options(self):
        today = datetime.now().date()
        opts = []
        for i in range(14):
            d = today + timedelta(days=i)
            label = "Сегодня" if i == 0 else "Завтра" if i == 1 else WEEKDAYS[d.weekday()]
            opts.append(ft.DropdownOption(d.isoformat(), "%s, %s" % (label, d.strftime("%d.%m"))))
        return opts

    def time_slots(self, date_iso):
        if not date_iso:
            return []
        earliest = datetime.now() + timedelta(minutes=60)
        slots = []
        for h in range(9, 20):
            for m in (0, 30):
                t = "%02d:%02d" % (h, m)
                if datetime.strptime("%s %s" % (date_iso, t), "%Y-%m-%d %H:%M") >= earliest:
                    slots.append(t)
        return slots

    def view_cart(self):
        self.imgs.clear()
        for fid in list(self.cart):  # склад мог измениться
            fl = db.get_flower(fid)
            if not fl or fl["stock"] <= 0:
                del self.cart[fid]
            else:
                self.cart[fid] = min(self.cart[fid], fl["stock"])
        self.update_cart_badge()
        if not self.cart:
            return ft.Column(controls=[ft.Text("🛒", size=64), ft.Text("Корзина пуста", size=20, weight=ft.FontWeight.BOLD),
                 ft.Text("Выберите цветы в каталоге", color=ft.Colors.GREY_600),
                 ft.Button(content="Перейти в каталог", on_click=lambda e: self.go(0))],
                alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True)

        f = self.f
        rows = []
        for fid, qty in self.cart.items():
            fl = db.get_flower(fid)
            rows.append(ft.Container(
                content=ft.Row(controls=[
                    self.photo(fl, 60, 60, radius=8),
                    ft.Column(controls=[ft.Text(fl["name"], weight=ft.FontWeight.BOLD, max_lines=1,
                                       overflow=ft.TextOverflow.ELLIPSIS),
                               ft.Text("%d ₽ × %d = %d ₽" % (fl["price"], qty, fl["price"] * qty), size=12)],
                              spacing=2, expand=True),
                    ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=22,
                                  on_click=lambda e, i=fid: self.cart_change(i, -1)),
                    ft.Text(str(qty), weight=ft.FontWeight.BOLD),
                    ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_size=22,
                                  on_click=lambda e, i=fid: self.cart_change(i, 1)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, icon_size=22,
                                  on_click=lambda e, i=fid: self.cart_change(i, -999)),
                ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=8, border_radius=12, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)))

        # --- форма заказа
        def set_method(e):
            f["method"] = e.control.value
            self.go(2)

        def on_date(e):
            f["date"] = e.control.value
            if f["time"] not in self.time_slots(f["date"]):
                f["time"] = None
            self.go(2)

        def on_time(e):
            f["time"] = e.control.value

        def on_text(key):
            def h(e):
                f[key] = e.control.value or ""
            return h

        def apply_promo(e):
            code = (f["promo"] or "").strip().upper()
            if code in db.PROMOS:
                self.promo_applied = code
                self.snack("Промокод применён: −%d%%" % db.PROMOS[code])
            else:
                self.promo_applied = ""
                self.snack("Такого промокода нет", error=True)
            self.go(2)

        slots = self.time_slots(f["date"])
        delivery = f["method"] == "Доставка"
        t = db.calc_totals(self.cart_sum(), f["method"], self.promo_applied)

        method = ft.RadioGroup(
            value=f["method"], on_change=set_method,
            content=ft.Row(controls=[ft.Radio(value="Самовывоз", label="Самовывоз"),
                            ft.Radio(value="Доставка", label="Доставка")], wrap=True))
        address = ft.TextField(label="Адрес доставки", value=f["address"], on_change=on_text("address"),
                               visible=delivery, prefix_icon=ft.Icons.HOME, dense=True)
        date_dd = ft.Dropdown(label="Дата доставки" if delivery else "Дата самовывоза", value=f["date"],
                              options=self.date_options(), on_select=on_date, expand=True, dense=True)
        time_dd = ft.Dropdown(label="Время", value=f["time"], on_select=on_time, expand=True, dense=True,
                              options=[ft.DropdownOption(key=t, text=t) for t in slots],
                              disabled=not f["date"], hint_text="Сначала дата")
        phone = ft.TextField(label="Телефон", value=f["phone"], on_change=on_text("phone"), dense=True,
                             prefix_icon=ft.Icons.PHONE, keyboard_type=ft.KeyboardType.PHONE)
        comment = ft.TextField(label="Комментарий (открытка, пожелания)", value=f["comment"],
                               on_change=on_text("comment"), dense=True, multiline=True, min_lines=1, max_lines=3)
        promo = ft.TextField(label="Промокод", value=f["promo"], on_change=on_text("promo"), dense=True,
                             expand=True, prefix_icon=ft.Icons.SELL)

        def totals_row(label, value, bold=False, color=None):
            st = dict(weight=ft.FontWeight.BOLD, size=18) if bold else dict(size=14)
            return ft.Row(controls=[ft.Text(label, **st), ft.Text(value, color=color, **st)],
                          alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        summary = [totals_row("Цветы", "%d ₽" % t["subtotal"])]
        if t["discount"]:
            summary.append(totals_row("Скидка %d%% (%s)" % (t["percent"], self.promo_applied),
                                      "−%d ₽" % t["discount"], color=ft.Colors.GREEN_700))
        if delivery:
            summary.append(totals_row("Доставка" + (" (бесплатно от %d ₽)" % db.FREE_DELIVERY_FROM
                                                    if not t["delivery"] else ""), "%d ₽" % t["delivery"]))
        summary.append(ft.Divider())
        summary.append(totals_row("Итого", "%d ₽" % t["total"], bold=True, color=PINK))

        if not delivery:
            rows_info = ft.Text("Заберите заказ: " + SHOP_INFO, size=12, color=ft.Colors.GREY_700)
        else:
            rows_info = ft.Text("Доставка по городу — %d ₽, бесплатно при заказе от %d ₽"
                                % (db.DELIVERY_FEE, db.FREE_DELIVERY_FROM), size=12, color=ft.Colors.GREY_700)

        controls = rows + [
            ft.Container(height=4),
            ft.Text("Оформление заказа", size=18, weight=ft.FontWeight.BOLD),
            method, rows_info, address,
            ft.Row(controls=[date_dd, time_dd], spacing=8),
            phone, comment,
            ft.Row(controls=[promo, ft.OutlinedButton(content="Применить", on_click=apply_promo)], spacing=8),
            ft.Container(content=ft.Column(controls=summary, spacing=4), padding=12, border_radius=12,
                         bgcolor=ft.Colors.with_opacity(0.06, PINK)),
            ft.Button(content="Оформить заказ", icon=ft.Icons.CHECK, height=50, bgcolor=PINK,
                              color=ft.Colors.WHITE, on_click=self.checkout),
            ft.Container(height=16),
        ]
        return ft.ListView(controls=controls, expand=True, spacing=10, padding=ft.Padding.only(top=8))

    def checkout(self, e):
        f = self.f
        digits = "".join(c for c in (f["phone"] or "") if c.isdigit())
        if len(digits) < 10:
            return self.snack("Укажите телефон для связи", error=True)
        if f["method"] == "Доставка" and len((f["address"] or "").strip()) < 5:
            return self.snack("Укажите адрес доставки", error=True)
        if not f["date"] or not f["time"]:
            return self.snack("Выберите дату и время", error=True)
        when = datetime.strptime("%s %s" % (f["date"], f["time"]), "%Y-%m-%d %H:%M")
        if when < datetime.now() + timedelta(minutes=45):
            return self.snack("На выбранное время мы уже не успеем — выберите позже", error=True)
        try:
            oid = db.place_order(self.user["id"], dict(self.cart), f["method"], (f["address"] or "").strip(),
                                 when, f["phone"].strip(), (f["comment"] or "").strip(), self.promo_applied)
        except ValueError as ex:
            self.snack(str(ex), error=True)
            return self.go(2)
        if not self.user["phone"]:
            db.update_profile(self.user["id"], self.user["full_name"], f["phone"])
            self.user["phone"] = f["phone"]
        method, when_s = f["method"], when.strftime("%d.%m.%Y в %H:%M")
        self.cart = {}
        self.reset_form()
        self.go(3)
        dlg = None

        def ok(ev):
            self.close(dlg)

        dlg = self.dialog(
            "Заказ №%d оформлен 🎉" % oid,
            ft.Text("%s: %s.\nСтатус заказа можно отслеживать во вкладке «Заказы»." % (method, when_s)),
            [ft.Button(content="Отлично", on_click=ok)])

    # ------------------------------------------------------------ карточка заказа
    def order_card(self, o, admin=False):
        color = STATUS_COLORS[o["status"]]
        lines = [ft.Text("• %s × %d — %d ₽" % (i["name"], i["qty"], i["price"] * i["qty"]), size=13)
                 for i in o["items"]]
        when = fmt_dt(o["when_dt"])
        overdue = admin and o["status"] in db.ACTIVE_STATUSES and o["when_dt"] < datetime.now().strftime("%Y-%m-%d %H:%M")
        head = ft.Row(controls=[ft.Text("Заказ №%d" % o["id"], size=16, weight=ft.FontWeight.BOLD),
                       chip(o["status"], color)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        col = [head]
        if admin:
            col.append(ft.Text("👤 %s (%s) · 📞 %s" % (o["customer"] or o["login"], o["login"], o["phone"]), size=13))
        icon = "🚚" if o["method"] == "Доставка" else "🏪"
        col.append(ft.Text("%s %s · %s" % (icon, o["method"], when) + ("  ⚠ просрочен" if overdue else ""),
                           size=13, weight=ft.FontWeight.W_500, color=RED if overdue else None))
        if o["address"]:
            col.append(ft.Text("📍 " + o["address"], size=13))
        col += lines
        if o["comment"]:
            col.append(ft.Text("💬 " + o["comment"], size=13, italic=True))
        price = "Итого: %d ₽" % o["total"]
        if o["discount"]:
            price += "  (скидка %d ₽)" % o["discount"]
        col.append(ft.Text(price, weight=ft.FontWeight.BOLD, color=PINK))
        col.append(ft.Text("Создан: " + fmt_dt(o["created"]), size=11, color=ft.Colors.GREY_600))

        btns = []
        if admin and o["status"] in NEXT_STATUS:
            ns, label = NEXT_STATUS[o["status"]]
            btns.append(ft.Button(content=label, bgcolor=STATUS_COLORS[ns], color=ft.Colors.WHITE,
                                          on_click=lambda e, i=o["id"], s=ns: self.change_status(i, s)))
        if o["status"] in db.ACTIVE_STATUSES and (admin or o["status"] == "Новый"):
            btns.append(ft.OutlinedButton(content="Отменить заказ", style=ft.ButtonStyle(color=RED),
                                          on_click=lambda e, i=o["id"]: self.confirm_cancel(i)))
        if btns:
            col.append(ft.Row(controls=btns, wrap=True, spacing=8))
        return ft.Container(content=ft.Column(controls=col, spacing=4), padding=12, border_radius=14,
                            border=ft.Border.all(1, color))

    def confirm_cancel(self, oid):
        dlg = None

        def yes(e):
            self.close(dlg)
            self.change_status(oid, "Отменён")

        dlg = self.dialog("Отменить заказ №%d?" % oid, ft.Text("Товар вернётся на склад."),
                          [ft.TextButton(content="Нет", on_click=lambda e: self.close(dlg)),
                           ft.Button(content="Да, отменить", on_click=yes, bgcolor=RED, color=ft.Colors.WHITE)])

    def change_status(self, oid, status):
        try:
            db.set_order_status(oid, status)
            self.snack("Заказ №%d: %s" % (oid, status))
        except ValueError as ex:
            self.snack(str(ex), error=True)
        self.go(self.tab)

    # ------------------------------------------------------------ заказы покупателя
    def view_my_orders(self):
        orders = sorted(db.list_orders(user_id=self.user["id"]), key=lambda o: -o["id"])
        if not orders:
            return ft.Column(controls=[ft.Text("📦", size=60), ft.Text("Заказов пока нет", size=18, weight=ft.FontWeight.BOLD)],
                             alignment=ft.MainAxisAlignment.CENTER,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        return ft.ListView(controls=[self.order_card(o) for o in orders], expand=True, spacing=10,
                           padding=ft.Padding.symmetric(vertical=8))

    # ------------------------------------------------------------ профиль
    def view_profile(self):
        u = self.user
        name = ft.TextField(label="Имя", value=u["full_name"], dense=True)
        phone = ft.TextField(label="Телефон", value=u["phone"], dense=True, keyboard_type=ft.KeyboardType.PHONE)

        def save(e):
            db.update_profile(u["id"], name.value or "", phone.value or "")
            u["full_name"], u["phone"] = name.value or "", phone.value or ""
            self.f["phone"] = u["phone"]
            self.snack("Профиль сохранён")

        col = [
            ft.Container(height=8),
            ft.Row(controls=[ft.CircleAvatar(content=ft.Text("🌸", size=26), radius=30,
                                    bgcolor=ft.Colors.with_opacity(0.15, PINK)),
                    ft.Column(controls=[ft.Text(u["full_name"] or u["username"], size=20, weight=ft.FontWeight.BOLD),
                               ft.Text("Логин: %s · %s" % (u["username"],
                                                          "администратор" if u["role"] == "admin" else "покупатель"),
                                       size=12, color=ft.Colors.GREY_700)], spacing=0)], spacing=14),
        ]
        if u["role"] != "admin":
            col += [name, phone, ft.OutlinedButton(content="Сохранить", icon=ft.Icons.SAVE, on_click=save),
                    ft.Divider(),
                    ft.Text("Промокоды: SPRING10 (−10%), FLORA15 (−15%), HELLO5 (−5%)", size=13),
                    ft.Text("Бесплатная доставка при заказе от %d ₽" % db.FREE_DELIVERY_FROM, size=13)]
        col += [ft.Text(SHOP_INFO, size=12, color=ft.Colors.GREY_600),
                ft.Button(content="Выйти", icon=ft.Icons.LOGOUT, bgcolor=RED, color=ft.Colors.WHITE,
                                  on_click=lambda e: self.show_login())]
        return ft.ListView(controls=col, expand=True, spacing=12)

    # ------------------------------------------------------------ АДМИН: заказы
    def view_admin_orders(self):
        orders = db.list_orders(status=self.admin_status)
        active = sorted([o for o in orders if o["status"] in db.ACTIVE_STATUSES], key=lambda o: o["when_dt"])
        closed = sorted([o for o in orders if o["status"] not in db.ACTIVE_STATUSES], key=lambda o: -o["id"])
        counts = {s: len(db.list_orders(status=s)) for s in db.STATUSES}

        def on_filter(e):
            self.admin_status = e.control.value
            self.go(0)

        dd = ft.Dropdown(
            label="Фильтр по статусу", value=self.admin_status, dense=True, on_select=on_filter,
            options=[ft.DropdownOption(key="Все", text="Все")] + [ft.DropdownOption(s, "%s (%d)" % (s, counts[s]))
                                                    for s in db.STATUSES])
        items = []
        if active:
            items.append(ft.Text("Текущие заказы — по ближайшему времени", weight=ft.FontWeight.BOLD))
            items += [self.order_card(o, True) for o in active]
        if closed:
            items.append(ft.Text("Закрытые", weight=ft.FontWeight.BOLD))
            items += [self.order_card(o, True) for o in closed]
        if not items:
            items.append(ft.Text("Заказов нет", color=ft.Colors.GREY_600))
        return ft.Column(controls=[ft.Container(height=4), dd,
                          ft.ListView(controls=items, expand=True, spacing=10, padding=ft.Padding.only(bottom=12))],
                         expand=True, spacing=8)

    # ------------------------------------------------------------ АДМИН: склад
    def view_admin_flowers(self):
        self.imgs.clear()
        lst = ft.ListView(expand=True, spacing=8, padding=ft.Padding.only(bottom=12))

        def fill(update=True):
            items = db.list_flowers(self.admin_q, "Все", "name")
            lst.controls = [self.admin_flower_row(fl) for fl in items]
            if update:
                self.page.update()

        def on_search(e):
            self.admin_q = e.control.value or ""
            fill()

        def refresh_photos(e):
            self.snack("Ищу фотографии в интернете…")
            self.page.run_task(self.load_photos)

        search = ft.TextField(label="Поиск", prefix_icon=ft.Icons.SEARCH, dense=True, expand=True,
                              value=self.admin_q, on_change=on_search)
        fill(update=False)
        return ft.Column(controls=[
            ft.Container(height=4),
            ft.Row(controls=[search, ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=PINK, icon_size=34,
                                          tooltip="Добавить цветок", on_click=self.add_flower_dialog),
                    ft.IconButton(icon=ft.Icons.IMAGE_SEARCH, tooltip="Найти недостающие фото",
                                  on_click=refresh_photos)]),
            lst], expand=True, spacing=8)

    def admin_flower_row(self, fl):
        low = fl["stock"] <= 5
        stock_txt = ("Нет в наличии" if fl["stock"] <= 0 else "Остаток: %d шт." % fl["stock"])
        return ft.Container(
            content=ft.Row(controls=[self.photo(fl, 52, 52, radius=8),
                    ft.Column(controls=[ft.Text(fl["name"], weight=ft.FontWeight.BOLD, max_lines=1,
                                       overflow=ft.TextOverflow.ELLIPSIS),
                               ft.Row(controls=[ft.Text("%d ₽" % fl["price"], color=PINK, weight=ft.FontWeight.BOLD),
                                       ft.Text(stock_txt, size=12, color=RED if low else ft.Colors.GREEN_700)],
                                      spacing=12)], spacing=2, expand=True),
                    ft.IconButton(icon=ft.Icons.EDIT, tooltip="Изменить",
                                  on_click=lambda e, i=fl["id"]: self.edit_flower_dialog(i))]),
            padding=8, border_radius=12, border=ft.Border.all(1, RED if low else ft.Colors.OUTLINE_VARIANT))

    def edit_flower_dialog(self, fid):
        fl = db.get_flower(fid)
        price = ft.TextField(label="Цена, ₽", value=str(fl["price"]), keyboard_type=ft.KeyboardType.NUMBER)
        stock = ft.TextField(label="Количество на складе", value=str(fl["stock"]),
                             keyboard_type=ft.KeyboardType.NUMBER)
        url = ft.TextField(label="Ссылка на фото (необязательно)", value=fl["photo_url"], multiline=True,
                           max_lines=3)
        err = ft.Text("", color=RED, size=13)
        dlg = None

        def plus(n):
            def h(e):
                try:
                    stock.value = str(int(stock.value or 0) + n)
                except ValueError:
                    stock.value = str(n)
                stock.update()
            return h

        def save(e):
            try:
                p, s = int(price.value), int(stock.value)
                if p < 0 or s < 0:
                    raise ValueError
            except (ValueError, TypeError):
                err.value = "Цена и количество — целые числа ≥ 0"
                self.page.update()
                return
            db.update_flower(fid, p, s, url.value or "")
            self.close(dlg)
            self.snack("Сохранено")
            self.go(1)

        content = ft.Container(width=self.dw(), content=ft.Column(controls=[price, stock, ft.Row(controls=[ft.OutlinedButton(content="+10", on_click=plus(10)),
                                   ft.OutlinedButton(content="+50", on_click=plus(50))], spacing=8), url, err],
            tight=True, scroll=ft.ScrollMode.AUTO))
        dlg = self.dialog(fl["name"], content, [ft.TextButton(content="Отмена", on_click=lambda e: self.close(dlg)),
                                                ft.Button(content="Сохранить", on_click=save)])

    def add_flower_dialog(self, e):
        f = {k: ft.TextField(label=l, dense=True) for k, l in [
            ("name", "Название *"), ("latin", "Латинское название"), ("wiki", "Статья в Википедии (англ.) для фото"),
            ("price", "Цена, ₽ *"), ("stock", "Количество *"), ("soil", "Почва"), ("feeding", "Подкормка"),
            ("bloom", "Период цветения"), ("height", "Высота"), ("light", "Освещение"), ("watering", "Полив")]}
        f["price"].keyboard_type = f["stock"].keyboard_type = ft.KeyboardType.NUMBER
        cat = ft.Dropdown(label="Категория", value=CATEGORIES[0], dense=True,
                          options=[ft.DropdownOption(key=c, text=c) for c in CATEGORIES])
        err = ft.Text("", color=RED, size=13)
        dlg = None

        def save(ev):
            try:
                data = {k: (v.value or "").strip() for k, v in f.items()}
                if not data["name"]:
                    raise ValueError("Введите название")
                data["price"], data["stock"] = int(data["price"]), int(data["stock"])
            except ValueError as ex:
                err.value = str(ex) if "название" in str(ex) else "Цена и количество — целые числа"
                self.page.update()
                return
            data["category"] = cat.value
            data["wiki"] = data["wiki"] or data["name"]
            data["latin"] = data["latin"] or "—"
            data["vase"], data["meaning"], data["fact"] = "—", "—", "—"
            db.add_flower(data)
            self.close(dlg)
            self.page.run_task(self.load_photos)
            self.snack("Цветок добавлен")
            self.go(1)

        content = ft.Container(width=self.dw(), height=int(min(480, (self.page.height or 700) * 0.6)),
                               content=ft.Column(controls=[f["name"], cat] + [f[k] for k in f if k != "name"] + [err],
                                                 scroll=ft.ScrollMode.AUTO, spacing=8))
        dlg = self.dialog("Новый цветок", content, [ft.TextButton(content="Отмена", on_click=lambda e: self.close(dlg)),
                                                    ft.Button(content="Добавить", on_click=save)])

    # ------------------------------------------------------------ АДМИН: статистика
    def view_admin_stats(self):
        s = db.stats()

        def tile(title, value, icon, color):
            return ft.Container(
                content=ft.Column(controls=[ft.Icon(icon=icon, color=color), ft.Text(str(value), size=22, weight=ft.FontWeight.BOLD),
                           ft.Text(title, size=12, color=ft.Colors.GREY_700)], spacing=2),
                padding=12, border_radius=14, width=165, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT))

        tiles = ft.Row(controls=[
            tile("Выручка", "%d ₽" % s["revenue"], ft.Icons.PAYMENTS, ft.Colors.GREEN_600),
            tile("Всего заказов", s["total_orders"], ft.Icons.RECEIPT_LONG, ft.Colors.BLUE_600),
            tile("В работе сейчас", s["active"], ft.Icons.PENDING_ACTIONS, ft.Colors.ORANGE_700),
            tile("Средний чек", "%d ₽" % s["avg"], ft.Icons.TRENDING_UP, PINK),
            tile("Покупателей", s["customers"], ft.Icons.PEOPLE, ft.Colors.PURPLE_400),
            tile("Видов цветов", s["flowers"], ft.Icons.LOCAL_FLORIST, ft.Colors.TEAL_500),
        ], wrap=True, spacing=10, run_spacing=10)

        top_max = max([q for _, q in s["top"]], default=1)
        top = [ft.Text("Самые популярные цветы", size=16, weight=ft.FontWeight.BOLD)]
        if s["top"]:
            for name, q in s["top"]:
                top.append(ft.Column(controls=[ft.Text("%s — %d шт." % (name, q), size=13),
                                      ft.ProgressBar(value=q / top_max, color=PINK, bar_height=8)], spacing=2))
        else:
            top.append(ft.Text("Пока нет продаж", color=ft.Colors.GREY_600))

        by = [ft.Text("Заказы по статусам", size=16, weight=ft.FontWeight.BOLD),
              ft.Row(controls=[chip("%s: %d" % (k, v), STATUS_COLORS[k]) for k, v in s["by_status"].items()],
                     wrap=True, spacing=6, run_spacing=6)]

        low = [ft.Text("Заканчиваются на складе (≤ 5 шт.)", size=16, weight=ft.FontWeight.BOLD)]
        if s["low"]:
            for name, st in s["low"]:
                low.append(ft.Text("• %s — %s" % (name, "нет в наличии" if st <= 0 else "%d шт." % st), size=13,
                                   color=RED if st <= 0 else ft.Colors.ORANGE_800))
        else:
            low.append(ft.Text("Всё в достатке 👍", color=ft.Colors.GREY_600))

        return ft.ListView(controls=[ft.Container(height=4), tiles] + by + top + low + [ft.Container(height=12)],
                           expand=True, spacing=12)


def main(page: ft.Page):
    db.init(str(storage_dir() / "flora.db"))
    App(page)


if __name__ == "__main__":
    ft.run(main)
