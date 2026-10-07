# -*- coding: utf-8 -*-
"""
기회비용 미터 위젯 v5

화면 위에 항상 떠 있는 작은 카운터입니다.
  - 드래그: 이동                 - 더블클릭: 공부 <-> 딴짓 전환
  - 아래 버튼: 공부 / 휴식 / 딴짓 (기록 멈춤은 우클릭 메뉴)
  - 오른쪽 위 -: 작게 보기       - 오른쪽 위 ... 또는 우클릭: 메뉴
  - 알림 창: 공부 체크인, 딴짓 경고, 멈춤 알림, 뽀모도로, 목표 달성, 오늘 결산
  - 메뉴 > 숫자 · 목표 설정: 사용 방식(취업 준비 / 직장인), 회사·연봉, 근무 시간, 목표, D-day, 오늘 기록 고치기
  - 메뉴 > 공부 활동: 켜진 시간 대비 공부 비율 (일별 히트맵 · 주간 · 누적)
설정 파일: %APPDATA%\\OpportunityMeter\\config.json (메뉴 > 설정 파일 열기)
Python 3 기본 라이브러리만 사용합니다.
"""
import ctypes
import datetime as dt
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import tkinter as tk

try:
    import winsound
except ImportError:  # Windows가 아니면 기본 벨 소리
    winsound = None

LAYOUT_VERSION = 2

DEFAULTS = {
    # 사용 방식: "job" 취업 준비 (목표 회사 두 곳의 돈이 하루 종일 쌓임)
    #           "work" 직장인 (내 월급이 근무 시간에만 쌓이고, 목표 회사와 비교)
    "profile": "job",
    # 취업 준비: 목표 회사 두 곳 (연봉 만원, 성과급 억원/년)
    "companies": [
        {"name": "삼성 메모리", "salary_manwon": 8000, "bonus_eok": 7.5},
        {"name": "SK하이닉스", "salary_manwon": 8000, "bonus_eok": 7.53},  # 260조 × 10% ÷ 34,549명
    ],
    "include_salary": True,       # 기본 연봉 포함
    # 성과급 계산기 기본값 (영업이익 × 비율 ÷ 직원 수)
    "hynix_op_jo": 260,
    "hynix_ps_pct": 10,
    "hynix_headcount": 34549,
    # 직장인
    "work_salary_manwon": 4500,   # 내 연봉 (성과급 포함 연간 총액, 만원)
    "work_start": "09:00",
    "work_end": "18:00",
    "work_lunch": "12:00-13:00",  # 비우면 점심시간 없음
    "work_days": "월화수목금",
    "payday": 25,                 # 월급날 (일), 0이면 숨김
    "target_name": "",            # 이직 목표 회사 (비우면 '이번 달 번 돈'을 보여줌)
    "target_manwon": 0,           # 목표 회사 연간 총보상 (연봉 + 성과급, 만원)
    # 세후로 볼 때 실제로 받는 비율 (대략)
    "tax_keep_job": 0.55,         # 성과급이 큰 경우 (실효세율 약 45%)
    "tax_keep_work": 0.8,
    "after_tax": False,
    "basis": "today",             # "today" 오늘 0시부터 / "launch" 위젯 켠 뒤부터
    "min_wage": 10320,            # 2026년 최저시급 (원)
    "fun_items": [                # 놓친 돈 환산: [이름, 단위, 가격(원)] — 가격은 대략
        ["아메리카노", "잔", 4500],
        ["국밥", "그릇", 11000],
        ["치킨", "마리", 23000],
        ["최저시급 알바", "시간", 10320],
    ],
    # 공부
    "daily_goal_h": 6,            # 하루 목표 공부 시간
    "pomodoro": True,             # 집중/휴식 타이머
    "focus_min": 25,              # 메뉴에서 25 / 35 / 45 / 55분 중 선택
    "break_min": 5,
    "sound": True,
    # 알림
    "checkin": "sometimes",       # 공부 체크인: "sometimes" 20~40분 / "often" 10~20분 / "off"
    "checkin_timeout_s": 90,      # 체크인에 이 시간 안에 답이 없으면 그때부터 딴짓으로 기록
    "slack_warn": True,           # 딴짓 5분째부터 10분마다 알림 (세 번 연속 무응답이면 기록 멈춤)
    "idle_nudge": True,           # 멈춤이 오래되면 알림
    "idle_nudge_min": 60,
    "active_hours": [9, 23],      # 멈춤 알림을 보내는 시간대 (시작시, 끝시)
    "summary_at": "23:00",        # 오늘 결산 알림 시각 (HH:MM), 비우면 끔
    # 화면
    "money_fx": True,             # 공부 중 +원, 딴짓 중 -원이 떠오르는 효과
    "slack_alert": "strong",      # 딴짓할 때 위젯: "strong" 빨간 깜빡임+흔들림 / "normal" 깜빡임 / "off"
    "dday_label": "",             # 예: "졸업"
    "dday_date": "",              # 예: "2027-08-31", 비우면 숨김
    "mini": False,
    "topmost": True,
    "alpha": 0.95,
    "x": None,
    "y": None,
    "layout_v": LAYOUT_VERSION,
}

YEAR_SEC = 365 * 24 * 3600
KINDS = ("study", "break", "slack")
STORE = KINDS + ("on",)  # on = 위젯이 켜져 있던 시간 (절전·잠자기 제외)
FOCUS_CHOICES = (25, 35, 45, 55)  # 뽀모도로 집중 시간 선택지 (분)
CHECKIN_RANGES = {"sometimes": (20, 40), "often": (10, 20)}  # 체크인 간격 (분, 무작위)
HIST_DAYS = 400

# ---------- 색 ----------
KEY = "#010203"      # 투명 처리용
BG = "#17140e"
PANEL = "#221e16"
PANEL_H = "#2e291f"
LINE = "#3a3322"
DIM = "#6d6453"
MUTED = "#a89a78"
FG = "#f6ecd2"
DARK = "#15120c"
SAM = "#7b97ff"
HYN = "#ff7a4f"
GOOD = "#5fcf86"
REST = "#6cc3d5"
BAD = "#ff6b5b"
GOLD = "#f2c14e"

STATE_COLOR = {"study": GOOD, "break": REST, "slack": BAD, "idle": MUTED}

# 공부 비율 히트맵: 보라 한 색 계열 4단계 (어두운 바탕에서 단계 구분·대비 검증함)
HEAT = ("#53408b", "#7057ba", "#8d73e0", "#b09ef9")
HEAT_EMPTY = "#2a2519"
HEAT_BINS = (0.2, 0.4, 0.6)  # 0~20% / 20~40% / 40~60% / 60% 이상
TIP_BG = "#0d0b07"

# 딴짓 경고 모드
ALERT_DARK = "#5a0f12"
ALERT_HOT = "#c62828"
ALERT_TEXT = "#fff3f1"
ALERT_SOFT = "#ffcdc8"
ALERT_LINE = "#ff8a80"

UI = "Malgun Gothic"
MONO = "Consolas"

FULL = (340, 200)   # 96dpi 기준 크기. 화면 배율에 맞춰 자동으로 커짐
MINI = (236, 40)

APPDIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "OpportunityMeter")
CFG = os.path.join(APPDIR, "config.json")
LOG = os.path.join(APPDIR, "today.json")
HIST = os.path.join(APPDIR, "history.json")
STARTUP = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                       "OpportunityMeter.cmd")


# ---------- 도우미 ----------
def load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else fallback
    except Exception:
        return fallback


def save_json(path, data):
    try:
        os.makedirs(APPDIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def today_str():
    return dt.date.today().isoformat()


def new_log():
    return {"day": today_str(), "study": 0.0, "break": 0.0, "slack": 0.0, "on": 0.0,
            "goal_done": False, "summary_done": False}


def won(v):
    return f"{v:,.0f}원"


def won0(v):
    return f"{v:,.0f}원"


def man(v):
    if v >= 1e8:
        return f"{v / 1e8:.2f}억원"
    if v >= 1e4:
        return f"{v / 1e4:,.1f}만원"
    return f"{v:,.0f}원"


def hms(s):
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def hm(s):
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}"


def mmss(s):
    s = int(max(0, s))
    return f"{s // 60:02d}:{s % 60:02d}"


def dur(s):
    m = int(max(0, s) // 60)
    if m >= 60:
        return f"{m // 60}시간 {m % 60}분" if m % 60 else f"{m // 60}시간"
    return f"{m}분"


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def num(cfg, key):
    try:
        return float(cfg[key])
    except (KeyError, TypeError, ValueError):
        return float(DEFAULTS[key])


def fmt_val(v):
    if isinstance(v, bool) or v is None:
        return ""
    if isinstance(v, (int, float)):
        return f"{v:g}"
    return str(v)


class Meter:
    def __init__(self):
        try:  # 고해상도 모니터에서 글자를 선명하게
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        self.first_run = not os.path.exists(CFG)
        loaded = load_json(CFG, {})
        if loaded.get("layout_v") != LAYOUT_VERSION:  # 예전 버전 위치는 버리고 새로 배치
            loaded.pop("x", None)
            loaded.pop("y", None)
        if "companies" not in loaded and "salary_manwon" in loaded:  # 예전 설정(삼성·하이닉스 고정)을 옮김
            try:
                sal = float(loaded.get("salary_manwon", 8000))
                ps = (float(loaded.get("hynix_op_jo", 260)) * 1e12 * float(loaded.get("hynix_ps_pct", 10)) / 100
                      / max(1.0, float(loaded.get("hynix_headcount", 34549))) / 1e8)
                loaded["companies"] = [
                    {"name": "삼성 메모리", "salary_manwon": sal,
                     "bonus_eok": float(loaded.get("samsung_bonus_eok", 7.5))},
                    {"name": "SK하이닉스", "salary_manwon": sal, "bonus_eok": round(ps, 2)},
                ]
            except (TypeError, ValueError):
                pass
        for old in ("salary_manwon", "samsung_bonus_eok"):
            loaded.pop(old, None)
        self.cfg = dict(DEFAULTS)
        self.cfg.update(loaded)
        self.cfg["layout_v"] = LAYOUT_VERSION

        self.hist = load_json(HIST, {})
        log = load_json(LOG, {})
        if log.get("day") != today_str():
            if log.get("day"):
                self.hist[log["day"]] = {k: round(float(log.get(k, 0) or 0)) for k in STORE}
            log = new_log()
        for k in STORE:
            log[k] = float(log.get(k, 0) or 0)
        log.setdefault("goal_done", False)
        log.setdefault("summary_done", False)
        self.log = log

        now = time.time()
        self.mode = "idle"
        self.mode_t = self.phase_t = self.launch_t = self.idle_since = self.fx_last = now
        self.notice, self.notice_until, self.flash_until = "", 0.0, 0.0
        self.n = 0
        self.items, self.btns, self.hovered, self.floaters = {}, {}, None, []
        self._btn_hit, self._drag = False, None
        self.hwin = self.swin = self.awin = None
        self.act_tab, self.act_hits, self.act_cum, self.act_hl = "day", [], None, None
        self.alert_on, self.cur_bg, self.theme = False, BG, []
        self.icon_tags, self.icon_hover = [], None
        self.shake_t, self.shaking, self.last_tick = 0.0, False, now
        self.toast_win, self.toast_info = None, None
        self.checkin_t0 = self.next_checkin = self.next_slack_warn = None
        self.last_idle_nudge, self.idle_off_day, self.missed_slack = 0.0, None, 0
        self.summary_time = str(self.cfg.get("summary_at") or "23:00")
        self.rates()

        r = self.root = tk.Tk()
        r.title("기회비용 미터")
        r.overrideredirect(True)
        r.config(bg=KEY)
        try:
            r.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        r.attributes("-topmost", bool(self.cfg["topmost"]))
        r.attributes("-alpha", num(self.cfg, "alpha"))
        s = r.winfo_fpixels("1i") / 96.0
        self.S = s if 0.75 <= s <= 4 else 1.0

        self.c = tk.Canvas(r, bg=KEY, highlightthickness=0, bd=0)
        self.c.pack()
        self.c.bind("<ButtonPress-1>", self.on_press)
        self.c.bind("<B1-Motion>", self.on_move)
        self.c.bind("<ButtonRelease-1>", self.on_release)
        self.c.bind("<Double-Button-1>", self.on_double)
        self.c.bind("<Button-3>", self.menu_open)

        self.build_menu()
        self.layout(first=True)
        self.tick()
        r.after(15000, self.autosave)
        if self.first_run:  # 처음 켠 사람에게 설정 방법 안내
            r.after(1500, self.welcome)
        r.mainloop()

    # ---------- 크기와 위치 ----------
    def p(self, v):
        return int(round(v * self.S))

    def f(self, family, size, *style):
        return (family, -max(7, self.p(size))) + style

    def est_w(self, text, size):
        px = self.p(size)
        return sum(px * (1.0 if ord(ch) >= 0x1100 else 0.56) for ch in text)

    def vscreen(self):
        try:
            gm = ctypes.windll.user32.GetSystemMetrics
            x, y, w, h = gm(76), gm(77), gm(78), gm(79)  # 모니터 전체(가상 화면)
            if w > 0 and h > 0:
                return x, y, x + w, y + h
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def workarea(self):
        try:
            class RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                            ("r", ctypes.c_long), ("b", ctypes.c_long)]
            rc = RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0):
                return rc.l, rc.t, rc.r, rc.b  # 작업 표시줄을 뺀 주 모니터 영역
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def clamp(self, x, y, w, h):
        l, t, r, b = self.vscreen()
        return int(min(max(l, x), r - w)), int(min(max(t, y), b - h))

    def toggle_pos(self, w, h, mini):
        """작게 보기 / 크게 보기 버튼의 위치 (창 안 좌표)"""
        return (w - self.p(20), h / 2) if mini else (w - self.p(46), self.p(20))

    def layout(self, first=False, anchor=None):
        w, h = (self.p(v) for v in (MINI if self.cfg["mini"] else FULL))
        if first:
            if self.cfg.get("x") is None or self.cfg.get("y") is None:
                _, _, wr, wb = self.workarea()
                x, y = wr - w - self.p(20), wb - h - self.p(20)
            else:
                x, y = int(self.cfg["x"]), int(self.cfg["y"])
        elif anchor is not None:  # 전환 버튼이 마우스 아래 그 자리에 오도록
            bx, by = self.toggle_pos(w, h, self.cfg["mini"])
            x, y = round(anchor[0] - bx), round(anchor[1] - by)
        else:  # 오른쪽 아래 모서리를 고정한 채 크기 변경
            x = self.root.winfo_x() + self.root.winfo_width() - w
            y = self.root.winfo_y() + self.root.winfo_height() - h
        x, y = self.clamp(x, y, w, h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.c.config(width=w, height=h)
        self.c.delete("all")
        self.items, self.btns, self.hovered, self.floaters = {}, {}, None, []
        self.theme, self.icon_tags, self.icon_hover = [], [], None
        self.alert_on, self.cur_bg = False, BG  # 새로 그린 뒤 다음 갱신 때 경고 모드를 다시 입힘
        if self.cfg["mini"]:
            self.build_mini(w, h)
        else:
            self.build_full(w, h)
        self.cfg["x"], self.cfg["y"] = x, y
        save_json(CFG, self.cfg)

    def reset_pos(self):
        self.cfg["x"] = self.cfg["y"] = None
        self.layout(first=True)

    # ---------- 화면 구성 ----------
    def build_full(self, w, h):
        p, c, it = self.p, self.c, self.items
        it["bg"] = self.round_rect(1, 1, w - 1, h - 1, p(16), fill=BG, outline=LINE)

        # 머리줄: 돌아가며 보여주는 한 줄 / D-day / 작게 보기 / 메뉴
        it["head"] = c.create_text(p(16), p(20), text="", anchor="w", font=self.f(UI, 11), fill=MUTED)
        self.icon_btn("menu", w - p(22), p(20), self.menu_at)
        bx, by = self.toggle_pos(w, h, False)
        self.icon_btn("min", bx, by, self.toggle_mini)
        it["dday"] = c.create_text(w - p(62), p(20), text="", anchor="e", font=self.f(UI, 11), fill=MUTED)
        self.theme += [(it["head"], MUTED, ALERT_SOFT), (it["dday"], MUTED, ALERT_SOFT)]

        # 두 줄 카운터 (취업 준비: 목표 회사 두 곳 / 직장인: 오늘 번 돈 + 이직 차액 또는 이번 달 번 돈)
        lab1, lab2 = self.row_labels()
        for key, label, color, y in (("sam", lab1, SAM, 48), ("hyn", lab2, HYN, 74)):
            c.create_oval(p(16), p(y - 4), p(24), p(y + 4), fill=color, outline="")
            lab = c.create_text(p(30), p(y), text=label, anchor="w", font=self.f(UI, 12), fill=MUTED)
            it[key] = c.create_text(w - p(16), p(y), text="", anchor="e",
                                    font=self.f(MONO, 15, "bold"), fill=color)
            self.theme += [(lab, MUTED, ALERT_SOFT), (it[key], color, ALERT_TEXT)]
        div = c.create_line(p(16), p(92), w - p(16), p(92), fill=LINE)
        self.theme.append((div, LINE, ALERT_LINE))

        # 상태줄 + 타이머
        it["dot"] = c.create_oval(p(16), p(106), p(24), p(114), fill=MUTED, outline="")
        it["state"] = c.create_text(p(30), p(110), text="", anchor="w", font=self.f(UI, 12), fill=MUTED)
        it["pomo"] = c.create_text(w - p(16), p(110), text="", anchor="e", font=self.f(MONO, 12), fill=MUTED)
        it["fx_slack"] = (w - p(16), p(110))

        # 오늘 목표 막대
        box = (p(16), p(126), w - p(16), p(131))
        track = c.create_rectangle(*box, fill=LINE, outline="")
        self.theme.append((track, LINE, "#8e2a2a"))
        it["bar"] = c.create_rectangle(box[0], box[1], box[0], box[3], fill=GOOD, outline="")
        it["bar_box"] = box
        it["goal"] = c.create_text(p(16), p(145), text="", anchor="w", font=self.f(UI, 10), fill=MUTED)
        it["saved"] = c.create_text(w - p(16), p(145), text="", anchor="e", font=self.f(UI, 10), fill=GOOD)

        # 버튼 3개 (기록 멈춤은 우클릭 메뉴)
        modes = (("study", "▶ 공부"), ("break", "휴식"), ("slack", "딴짓"))
        gap = p(8)
        bw = (w - p(32) - gap * (len(modes) - 1)) / len(modes)
        for i, (m, label) in enumerate(modes):
            x1 = p(16) + i * (bw + gap)
            self.mode_btn(m, label, x1, p(160), x1 + bw, p(186))
        self.paint_buttons()

    def build_mini(self, w, h):
        p, c, it = self.p, self.c, self.items
        it["bg"] = self.round_rect(1, 1, w - 1, h - 1, (h - 2) / 2, fill=BG, outline=LINE)
        it["dot"] = c.create_oval(p(14), h / 2 - p(4), p(22), h / 2 + p(4), fill=MUTED, outline="")
        it["lbl"] = c.create_text(p(30), h / 2, text="", anchor="w", font=self.f(UI, 10), fill=MUTED)
        it["amt"] = c.create_text(p(60), h / 2, text="", anchor="w", font=self.f(MONO, 15, "bold"), fill=FG)
        self.theme += [(it["lbl"], MUTED, ALERT_SOFT), (it["amt"], FG, ALERT_TEXT)]
        bx, by = self.toggle_pos(w, h, True)
        self.icon_btn("max", bx, by, self.toggle_mini)

    def round_rect(self, x1, y1, x2, y2, r, canvas=None, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return (canvas or self.c).create_polygon(pts, smooth=True, **kw)

    def icon_btn(self, name, x, y, fn):
        """글꼴에 의존하지 않도록 아이콘을 직접 그림"""
        p, c = self.p, self.c
        tag = "ib_" + name
        g = (tag, tag + "_g", "btn")
        c.create_oval(x - p(11), y - p(11), x + p(11), y + p(11), fill=BG, outline="",
                      tags=(tag, tag + "_bg", "btn"))
        if name == "menu":
            for dx in (-5, 0, 5):
                c.create_oval(x + p(dx) - p(1.6), y - p(1.6), x + p(dx) + p(1.6), y + p(1.6),
                              fill=MUTED, outline="", tags=g)
        else:
            c.create_line(x - p(5), y, x + p(5), y, fill=MUTED, width=max(1, p(2)), capstyle="round", tags=g)
            if name == "max":
                c.create_line(x, y - p(5), x, y + p(5), fill=MUTED, width=max(1, p(2)), capstyle="round", tags=g)
        self.icon_tags.append(tag)
        self.btn_bind(tag, fn, lambda: self.icon_paint(tag, True), lambda: self.icon_paint(tag, False))

    def icon_paint(self, tag, hover=None):
        """아이콘 색: 마우스를 올리면 밝게, 딴짓 경고 중이면 경고 색에 맞춤"""
        if hover is not None:
            self.icon_hover = tag if hover else (None if self.icon_hover == tag else self.icon_hover)
        on = self.icon_hover == tag
        if self.alert_on:
            bg, fg = ("#7a1c1c" if on else self.cur_bg), (ALERT_TEXT if on else ALERT_SOFT)
        else:
            bg, fg = (PANEL_H if on else BG), (FG if on else MUTED)
        self.c.itemconfig(tag + "_bg", fill=bg)
        self.c.itemconfig(tag + "_g", fill=fg)

    def mode_btn(self, m, label, x1, y1, x2, y2):
        tag = "mb_" + m
        rect = self.round_rect(x1, y1, x2, y2, self.p(8), fill=PANEL, outline=LINE, tags=(tag, "btn"))
        text = self.c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, font=self.f(UI, 12),
                                  fill=FG, tags=(tag, "btn"))
        self.btns[m] = (rect, text)
        self.btn_bind(tag, lambda e, m=m: self.set_mode(m),
                      lambda m=m: self.hover(m, True), lambda m=m: self.hover(m, False))

    def btn_bind(self, tag, on_click, on_enter, on_leave):
        c = self.c
        c.tag_bind(tag, "<Enter>", lambda e: (on_enter(), c.config(cursor="hand2")))
        c.tag_bind(tag, "<Leave>", lambda e: (on_leave(), c.config(cursor="")))
        c.tag_bind(tag, "<Button-1>", lambda e: self.btn_click(on_click, e))

    def btn_click(self, fn, e):
        self._btn_hit = True  # 버튼 클릭이 창 드래그/더블클릭으로 이어지지 않게
        fn(e)

    def hover(self, m, on):
        if on:
            self.hovered = m
        elif self.hovered == m:
            self.hovered = None
        self.paint_buttons()

    def paint_buttons(self):
        for m, (rect, text) in self.btns.items():
            if self.alert_on and m == "slack":  # 딴짓 경고 중: 지금 상태는 흰 버튼으로
                self.c.itemconfig(rect, fill=ALERT_TEXT, outline=ALERT_TEXT)
                self.c.itemconfig(text, fill=ALERT_HOT)
            elif self.alert_on and m == "study":  # 돌아갈 곳(공부)을 초록으로 눈에 띄게
                self.c.itemconfig(rect, fill="#24563a" if m == self.hovered else "#1d3b27", outline=GOOD)
                self.c.itemconfig(text, fill="#c9f7d6")
            elif m == self.mode:
                color = STATE_COLOR[m]
                self.c.itemconfig(rect, fill=color, outline=color)
                self.c.itemconfig(text, fill=DARK)
            else:
                self.c.itemconfig(rect, fill=PANEL_H if m == self.hovered else PANEL, outline=LINE)
                self.c.itemconfig(text, fill=FG)

    # ---------- 계산 ----------
    def is_work(self):
        return self.cfg.get("profile") == "work"

    def companies(self):
        out = []
        for i, d in enumerate((self.cfg.get("companies") or [])[:2]):
            try:
                out.append({"name": str(d.get("name") or f"회사 {i + 1}").strip(),
                            "salary_manwon": float(d.get("salary_manwon", 0) or 0),
                            "bonus_eok": float(d.get("bonus_eok", 0) or 0)})
            except (TypeError, ValueError, AttributeError):
                pass
        while len(out) < 2:
            out.append(dict(DEFAULTS["companies"][len(out)]))
        return out

    def tax_keep(self):
        if not self.cfg.get("after_tax"):
            return 1.0
        return min(1.0, max(0.05, num(self.cfg, "tax_keep_work" if self.is_work() else "tax_keep_job")))

    def rates(self):
        f = self.tax_keep()
        inc = self.cfg.get("include_salary", True)
        r = [(co["bonus_eok"] * 1e8 + (co["salary_manwon"] * 1e4 if inc else 0.0)) * f / YEAR_SEC
             for co in self.companies()]
        self.r_sam, self.r_hyn = r  # 취업 준비: 1번 줄, 2번 줄 (초당)
        # 직장인: 근무 1초당 내 월급, 목표 회사와의 차액 (초당, 하루 종일)
        self.sched = self.parse_sched()
        my = num(self.cfg, "work_salary_manwon") * 1e4 * f
        work_year = self.sched["day_secs"] * len(self.sched["days"]) * 365 / 7
        self.r_work = my / work_year if work_year > 0 else 0.0
        self.r_my_year = my / YEAR_SEC
        tgt = num(self.cfg, "target_manwon") * 1e4 * f
        has_target = bool(str(self.cfg.get("target_name") or "").strip()) and tgt > my
        self.r_diff = (tgt - my) / YEAR_SEC if has_target else 0.0

    def avg(self):
        """공부·딴짓을 돈으로 셀 때 쓰는 초당 금액"""
        if self.is_work():  # 이직 목표가 있으면 연봉 차액, 없으면 내 시간의 값
            return self.r_diff if self.r_diff > 0 else self.r_my_year
        return (self.r_sam + self.r_hyn) / 2

    @staticmethod
    def hhmm(s):
        try:
            h, m = (int(x) for x in str(s).strip().split(":"))
        except (TypeError, ValueError):
            return None
        return h * 60 + m if 0 <= h <= 24 and 0 <= m < 60 and h * 60 + m <= 1440 else None

    def parse_sched(self):
        start = self.hhmm(self.cfg.get("work_start"))
        end = self.hhmm(self.cfg.get("work_end"))
        start, end = (540 if start is None else start), (1080 if end is None else end)
        lunch = None
        lt = str(self.cfg.get("work_lunch") or "").strip()
        if "-" in lt:
            a, b = (self.hhmm(x) for x in lt.split("-", 1))
            if a is not None and b is not None and a < b:
                lunch = (a, b)
        days = {i for i, ch in enumerate("월화수목금토일") if ch in str(self.cfg.get("work_days") or "")}
        day_min = max(0, end - start)
        if lunch:
            day_min -= max(0, min(end, lunch[1]) - max(start, lunch[0]))
        return {"start": start, "end": end, "lunch": lunch, "days": days, "day_secs": day_min * 60}

    def worked_secs(self, d, upto=None):
        """그날 근무 시간 (초). upto가 있으면 그 시각까지만"""
        s = self.sched
        if d.weekday() not in s["days"] or s["end"] <= s["start"]:
            return 0.0
        lim = s["end"]
        if upto is not None:
            lim = min(lim, upto.hour * 60 + upto.minute + upto.second / 60)
        total = max(0.0, lim - s["start"])
        if s["lunch"]:
            total -= max(0.0, min(lim, s["lunch"][1]) - max(s["start"], s["lunch"][0]))
        return max(0.0, total) * 60

    @staticmethod
    def payday_in(y, m, pd):
        last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
        return dt.date(y, m, min(pd, last))

    def last_payday(self, today, pd):
        d = self.payday_in(today.year, today.month, pd)
        if d > today:
            y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
            d = self.payday_in(y, m, pd)
        return d

    def next_payday(self, today, pd):
        d = self.payday_in(today.year, today.month, pd)
        if d < today:
            y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
            d = self.payday_in(y, m, pd)
        return d

    def payday(self):
        try:
            pd = int(num(self.cfg, "payday"))
        except (TypeError, ValueError):
            return 0
        return pd if 1 <= pd <= 31 else 0

    def work_values(self):
        """(오늘 번 돈, 오늘 근무한 초, 이번 달 번 돈) — 근무 시간표 기준"""
        n = dt.datetime.now()
        today = n.date()
        today_s = self.worked_secs(today, n)
        start = self.last_payday(today, self.payday() or 1)  # 월급날이 없으면 매달 1일부터
        past = sum(self.worked_secs(start + dt.timedelta(days=i)) for i in range((today - start).days))
        return self.r_work * today_s, today_s, self.r_work * (past + today_s)

    @staticmethod
    def short(s, n):
        return s if len(s) <= n else s[:n - 1] + "…"

    def row_labels(self):
        if self.is_work():
            tname = str(self.cfg.get("target_name") or "").strip()
            return "오늘 번 돈", (f"{self.short(tname, 7)} 이직하면" if self.r_diff > 0 else "이번 달 번 돈")
        a, b = self.companies()
        return self.short(a["name"], 10), self.short(b["name"], 10)

    def row_values(self, e):
        """두 줄에 보여줄 금액과 둘째 줄 앞에 붙일 기호"""
        if self.is_work():
            earned, _, month = self.work_values()
            if self.r_diff > 0:
                return earned, self.r_diff * e, "+"
            return earned, month, ""
        return self.r_sam * e, self.r_hyn * e, ""

    def elapsed(self):
        if self.cfg["basis"] == "launch":
            return time.time() - self.launch_t
        now = dt.datetime.now()
        return (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()

    def today_totals(self):
        live = max(0.0, time.time() - self.mode_t)
        return {k: self.log[k] + (live if self.mode == k else 0.0) for k in KINDS}

    def fun_items(self):
        out = []
        for item in self.cfg.get("fun_items") or []:
            try:
                name, unit, price = str(item[0]), str(item[1]), float(item[2])
            except (TypeError, ValueError, IndexError):
                continue
            if price > 0:
                out.append((name, unit, price))
        return out

    def head_text(self, now, e, avg, today_basis):
        """머리줄은 7초마다 다른 정보로 바뀜"""
        pre = "오늘" if today_basis else "켠 뒤"
        texts = [f"{pre} 누적 · 시간당 +{man(avg * 3600)}"]
        lost = avg * e
        for name, unit, price in self.fun_items():
            cnt = int(lost // price)
            if cnt >= 1:
                texts.append(f"놓친 돈 = {name} {cnt:,}{unit}")
        wage = num(self.cfg, "min_wage")
        if wage > 0:
            texts.append(f"공부 1시간 = 최저시급의 {avg * 3600 / wage:.1f}배")
        n = dt.datetime.now()
        left = (dt.datetime(n.year + 1, 1, 1) - n).total_seconds()
        texts.append(f"올해 남은 {math.ceil(left / 86400)}일 = {man(avg * left)}")
        st = self.day_stats(self.log["day"])
        if st and st["on"] >= 600:
            texts.append(f"오늘 켜진 {hm(st['on'])} 중 공부 {int(st['ratio'] * 100)}%")
        return texts[int(now // 7) % len(texts)]

    def head_text_work(self, now):
        """직장인 모드 머리줄: 퇴근까지 / 내 시급 / 월급날 / 오늘 번 돈 환산 / 이직 차액"""
        s = self.sched
        n = dt.datetime.now()
        today = n.date()
        mins = n.hour * 60 + n.minute + n.second / 60
        earned, today_s, month = self.work_values()
        if today.weekday() not in s["days"] or s["end"] <= s["start"]:
            texts = ["오늘은 쉬는 날이에요"]
        elif mins < s["start"]:
            texts = [f"출근까지 {hm((s['start'] - mins) * 60)}"]
        elif mins < s["end"]:
            texts = [f"퇴근까지 {hm((s['end'] - mins) * 60)} · 남은 돈 {man(self.r_work * (s['day_secs'] - today_s))}"]
        else:
            texts = [f"퇴근! 오늘 {man(earned)} 벌었어요"]
        texts.append(f"내 시급 {man(self.r_work * 3600)} · 1분에 {won0(self.r_work * 60)}")
        pd = self.payday()
        if pd:
            left = (self.next_payday(today, pd) - today).days
            texts.append(("오늘 월급날!" if left == 0 else f"월급날 D-{left}") + f" · 이번 달 {man(month)}째")
        for name, unit, price in self.fun_items():
            cnt = int(earned // price)
            if cnt >= 1:
                texts.append(f"오늘 번 돈 = {name} {cnt:,}{unit}")
        if self.r_diff > 0:
            tname = self.short(str(self.cfg.get("target_name") or "").strip(), 8)
            texts.append(f"{tname} 가면 연 +{man(self.r_diff * YEAR_SEC)}")
        st = self.day_stats(self.log["day"])
        if st and st["on"] >= 600:
            texts.append(f"오늘 켜진 {hm(st['on'])} 중 공부 {int(st['ratio'] * 100)}%")
        return texts[int(now // 7) % len(texts)]

    def dday_text(self):
        try:
            d = dt.date.fromisoformat(str(self.cfg.get("dday_date", "")).strip())
        except ValueError:
            return ""
        n = (d - dt.date.today()).days
        tag = "D-Day" if n == 0 else (f"D-{n}" if n > 0 else f"D+{-n}")
        return f"{str(self.cfg.get('dday_label', '')).strip()} {tag}".strip()

    def flush(self):
        now = time.time()
        if self.mode in KINDS:
            self.log[self.mode] += max(0.0, now - self.mode_t)
        self.mode_t = now
        self.hist[self.log["day"]] = {k: round(self.log.get(k, 0.0)) for k in STORE}
        if self.log["day"] != today_str():  # 자정이 지나면 새 날로
            self.log = new_log()
        for d in sorted(self.hist)[:-HIST_DAYS]:
            del self.hist[d]
        save_json(LOG, self.log)
        save_json(HIST, self.hist)

    def autosave(self):
        self.flush()
        self.root.after(15000, self.autosave)

    # ---------- 뽀모도로 ----------
    def check_timers(self, now):
        if not self.cfg.get("pomodoro"):
            return
        focus = max(1.0, num(self.cfg, "focus_min"))
        rest = max(1.0, num(self.cfg, "break_min"))
        if self.mode == "study" and now - self.phase_t >= focus * 60:
            self.set_mode("break")
            self.say(f"집중 {focus:g}분 끝! {rest:g}분 쉬어요", 10)
            self.flash(4)
            self.toast(f"집중 {focus:g}분 끝!", f"{rest:g}분 쉬어요. 휴식이 끝나면 다시 알려드릴게요.", REST,
                       kind="info", timeout=12, sound=2)
        elif self.mode == "break" and now - self.phase_t >= rest * 60:
            self.set_mode("idle")
            self.say("휴식 끝! ▶ 공부를 누르면 다시 시작해요", 60)
            self.flash(6)
            self.toast("휴식 끝!", "다시 집중할 시간이에요.", GOOD,
                       buttons=(("▶ 다시 공부", lambda: self.set_mode("study")),),
                       kind="break_end", timeout=60, sound=2)

    def timer_text(self, now):
        if not self.cfg.get("pomodoro") or self.mode not in ("study", "break"):
            return ""
        total = max(1.0, num(self.cfg, "focus_min" if self.mode == "study" else "break_min")) * 60
        left = math.ceil(max(0.0, total - (now - self.phase_t)))
        return f"{'집중' if self.mode == 'study' else '휴식'} {mmss(left)}"

    def say(self, text, secs):
        self.notice, self.notice_until = text, time.time() + secs

    def flash(self, secs):
        self.flash_until = time.time() + secs

    def beep(self, n=1):
        if not n or not self.cfg.get("sound", True):
            return
        if winsound is None:
            self.root.bell()
            return

        def run():
            for i in range(n):
                try:
                    winsound.Beep(880 if i % 2 == 0 else 1175, 140)
                except Exception:
                    break
                time.sleep(0.06)
        threading.Thread(target=run, daemon=True).start()

    # ---------- 공부 체크인 · 딴짓 경고 · 멈춤 알림 · 오늘 결산 ----------
    def schedule_checkin(self, now):
        rng = CHECKIN_RANGES.get(self.cfg.get("checkin"))
        self.next_checkin = now + random.uniform(*rng) * 60 if rng else None

    def check_nudges(self, now, avg):
        if (self.mode == "study" and self.next_checkin and now >= self.next_checkin
                and self.checkin_t0 is None):
            self.checkin_t0, self.next_checkin = now, None
            wait = max(15.0, num(self.cfg, "checkin_timeout_s"))
            self.toast("공부 체크인", "지금 공부하고 있나요?", GOOD,
                       buttons=(("네, 공부 중", self.checkin_yes), ("사실 딴짓 중", self.checkin_no)),
                       kind="checkin", deadline=now + wait, on_timeout=self.checkin_timeout,
                       countdown="{s}초 안에 답이 없으면 체크인 때부터 딴짓으로 기록돼요", sound=2)
        elif (self.mode == "slack" and self.cfg.get("slack_warn", True) and self.next_slack_warn
                and now >= self.next_slack_warn):
            self.next_slack_warn = now + 10 * 60
            spent = now - self.phase_t
            self.toast(f"딴짓 {dur(spent)}째", f"그동안 {won0(spent * avg)}이 흘러갔어요.", BAD,
                       buttons=(("▶ 공부 시작", lambda: self.set_mode("study")), ("5분만 더", self.snooze_slack)),
                       kind="slack", deadline=now + 60, on_timeout=self.slack_missed, sound=2)
        elif self.mode == "idle" and self.idle_nudge_due(now):
            self.last_idle_nudge = now
            spent = now - self.idle_since
            self.toast(f"공부 멈춘 지 {dur(spent)}", f"그 사이 {won0(spent * avg)}이 흘러갔어요. 다시 시작해볼까요?",
                       GOLD, buttons=(("▶ 공부 시작", lambda: self.set_mode("study")),
                                      ("오늘은 쉴래요", self.idle_off)),
                       kind="idle", timeout=45, sound=1)

    def idle_nudge_due(self, now):
        if not self.cfg.get("idle_nudge", True) or self.idle_off_day == today_str():
            return False
        gap = max(10.0, num(self.cfg, "idle_nudge_min")) * 60
        if now - self.idle_since < gap or now - self.last_idle_nudge < gap:
            return False
        try:
            start, end = (int(v) for v in self.cfg.get("active_hours", [9, 23]))
        except (TypeError, ValueError):
            start, end = 9, 23
        return start <= dt.datetime.now().hour < end

    def checkin_yes(self):
        self.checkin_t0 = None
        self.schedule_checkin(time.time())

    def checkin_no(self):
        self.checkin_t0 = None
        self.set_mode("slack")

    def checkin_timeout(self):
        t0, self.checkin_t0 = self.checkin_t0, None
        if self.mode != "study" or t0 is None:
            return
        # 체크인 전까지만 공부로 인정하고, 체크인 때부터는 딴짓으로 기록
        if self.mode_t > t0:  # 자동 저장으로 체크인 뒤 시간이 이미 공부에 들어갔으면 빼기
            self.log["study"] = max(0.0, self.log["study"] - (self.mode_t - t0))
        else:
            self.log["study"] += t0 - self.mode_t
        self.mode, self.mode_t, self.phase_t = "slack", t0, t0
        self.next_checkin, self.next_slack_warn = None, t0 + 5 * 60
        self.missed_slack, self.fx_last, self.shake_t = 0, time.time(), time.time() - 12
        self.v_mode.set("slack")
        self.paint_buttons()
        self.flush()
        self.say("체크인 무응답 · 딴짓으로 기록 중", 30)
        self.toast("딴짓으로 기록했어요", "체크인에 답이 없어서 그때부터 딴짓으로 셌어요. 돌아오면 다시 공부를 누르세요.",
                   BAD, buttons=(("▶ 다시 공부", lambda: self.set_mode("study")),),
                   kind="slack", timeout=None, sound=1)

    def slack_missed(self):
        self.missed_slack += 1
        if self.missed_slack >= 3 and self.mode == "slack":
            self.set_mode("idle")
            self.toast("기록을 멈췄어요", "딴짓 알림에 세 번 연속 답이 없어서 자리를 비운 걸로 보고 멈췄어요.", MUTED,
                       buttons=(("확인", lambda: None),), kind="info", timeout=None, sound=1)

    def snooze_slack(self):
        self.missed_slack = 0
        self.next_slack_warn = time.time() + 5 * 60

    def idle_off(self):
        self.idle_off_day = today_str()

    def check_summary(self, tot):
        at = str(self.cfg.get("summary_at") or "").strip()
        if not at or self.log.get("summary_done"):
            return
        try:
            hh, mm = (int(x) for x in at.split(":"))
        except ValueError:
            return
        n = dt.datetime.now()
        if (n.hour, n.minute) < (hh, mm):
            return
        if self.toast_info and self.toast_info["kind"] == "checkin":
            return  # 체크인에 답한 뒤에 보여줌
        self.log["summary_done"] = True
        if sum(tot.values()) >= 60:  # 오늘 기록이 있을 때만
            self.show_summary()

    def show_summary(self):
        self.flush()
        tot, avg = self.today_totals(), self.avg()
        goal_h = max(0.1, num(self.cfg, "daily_goal_h"))
        pct = int(tot["study"] / (goal_h * 3600) * 100)
        st = self.day_stats(self.log["day"])
        on_line = (f"켜져 있던 {hm(st['on'])} 중 공부 {int(st['ratio'] * 100)}%\n" if st else "")
        body = (f"공부 {hm(tot['study'])} · 공부로 지킨 돈 {man(tot['study'] * avg)}\n"
                f"딴짓 {hm(tot['slack'])} · 흘러간 돈 {man(tot['slack'] * avg)}\n"
                f"{on_line}"
                f"목표 {goal_h:g}시간 중 {pct}% · 연속 {self.streak()}일")
        self.toast("오늘 결산", body, SAM, buttons=(("확인", lambda: None), ("공부 활동 보기", self.show_activity)),
                   kind="info", timeout=None, sound=1)

    # ---------- 알림 창 ----------
    def toast(self, title, body, color, buttons=(), kind="info", timeout=10.0, deadline=None,
              on_timeout=None, countdown=None, sound=1):
        # 체크인에 답하기 전에는 다른 알림으로 덮지 않음
        if self.toast_info and self.toast_info["kind"] == "checkin" and kind != "checkin":
            return
        self.close_toast()
        p = self.p
        w = p(300)
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.config(bg=KEY)
        try:
            win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        c = tk.Canvas(win, width=w, height=p(240), bg=KEY, highlightthickness=0, bd=0)
        c.pack()
        c.create_oval(p(16), p(19), p(24), p(27), fill=color, outline="")
        c.create_text(p(32), p(23), text=title, anchor="w", font=self.f(UI, 12, "bold"), fill=color)
        self.toast_close_btn(c, w - p(22), p(23))
        body_id = c.create_text(p(16), p(40), text=body, anchor="nw", width=w - p(32),
                                font=self.f(UI, 11), fill=FG)
        y = c.bbox(body_id)[3]
        cd_id = None
        if countdown and deadline:
            cd_id = c.create_text(p(16), y + p(6), anchor="nw", width=w - p(32), font=self.f(UI, 10),
                                  fill=MUTED, text=countdown.format(s=math.ceil(deadline - time.time())))
            y = c.bbox(cd_id)[3]
        if buttons:
            y += p(12)
            right = w - p(16)
            for i, (label, fn) in enumerate(buttons):  # 첫 번째(주 버튼)가 오른쪽 끝
                primary = i == 0
                tag = f"tb{i}"
                tid = c.create_text(right - p(12), y + p(14), text=label, anchor="e", font=self.f(UI, 11),
                                    fill=DARK if primary else FG, tags=(tag,))
                bb = c.bbox(tid)
                tw = max(bb[2] - bb[0], self.est_w(label, 11))  # 글꼴 측정이 어긋나도 글자가 버튼 밖으로 안 나가게
                x1 = right - p(12) - tw - p(12)
                rid = self.round_rect(x1, y, right, y + p(28), p(8), canvas=c, tags=(tag,),
                                      fill=color if primary else PANEL, outline=color if primary else LINE)
                c.tag_lower(rid, tid)
                self.toast_btn_bind(c, tag, rid, fn, PANEL_H if not primary else color,
                                    color if primary else PANEL)
                right = x1 - p(8)
            y += p(28)
        h = y + p(14)
        bg = self.round_rect(1, 1, w - 1, h - 1, p(14), canvas=c, fill=BG, outline=color)
        c.tag_lower(bg)
        c.config(height=h)
        x, ty = self.toast_pos(w, h)
        win.geometry(f"{w}x{h}+{x}+{ty}")
        now = time.time()
        self.toast_win = win
        self.toast_info = {"kind": kind, "deadline": deadline, "on_timeout": on_timeout, "canvas": c,
                           "until": None if deadline or not timeout else now + timeout,
                           "cd_id": cd_id, "countdown": countdown}
        self.fade_in(win, 0.0)
        self.beep(sound)

    def toast_pos(self, w, h):
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        top = self.vscreen()[1]
        y = ry - h - self.p(10)  # 위젯 바로 위, 자리가 없으면 아래
        if y < top:
            y = ry + rh + self.p(10)
        return self.clamp(rx + rw - w, y, w, h)

    def toast_close_btn(self, c, x, y):
        p = self.p
        c.create_oval(x - p(10), y - p(10), x + p(10), y + p(10), fill=BG, outline="",
                      tags=("tclose", "tclose_bg"))
        for dy in (-4, 4):
            c.create_line(x - p(4), y + p(dy), x + p(4), y - p(dy), fill=MUTED, width=max(1, p(1.6)),
                          capstyle="round", tags=("tclose", "tclose_g"))
        c.tag_bind("tclose", "<Enter>", lambda e: (c.itemconfig("tclose_bg", fill=PANEL_H),
                                                   c.itemconfig("tclose_g", fill=FG), c.config(cursor="hand2")))
        c.tag_bind("tclose", "<Leave>", lambda e: (c.itemconfig("tclose_bg", fill=BG),
                                                   c.itemconfig("tclose_g", fill=MUTED), c.config(cursor="")))
        c.tag_bind("tclose", "<Button-1>", lambda e: self.toast_dismiss())

    def toast_btn_bind(self, c, tag, rid, fn, hover_fill, normal_fill):
        c.tag_bind(tag, "<Enter>", lambda e: (c.itemconfig(rid, fill=hover_fill), c.config(cursor="hand2")))
        c.tag_bind(tag, "<Leave>", lambda e: (c.itemconfig(rid, fill=normal_fill), c.config(cursor="")))
        c.tag_bind(tag, "<Button-1>", lambda e: self.toast_click(fn))

    def toast_click(self, fn):
        self.close_toast()
        fn()

    def toast_dismiss(self):
        kind = self.toast_info["kind"] if self.toast_info else None
        self.close_toast()
        if kind == "checkin":  # 닫기를 눌렀다면 자리에 있다는 뜻으로 봄
            self.checkin_yes()
        elif kind == "slack":
            self.missed_slack = 0

    def close_toast(self, kinds=None):
        if self.toast_info and kinds and self.toast_info["kind"] not in kinds:
            return
        if self.toast_win is not None:
            try:
                self.toast_win.destroy()
            except tk.TclError:
                pass
        self.toast_win, self.toast_info = None, None

    def fade_in(self, win, a):
        try:
            if not win.winfo_exists():
                return
            a = min(0.97, a + 0.15)
            win.attributes("-alpha", a)
            if a < 0.97:
                self.root.after(25, lambda: self.fade_in(win, a))
        except tk.TclError:
            pass

    def toast_tick(self, now):
        ti = self.toast_info
        if not ti:
            return
        try:
            alive = bool(self.toast_win.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            self.toast_win, self.toast_info = None, None
            return
        if ti["deadline"]:
            if ti["cd_id"]:
                ti["canvas"].itemconfig(ti["cd_id"], text=ti["countdown"].format(
                    s=max(0, math.ceil(ti["deadline"] - now))))
            if now >= ti["deadline"]:
                fn = ti["on_timeout"]
                self.close_toast()
                if fn:
                    fn()
                return
        if ti["until"] and now >= ti["until"]:
            self.close_toast()

    def toast_test(self):
        self.toast("알림 미리보기", "공부 체크인, 딴짓 경고, 뽀모도로 알림이 이렇게 떠요.", SAM,
                   buttons=(("확인", lambda: None),), kind="info", timeout=8, sound=1)

    # ---------- +원 / -원 효과 ----------
    def money_fx(self, now, avg):
        if self.cfg["mini"] or not self.cfg.get("money_fx", True):
            return
        if self.mode == "study" and now - self.fx_last >= 60:
            self.fx_last = now
            # '공부로 지킨 돈' 바로 왼쪽에서 떠오름 (글꼴 측정이 어긋나도 겹치지 않게 넉넉히)
            bb = self.c.bbox(self.items["saved"]) or (0, 0, 0, 0)
            text = self.c.itemcget(self.items["saved"], "text")
            right = self.items["fx_slack"][0]
            x = right - max(bb[2] - bb[0], self.est_w(text, 10)) - self.p(8)
            self.spawn_float(f"+{won0(avg * 60)}", GOOD, x, self.p(145), now)
        elif self.mode == "slack" and now - self.fx_last >= 10:
            self.fx_last = now
            x, y = self.items["fx_slack"]
            self.spawn_float(f"−{won0(avg * 10)}", ALERT_TEXT if self.alert_on else BAD, x, y, now)

    def spawn_float(self, text, color, x, y, now):
        fid = self.c.create_text(x, y, text=text, anchor="e", font=self.f(MONO, 11, "bold"), fill=color)
        self.floaters.append((fid, now, x, y, color))

    def animate_floats(self, now):
        keep = []
        for fid, t0, x, y, color in self.floaters:
            t = max(0.0, (now - t0) / 1.4)
            if t >= 1:
                self.c.delete(fid)
                continue
            self.c.coords(fid, x, y - self.p(16) * t)
            self.c.itemconfig(fid, fill=mix(color, self.cur_bg, t ** 1.6))  # 바탕색 쪽으로 사라짐
            keep.append((fid, t0, x, y, color))
        self.floaters = keep

    # ---------- 딴짓 경고 모드 ----------
    def alert_wanted(self):
        return self.mode == "slack" and self.cfg.get("slack_alert", "strong") in ("strong", "normal")

    def apply_alert(self, on):
        """딴짓 경고 모드 켜기/끄기: 글자색을 바꾸고, 흐리게·뒤로 숨기기 설정은 잠시 무시"""
        self.alert_on = on
        self.cur_bg = ALERT_DARK if on else BG
        for item, normal, alert in self.theme:
            self.c.itemconfig(item, fill=alert if on else normal)
        if "state" in self.items:
            self.c.itemconfig(self.items["state"], font=self.f(UI, 12, "bold") if on else self.f(UI, 12))
        self.c.itemconfig(self.items["bg"], fill=self.cur_bg,
                          outline=ALERT_LINE if on else LINE, width=max(1, self.p(2)) if on else 1)
        for tag in self.icon_tags:
            self.icon_paint(tag)
        self.paint_buttons()
        try:
            self.root.attributes("-alpha", 1.0 if on else num(self.cfg, "alpha"))
            self.root.attributes("-topmost", True if on else bool(self.cfg["topmost"]))
        except tk.TclError:
            pass

    def alert_pulse(self, now):
        """빨간 바탕이 1.6초 주기로 천천히 밝아졌다 어두워짐 (번쩍이는 깜빡임은 피함)"""
        k = 0.5 - 0.5 * math.cos(2 * math.pi * now / 1.6)
        self.cur_bg = mix(ALERT_DARK, ALERT_HOT, k)
        self.c.itemconfig(self.items["bg"], fill=self.cur_bg)
        for tag in self.icon_tags:
            if tag != self.icon_hover:
                self.c.itemconfig(tag + "_bg", fill=self.cur_bg)

    def shake(self):
        """창을 좌우로 짧게 흔듦"""
        self.shaking = True
        x0, y0 = self.root.winfo_x(), self.root.winfo_y()
        offs = (7, -7, 6, -6, 4, -4, 2, -2, 0)

        def step(i=0):
            if self._drag:  # 사용자가 끌고 있으면 바로 멈춤
                self.shaking = False
                return
            try:
                if i >= len(offs):
                    self.root.geometry(f"+{x0}+{y0}")
                    self.shaking = False
                    return
                self.root.geometry(f"+{x0 + self.p(offs[i])}+{y0}")
            except tk.TclError:
                self.shaking = False
                return
            self.root.after(35, lambda: step(i + 1))
        step()

    # ---------- 화면 갱신 ----------
    def status(self, now, tot, avg):
        if self.notice and now < self.notice_until:
            return {"text": self.notice, "fill": FG}
        if self.mode == "study":
            return {"text": f"공부 중 {hms(tot['study'])}", "fill": GOOD}
        if self.mode == "break":
            return {"text": f"휴식 중 · 오늘 공부 {hms(tot['study'])}", "fill": REST}
        if self.mode == "slack":
            return {"text": f"딴짓 중 {hms(tot['slack'])} · 손실 {won0(tot['slack'] * avg)}", "fill": BAD}
        return {"text": f"멈춤 · 오늘 공부 {hms(tot['study'])}", "fill": MUTED}

    def tick(self):
        try:
            self.tick_once()
        except Exception:
            pass  # 한 번 갱신에 실패해도 위젯이 멈추지 않게 다음 갱신은 계속
        self.root.after(100, self.tick)

    def tick_once(self):
        now = time.time()
        if self.log["day"] != today_str():
            self.flush()
        gap, self.last_tick = now - self.last_tick, now
        if 0 < gap < 5:  # 위젯이 켜져 있던 시간 (절전·잠자기로 멈춘 시간은 빼고)
            self.log["on"] = self.log.get("on", 0.0) + gap
        self.check_timers(now)
        avg = self.avg()
        self.check_nudges(now, avg)
        self.toast_tick(now)

        e = self.elapsed()
        tot = self.today_totals()
        self.check_summary(tot)
        goal_h = max(0.1, num(self.cfg, "daily_goal_h"))
        goal_s = goal_h * 3600
        if tot["study"] >= goal_s and not self.log.get("goal_done"):
            self.log["goal_done"] = True
            self.say("오늘 목표 달성! 수고했어요", 8)
            self.flash(5)
            self.toast("오늘 목표 달성!", f"목표 {goal_h:g}시간을 채웠어요. 수고했어요.", GOLD,
                       kind="info", timeout=12, sound=3)

        self.n += 1
        c, it = self.c, self.items
        alert = self.alert_wanted()
        if alert != self.alert_on:
            self.apply_alert(alert)
        color = STATE_COLOR[self.mode]
        blink = self.mode != "idle" and (self.n // 5) % 2 == 1
        if alert:
            self.alert_pulse(now)
            c.itemconfig(it["dot"], fill=self.cur_bg if blink else ALERT_TEXT)
            if (self.cfg.get("slack_alert") == "strong" and now - self.shake_t >= 15
                    and not self._drag and not self.shaking):
                self.shake_t = now
                self.shake()
        else:
            c.itemconfig(it["dot"], fill=BG if blink else color)
            if now < self.flash_until:
                c.itemconfig(it["bg"], outline=color if (self.n // 3) % 2 == 0 else LINE, width=max(1, self.p(2)))
            else:
                c.itemconfig(it["bg"], outline=LINE, width=1)

        today_basis = self.cfg["basis"] != "launch"
        work = self.is_work()
        if self.cfg["mini"]:
            c.itemconfig(it["lbl"], text="오늘" if (today_basis or work) else "켠 뒤")
            c.itemconfig(it["amt"], text=won(self.row_values(e)[0] if work else avg * e))
        else:
            v1, v2, pre2 = self.row_values(e)
            c.itemconfig(it["sam"], text=won(v1))
            c.itemconfig(it["hyn"], text=pre2 + won(v2))
            c.itemconfig(it["head"], text=self.head_text_work(now) if work else
                         self.head_text(now, e, avg, today_basis))
            c.itemconfig(it["dday"], text=self.dday_text())
            st = self.status(now, tot, avg)
            if alert:
                st["fill"] = ALERT_TEXT
            c.itemconfig(it["state"], **st)
            c.itemconfig(it["pomo"], text=self.timer_text(now), fill=color)
            frac = min(1.0, tot["study"] / goal_s)
            x1, y1, x2, y2 = it["bar_box"]
            c.coords(it["bar"], x1, y1, x1 + (x2 - x1) * frac, y2)
            c.itemconfig(it["bar"], fill=GOLD if frac >= 1 else GOOD)
            if frac >= 1:
                c.itemconfig(it["goal"], text=f"오늘 목표 {goal_h:g}시간 달성!", fill=ALERT_SOFT if alert else GOLD)
            else:
                c.itemconfig(it["goal"], text=f"오늘 목표 {goal_h:g}시간 · {int(frac * 100)}%",
                             fill=ALERT_SOFT if alert else MUTED)
            c.itemconfig(it["saved"], text=f"공부로 지킨 돈 {won0(tot['study'] * avg)}",
                         fill=ALERT_SOFT if alert else GOOD)
            self.money_fx(now, avg)
            self.animate_floats(now)

    # ---------- 조작 ----------
    def on_press(self, ev):
        if self._btn_hit:
            self._btn_hit, self._drag = False, None
            return
        self._drag = (ev.x_root - self.root.winfo_x(), ev.y_root - self.root.winfo_y())

    def on_move(self, ev):
        if self._drag:
            self.root.geometry(f"+{ev.x_root - self._drag[0]}+{ev.y_root - self._drag[1]}")

    def on_release(self, _ev):
        if self._drag:
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            save_json(CFG, self.cfg)
        self._drag = None

    def on_double(self, _ev):
        if self._btn_hit:
            self._btn_hit = False
            return
        self.set_mode("slack" if self.mode == "study" else "study")

    def set_mode(self, m):
        if m == self.mode:
            return
        self.flush()
        now = time.time()
        self.mode, self.phase_t, self.notice = m, now, ""
        self.checkin_t0, self.next_checkin = None, None
        self.missed_slack, self.fx_last, self.shake_t = 0, now, now - 12  # 딴짓 시작 3초 뒤 첫 흔들림
        self.close_toast(kinds=("checkin", "slack", "idle", "break_end"))  # 지난 상태의 알림은 닫기
        self.next_slack_warn = now + 5 * 60 if m == "slack" else None
        if m == "study":
            self.schedule_checkin(now)
        elif m == "idle":
            self.idle_since = now
        self.v_mode.set(m)
        self.paint_buttons()

    def toggle_mini(self, _e=None):
        # 지금 전환 버튼이 있는 화면 위치를 기억했다가, 바뀐 창의 전환 버튼을 같은 자리에 둠
        bx, by = self.toggle_pos(self.root.winfo_width(), self.root.winfo_height(), self.cfg["mini"])
        anchor = (self.root.winfo_x() + bx, self.root.winfo_y() + by)
        self.cfg["mini"] = not self.cfg["mini"]
        self.v_mini.set(self.cfg["mini"])
        self.layout(anchor=anchor)

    # ---------- 메뉴 ----------
    def pomo_label(self):
        return f"뽀모도로 ({num(self.cfg, 'focus_min'):g}분 집중 · {num(self.cfg, 'break_min'):g}분 휴식)"

    def build_menu(self):
        font = (UI, 9)
        m = self.menu = tk.Menu(self.root, tearoff=0, font=font)
        self.v_mode = tk.StringVar(value=self.mode)
        for val, label in (("study", "공부 시작"), ("break", "휴식"), ("slack", "딴짓 중"), ("idle", "기록 멈춤")):
            m.add_radiobutton(label=label, variable=self.v_mode, value=val, command=lambda v=val: self.set_mode(v))
        m.add_separator()

        self.v_pomo = tk.BooleanVar(value=bool(self.cfg["pomodoro"]))
        m.add_checkbutton(label=self.pomo_label(), variable=self.v_pomo, command=self.set_pomo)
        self.pomo_idx = m.index("end")
        focus = tk.Menu(m, tearoff=0, font=font)
        self.v_focus = tk.StringVar(value=f"{num(self.cfg, 'focus_min'):g}")
        for mins in FOCUS_CHOICES:
            focus.add_radiobutton(label=f"{mins}분", variable=self.v_focus, value=str(mins),
                                  command=self.set_focus)
        m.add_cascade(label="뽀모도로 집중 시간", menu=focus)

        noti = tk.Menu(m, tearoff=0, font=font)
        self.v_checkin = tk.StringVar(value=str(self.cfg.get("checkin", "sometimes")))
        for val, label in (("sometimes", "공부 체크인 가끔 (20~40분마다)"),
                           ("often", "공부 체크인 자주 (10~20분마다)"),
                           ("off", "공부 체크인 끄기")):
            noti.add_radiobutton(label=label, variable=self.v_checkin, value=val, command=self.set_checkin)
        noti.add_separator()
        self.v_slackwarn = tk.BooleanVar(value=bool(self.cfg.get("slack_warn", True)))
        noti.add_checkbutton(label="딴짓이 길어지면 알림", variable=self.v_slackwarn, command=self.set_slackwarn)
        self.v_idle = tk.BooleanVar(value=bool(self.cfg.get("idle_nudge", True)))
        noti.add_checkbutton(label="멈춤이 오래되면 알림", variable=self.v_idle, command=self.set_idle)
        self.v_summary = tk.BooleanVar(value=bool(str(self.cfg.get("summary_at") or "").strip()))
        noti.add_checkbutton(label=f"오늘 결산 알림 ({self.summary_time})", variable=self.v_summary,
                             command=self.set_summary)
        self.summary_idx = noti.index("end")
        self.noti = noti
        self.v_sound = tk.BooleanVar(value=bool(self.cfg["sound"]))
        noti.add_checkbutton(label="알림 소리", variable=self.v_sound, command=self.set_sound)
        noti.add_separator()
        noti.add_command(label="알림 미리보기", command=self.toast_test)
        m.add_cascade(label="알림", menu=noti)

        goal = tk.Menu(m, tearoff=0, font=font)
        self.v_goal = tk.StringVar(value=f"{num(self.cfg, 'daily_goal_h'):g}")
        for g in (2, 4, 6, 8, 10, 12):
            goal.add_radiobutton(label=f"{g}시간", variable=self.v_goal, value=str(g), command=self.set_goal)
        m.add_cascade(label="하루 목표 공부 시간", menu=goal)
        m.add_separator()

        m.add_command(label="공부 활동 (켜진 시간 대비 공부)", command=self.show_activity)
        m.add_command(label="최근 7일 기록 보기", command=self.show_history)
        m.add_command(label="오늘 결산 보기", command=self.show_summary)
        m.add_command(label="숫자 · 목표 설정…", command=self.open_settings)
        prof = tk.Menu(m, tearoff=0, font=font)
        self.v_profile = tk.StringVar(value="work" if self.is_work() else "job")
        prof.add_radiobutton(label="취업 준비 (목표 회사 두 곳)", variable=self.v_profile, value="job",
                             command=self.set_profile)
        prof.add_radiobutton(label="직장인 (내 월급 + 이직 목표)", variable=self.v_profile, value="work",
                             command=self.set_profile)
        m.add_cascade(label="사용 방식", menu=prof)
        m.add_separator()

        basis = tk.Menu(m, tearoff=0, font=font)
        self.v_basis = tk.StringVar(value=self.cfg["basis"])
        basis.add_radiobutton(label="오늘 0시부터", variable=self.v_basis, value="today", command=self.set_basis)
        basis.add_radiobutton(label="위젯 켠 뒤부터", variable=self.v_basis, value="launch", command=self.set_basis)
        m.add_cascade(label="금액 세는 기준", menu=basis)
        self.v_tax = tk.BooleanVar(value=bool(self.cfg["after_tax"]))
        m.add_checkbutton(label="세후로 보기", variable=self.v_tax, command=self.set_tax)
        self.v_fx = tk.BooleanVar(value=bool(self.cfg.get("money_fx", True)))
        m.add_checkbutton(label="+원 / -원 떠오르는 효과", variable=self.v_fx, command=self.set_fx)
        alert = tk.Menu(m, tearoff=0, font=font)
        self.v_alert = tk.StringVar(value=str(self.cfg.get("slack_alert", "strong")))
        for val, label in (("strong", "강하게 (빨갛게 깜빡임 + 흔들림)"), ("normal", "보통 (빨갛게 깜빡임)"),
                           ("off", "끄기")):
            alert.add_radiobutton(label=label, variable=self.v_alert, value=val, command=self.set_alert)
        m.add_cascade(label="딴짓할 때 위젯 효과", menu=alert)
        alpha = tk.Menu(m, tearoff=0, font=font)
        for a in (1.0, 0.9, 0.75, 0.5):
            alpha.add_command(label=f"{int(a * 100)}%", command=lambda a=a: self.set_alpha(a))
        m.add_cascade(label="투명도", menu=alpha)
        self.v_top = tk.BooleanVar(value=bool(self.cfg["topmost"]))
        m.add_checkbutton(label="항상 위에 표시", variable=self.v_top, command=self.set_top)
        self.v_mini = tk.BooleanVar(value=bool(self.cfg["mini"]))
        m.add_checkbutton(label="작게 보기", variable=self.v_mini, command=self.toggle_mini)
        m.add_command(label="위치 초기화 (오른쪽 아래로)", command=self.reset_pos)
        m.add_separator()

        m.add_command(label="설정 파일 열기", command=self.open_cfg)
        m.add_command(label="설정 다시 불러오기", command=self.reload)
        self.v_start = tk.BooleanVar(value=os.path.exists(STARTUP))
        m.add_checkbutton(label="Windows 켤 때 자동 실행", variable=self.v_start, command=self.set_startup)
        m.add_separator()
        m.add_command(label="종료", command=self.quit)

    def menu_open(self, ev):
        self.v_mode.set(self.mode)
        try:
            self.menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.menu.grab_release()

    def menu_at(self, ev):
        self.menu_open(ev)

    def set_pomo(self):
        self.cfg["pomodoro"] = bool(self.v_pomo.get())
        self.phase_t = time.time()
        save_json(CFG, self.cfg)

    def set_focus(self):
        if not self.cfg.get("pomodoro"):  # 꺼져 있었으면 켜면서 타이머를 지금부터 시작
            self.phase_t = time.time()
        self.cfg["focus_min"] = int(self.v_focus.get())
        self.cfg["pomodoro"] = True
        self.v_pomo.set(True)
        self.menu.entryconfig(self.pomo_idx, label=self.pomo_label())
        save_json(CFG, self.cfg)

    def set_sound(self):
        self.cfg["sound"] = bool(self.v_sound.get())
        save_json(CFG, self.cfg)

    def set_checkin(self):
        self.cfg["checkin"] = self.v_checkin.get()
        if self.mode == "study" and self.checkin_t0 is None:
            self.schedule_checkin(time.time())
        save_json(CFG, self.cfg)

    def set_slackwarn(self):
        self.cfg["slack_warn"] = bool(self.v_slackwarn.get())
        save_json(CFG, self.cfg)

    def set_idle(self):
        self.cfg["idle_nudge"] = bool(self.v_idle.get())
        save_json(CFG, self.cfg)

    def set_summary(self):
        self.cfg["summary_at"] = self.summary_time if self.v_summary.get() else ""
        save_json(CFG, self.cfg)

    def set_goal(self):
        self.cfg["daily_goal_h"] = float(self.v_goal.get())
        self.log["goal_done"] = False
        save_json(CFG, self.cfg)

    def set_basis(self):
        self.cfg["basis"] = self.v_basis.get()
        self.launch_t = time.time()
        save_json(CFG, self.cfg)

    def set_tax(self):
        self.cfg["after_tax"] = bool(self.v_tax.get())
        self.rates()
        save_json(CFG, self.cfg)

    def set_fx(self):
        self.cfg["money_fx"] = bool(self.v_fx.get())
        save_json(CFG, self.cfg)

    def set_alert(self):
        self.cfg["slack_alert"] = self.v_alert.get()
        save_json(CFG, self.cfg)

    def set_alpha(self, a):
        self.cfg["alpha"] = a
        self.root.attributes("-alpha", 1.0 if self.alert_on else a)  # 딴짓 경고 중에는 끝난 뒤 적용
        save_json(CFG, self.cfg)

    def set_top(self):
        self.cfg["topmost"] = bool(self.v_top.get())
        self.root.attributes("-topmost", True if self.alert_on else self.cfg["topmost"])
        save_json(CFG, self.cfg)

    def open_cfg(self):
        save_json(CFG, self.cfg)
        try:
            subprocess.Popen(["notepad.exe", CFG])
        except Exception:
            try:
                os.startfile(CFG)
            except Exception:
                pass

    def reload(self):
        self.cfg.update(load_json(CFG, {}))
        self.cfg["layout_v"] = LAYOUT_VERSION
        if str(self.cfg.get("summary_at") or "").strip():
            self.summary_time = str(self.cfg["summary_at"]).strip()
        self.v_pomo.set(bool(self.cfg["pomodoro"]))
        self.v_focus.set(f"{num(self.cfg, 'focus_min'):g}")
        self.v_sound.set(bool(self.cfg["sound"]))
        self.v_checkin.set(str(self.cfg.get("checkin", "sometimes")))
        self.v_slackwarn.set(bool(self.cfg.get("slack_warn", True)))
        self.v_idle.set(bool(self.cfg.get("idle_nudge", True)))
        self.v_summary.set(bool(str(self.cfg.get("summary_at") or "").strip()))
        self.noti.entryconfig(self.summary_idx, label=f"오늘 결산 알림 ({self.summary_time})")
        self.v_fx.set(bool(self.cfg.get("money_fx", True)))
        self.v_alert.set(str(self.cfg.get("slack_alert", "strong")))
        self.v_profile.set("work" if self.is_work() else "job")
        if self.mode == "study" and self.checkin_t0 is None:
            self.schedule_checkin(time.time())
        self.v_goal.set(f"{num(self.cfg, 'daily_goal_h'):g}")
        self.v_basis.set(self.cfg["basis"])
        self.v_tax.set(bool(self.cfg["after_tax"]))
        self.v_top.set(bool(self.cfg["topmost"]))
        self.v_mini.set(bool(self.cfg["mini"]))
        self.menu.entryconfig(self.pomo_idx, label=self.pomo_label())
        self.root.attributes("-alpha", num(self.cfg, "alpha"))
        self.root.attributes("-topmost", bool(self.cfg["topmost"]))
        self.rates()
        self.layout()

    def set_startup(self):
        try:
            if self.v_start.get():
                if getattr(sys, "frozen", False):  # exe로 만들어 쓰는 경우
                    line = f'@start "" "{sys.executable}"\n'
                else:
                    exe = sys.executable
                    if exe.lower().endswith("python.exe"):
                        exe = exe[:-10] + "pythonw.exe"
                    line = f'@start "" "{exe}" "{os.path.abspath(__file__)}"\n'
                with open(STARTUP, "w", encoding="mbcs") as f:
                    f.write(line)
            elif os.path.exists(STARTUP):
                os.remove(STARTUP)
        except Exception:
            pass
        self.v_start.set(os.path.exists(STARTUP))

    def quit(self):
        self.flush()
        save_json(CFG, self.cfg)
        self.close_toast()
        self.root.destroy()

    # ---------- 숫자 · 목표 설정 창 ----------
    # (라벨, 키, 종류) / 키가 None이면 소제목. "c0.name"은 companies[0]["name"], "#study"는 오늘 기록(분)
    MONEY_ROWS = {
        "job": (
            ("목표 회사 1", None, None),
            ("이름", "c0.name", "text"),
            ("연봉 (만원)", "c0.salary_manwon", "num"),
            ("성과급 (억원/년)", "c0.bonus_eok", "num"),
            ("목표 회사 2", None, None),
            ("이름", "c1.name", "text"),
            ("연봉 (만원)", "c1.salary_manwon", "num"),
            ("성과급 (억원/년)", "c1.bonus_eok", "num"),
            ("성과급 계산기 · 영업이익 × 비율 ÷ 직원 수", None, None),
            ("영업이익 (조원/년)", "hynix_op_jo", "num"),
            ("성과급 비율 (%)", "hynix_ps_pct", "num"),
            ("직원 수 (명)", "hynix_headcount", "int"),
        ),
        "work": (
            ("내 월급", None, None),
            ("내 연봉 (성과급 포함, 만원/년)", "work_salary_manwon", "num"),
            ("출근 시각 (예: 09:00)", "work_start", "time"),
            ("퇴근 시각 (예: 18:00)", "work_end", "time"),
            ("점심시간 (예: 12:00-13:00)", "work_lunch", "lunch"),
            ("근무 요일 (예: 월화수목금)", "work_days", "days"),
            ("월급날 (1~31, 없으면 0)", "payday", "day"),
            ("이직 목표 (없으면 비워두세요)", None, None),
            ("목표 회사 이름", "target_name", "text"),
            ("목표 회사 연봉 + 성과급 (만원/년)", "target_manwon", "num"),
        ),
    }
    GOAL_ROWS = (
        ("목표", None, None),
        ("하루 목표 공부 (시간)", "daily_goal_h", "goal"),
        ("D-day 이름 (예: 졸업)", "dday_label", "text"),
        ("D-day 날짜 (예: 2027-08-31)", "dday_date", "date"),
        ("오늘 기록 고치기 (분)", None, None),
        ("공부", "#study", "min"),
        ("휴식", "#break", "min"),
        ("딴짓", "#slack", "min"),
    )
    ERRORS = {
        "num": "숫자를 확인해주세요. 쉼표 없이 0 이상의 숫자만 넣으면 돼요.",
        "int": "직원 수는 1 이상의 정수로 넣어주세요.",
        "goal": "하루 목표는 0.5시간 이상으로 넣어주세요.",
        "time": "출근·퇴근 시각은 09:00처럼 넣어주세요. 퇴근이 출근보다 늦어야 해요.",
        "lunch": "점심시간은 12:00-13:00처럼 넣거나 비워두세요.",
        "days": "근무 요일은 월화수목금처럼 요일 글자로 넣어주세요.",
        "day": "월급날은 1~31 사이 숫자로 넣어주세요. 없으면 0이에요.",
        "date": "D-day 날짜는 2027-08-31처럼 넣어주세요. 비워두면 D-day를 숨겨요.",
        "min": "오늘 기록은 0 이상의 분 단위 숫자로 넣어주세요.",
    }

    def cfg_get(self, key):
        if key.startswith("c") and "." in key:
            i, field = key[1:].split(".", 1)
            return self.companies()[int(i)][field]
        return self.cfg.get(key, "")

    def open_settings(self, *_):
        if self.swin is not None and self.swin.winfo_exists():
            self.swin.lift()
            return
        p = self.p
        win = self.swin = tk.Toplevel(self.root)
        win.title("숫자 · 목표 설정")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        frm = tk.Frame(win, bg=BG, padx=p(18), pady=p(14))
        frm.pack()
        self.st = {"lab": dict(bg=BG, fg=MUTED, font=self.f(UI, 10), anchor="w"),
                   "head": dict(bg=BG, fg=FG, font=self.f(UI, 11, "bold"), anchor="w"),
                   "ent": dict(bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=self.f(UI, 11),
                               width=12, highlightthickness=1, highlightbackground=LINE, highlightcolor=SAM,
                               justify="right"),
                   "btn": dict(relief="flat", bd=0, font=self.f(UI, 10), padx=p(16), pady=p(5), cursor="hand2")}
        self.sv, self.sv0, self.skind = {}, {}, {}

        # 사용 방식
        top = tk.Frame(frm, bg=BG)
        top.grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(top, text="사용 방식", **self.st["head"]).pack(side="left", padx=(0, p(14)))
        self.s_profile = tk.StringVar(value="work" if self.is_work() else "job")
        for val, label in (("job", "취업 준비 (목표 회사 두 곳)"), ("work", "직장인 (내 월급 + 이직 목표)")):
            tk.Radiobutton(top, text=label, value=val, variable=self.s_profile, command=self.settings_money,
                           bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                           font=self.f(UI, 10), bd=0, highlightthickness=0).pack(side="left", padx=(0, p(12)))
        self.s_desc = tk.Label(frm, text="", bg=BG, fg=DIM, font=self.f(UI, 9), anchor="w", justify="left")
        self.s_desc.grid(row=1, column=0, columnspan=3, sticky="w", pady=(p(4), p(6)))

        self.s_left = tk.Frame(frm, bg=BG)
        self.s_left.grid(row=2, column=0, sticky="nw")
        tk.Frame(frm, bg=LINE, width=1).grid(row=2, column=1, sticky="ns", padx=p(18))
        right = tk.Frame(frm, bg=BG)
        right.grid(row=2, column=2, sticky="nw")
        self.settings_rows(right, self.GOAL_ROWS)
        self.settings_money()

        self.serr = tk.Label(frm, text="", bg=BG, fg=BAD, font=self.f(UI, 10), anchor="w",
                             justify="left", wraplength=p(560))
        self.serr.grid(row=3, column=0, columnspan=3, sticky="w", pady=(p(10), 0))
        bar = tk.Frame(frm, bg=BG)
        bar.grid(row=4, column=0, columnspan=3, sticky="e", pady=(p(8), 0))
        tk.Button(bar, text="취소", command=win.destroy, bg=PANEL, fg=FG,
                  activebackground=PANEL_H, activeforeground=FG, **self.st["btn"]).pack(side="right")
        tk.Button(bar, text="저장", command=self.save_settings, bg=SAM, fg=DARK,
                  activebackground=SAM, activeforeground=DARK, **self.st["btn"]).pack(side="right", padx=(0, p(8)))
        self.place_dialog(win)

    def place_dialog(self, win):
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x, y = self.clamp(self.root.winfo_x() + self.root.winfo_width() - w,
                          self.root.winfo_y() - h - self.p(48), w, h)
        win.geometry(f"+{x}+{y}")

    def settings_rows(self, parent, rows):
        p, st = self.p, self.st
        tot = self.today_totals()
        for r, (label, key, kind) in enumerate(rows):
            if key is None:
                tk.Label(parent, text=label, **st["head"]).grid(row=r, column=0, columnspan=2, sticky="w",
                                                                pady=(p(10) if r else 0, p(3)))
                continue
            tk.Label(parent, text=label, **st["lab"]).grid(row=r, column=0, sticky="w", pady=p(2))
            val = f"{tot[key[1:]] / 60:.0f}" if key.startswith("#") else fmt_val(self.cfg_get(key))
            var = tk.StringVar(value=val)
            self.sv[key], self.sv0[key], self.skind[key] = var, val, kind
            ent = dict(st["ent"], justify="left") if kind in ("text", "days", "lunch") else st["ent"]
            tk.Entry(parent, textvariable=var, **ent).grid(row=r, column=1, sticky="e", padx=(p(12), 0), pady=p(2))
        return len(rows)

    def settings_money(self):
        """사용 방식에 맞는 돈 계산 칸으로 왼쪽을 다시 그림 (오른쪽 목표 칸은 그대로)"""
        prof = self.s_profile.get()
        for wdg in self.s_left.winfo_children():
            wdg.destroy()
        for key in [k for k in self.sv if not k.startswith("#") and k not in dict(
                (r[1], 1) for r in self.GOAL_ROWS)]:
            for d in (self.sv, self.sv0, self.skind):
                d.pop(key, None)
        n = self.settings_rows(self.s_left, self.MONEY_ROWS[prof])
        if prof == "job":
            tk.Button(self.s_left, text="계산해서 회사 2 성과급에 넣기", command=self.calc_bonus, bg=PANEL, fg=FG,
                      activebackground=PANEL_H, activeforeground=FG, **self.st["btn"]).grid(
                row=n, column=0, columnspan=2, sticky="e", pady=(self.p(6), 0))
            self.s_desc.config(text="가고 싶은 회사 두 곳의 연봉 + 성과급이 하루 종일 1초씩 쌓여요. "
                                    "공부·딴짓 금액은 두 회사 평균으로 계산해요.")
        else:
            self.s_desc.config(text="내 월급이 근무 시간에만 1초씩 쌓여요. 이직 목표를 넣으면 둘째 줄에 "
                                    "'이직하면 더 받는 돈'이 쌓이고, 공부·딴짓 금액도 그 차액으로 계산해요.")
        if self.swin is not None and self.swin.winfo_exists():
            self.place_dialog(self.swin)

    def calc_bonus(self):
        try:
            op = float(self.sv["hynix_op_jo"].get().replace(",", ""))
            pct = float(self.sv["hynix_ps_pct"].get().replace(",", ""))
            head = float(self.sv["hynix_headcount"].get().replace(",", ""))
            if op < 0 or pct < 0 or head < 1:
                raise ValueError
        except ValueError:
            self.serr.config(text="성과급 계산기 칸에 숫자를 넣어주세요. 직원 수는 1 이상이어야 해요.")
            return
        self.sv["c1.bonus_eok"].set(f"{op * 1e12 * pct / 100 / head / 1e8:.2f}")
        self.serr.config(text="")

    def parse_field(self, kind, raw):
        """칸 하나를 검사해서 저장할 값으로 바꿈. 잘못되면 ValueError"""
        s = raw.replace(",", "").strip() if kind in ("num", "int", "goal", "day", "min") else raw.strip()
        if kind == "text":
            return s
        if kind == "num":
            v = float(s)
            if v < 0:
                raise ValueError
            return v
        if kind == "int":
            v = int(float(s))
            if v < 1:
                raise ValueError
            return v
        if kind == "goal":
            v = float(s)
            if v < 0.5:
                raise ValueError
            return v
        if kind == "time":
            if self.hhmm(s) is None:
                raise ValueError
            return s
        if kind == "lunch":
            if not s:
                return ""
            a, b = (self.hhmm(x) for x in s.split("-", 1)) if "-" in s else (None, None)
            if a is None or b is None or a >= b:
                raise ValueError
            return s
        if kind == "days":
            days = "".join(ch for ch in "월화수목금토일" if ch in s)
            if not days:
                raise ValueError
            return days
        if kind == "day":
            v = int(float(s or 0))
            if not 0 <= v <= 31:
                raise ValueError
            return v
        if kind == "date":
            if s:
                dt.date.fromisoformat(s)
            return s
        if kind == "min":
            v = float(s)
            if v < 0:
                raise ValueError
            return v
        return s

    def save_settings(self):
        vals, mins = {}, {}
        for key, var in self.sv.items():
            kind = self.skind[key]
            if kind == "min" and var.get() == self.sv0[key]:
                continue  # 바꾼 칸만 오늘 기록에 반영
            try:
                v = self.parse_field(kind, var.get())
            except ValueError:
                self.serr.config(text=self.ERRORS.get(kind, self.ERRORS["num"]))
                return
            (mins if kind == "min" else vals)[key[1:] if kind == "min" else key] = v
        if "work_start" in vals and self.hhmm(vals["work_end"]) <= self.hhmm(vals["work_start"]):
            self.serr.config(text=self.ERRORS["time"])
            return
        cos = self.companies()
        for key in [k for k in vals if k.startswith("c") and "." in k]:
            i, field = key[1:].split(".", 1)
            cos[int(i)][field] = vals.pop(key) or (f"회사 {int(i) + 1}" if field == "name" else 0)
        self.cfg["companies"] = cos
        self.cfg.update(vals)
        self.cfg["profile"] = self.s_profile.get()
        self.v_profile.set(self.cfg["profile"])
        self.flush()
        for k, v in mins.items():
            self.log[k] = v * 60
        if self.log["study"] < num(self.cfg, "daily_goal_h") * 3600:
            self.log["goal_done"] = False
        self.v_goal.set(f"{num(self.cfg, 'daily_goal_h'):g}")
        self.rates()
        self.flush()
        self.layout()
        self.swin.destroy()

    def set_profile(self):
        self.cfg["profile"] = self.v_profile.get()
        self.rates()
        self.layout()
        if self.is_work() and not self.cfg.get("work_seen"):
            self.cfg["work_seen"] = True
            save_json(CFG, self.cfg)
            self.toast("직장인 모드", "내 연봉과 출퇴근 시각을 넣으면 근무 시간에 월급이 1초씩 쌓여요. "
                                   "이직 목표 회사도 넣을 수 있어요.", SAM,
                       buttons=(("설정 열기", self.open_settings), ("나중에", lambda: None)),
                       kind="info", timeout=None, sound=1)

    def welcome(self):
        self.toast("반가워요!", "우클릭 → 숫자 · 목표 설정에서 취업 준비 / 직장인 중 내 상황을 고르고, "
                             "회사와 연봉을 바꿀 수 있어요.", SAM,
                   buttons=(("설정 열기", self.open_settings), ("나중에", lambda: None)),
                   kind="info", timeout=None, sound=1)

    # ---------- 공부 활동: 켜진 시간 대비 공부 (일별 · 주간 · 누적) ----------
    def day_stats(self, iso):
        if iso == self.log["day"]:
            tot, on = self.today_totals(), float(self.log.get("on", 0.0))
        else:
            hday = self.hist.get(iso)
            if not hday:
                return None
            tot = {k: float(hday.get(k, 0) or 0) for k in KINDS}
            on = float(hday.get("on", 0) or 0)
        on = max(on, sum(tot.values()))  # 기록된 시간만큼은 켜져 있었던 것
        if on < 60:
            return None
        return dict(tot, on=on, ratio=min(1.0, tot["study"] / on))

    def ratio_over(self, days):
        s = o = 0.0
        for d in days:
            st = self.day_stats(d.isoformat())
            if st:
                s, o = s + st["study"], o + st["on"]
        return (s / o if o > 0 else None), s, o

    @staticmethod
    def heat_color(st):
        if not st or st["study"] < 60:
            return HEAT_EMPTY
        for i, b in enumerate(HEAT_BINS):
            if st["ratio"] < b:
                return HEAT[i]
        return HEAT[-1]

    @staticmethod
    def day_tip(d, st):
        head = f"{d.month}월 {d.day}일 ({'월화수목금토일'[d.weekday()]})"
        if not st:
            return f"{head} · 기록 없음"
        return f"{head} · 공부 {hm(st['study'])} / 켜짐 {hm(st['on'])} · {int(st['ratio'] * 100)}%"

    def show_activity(self):
        self.flush()
        if self.awin is not None and self.awin.winfo_exists():
            self.awin.lift()
            self.draw_activity()
            return
        p = self.p
        w, h = p(880), p(266)
        win = self.awin = tk.Toplevel(self.root)
        win.title("공부 활동")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        c = self.ac = tk.Canvas(win, width=w, height=h, bg=BG, highlightthickness=0)
        c.pack()
        self.act_size = (w, h)
        x, y = self.clamp(self.root.winfo_x() + self.root.winfo_width() - w,
                          self.root.winfo_y() - h - p(48), w, h)
        win.geometry(f"+{x}+{y}")
        c.bind("<Motion>", self.act_motion)
        c.bind("<Leave>", lambda e: self.act_hover(None))
        self.draw_activity()

    def set_act_tab(self, key):
        self.act_tab = key
        self.draw_activity()

    def draw_activity(self):
        c, p = self.ac, self.p
        w, h = self.act_size
        c.delete("all")
        self.act_hits, self.act_cum, self.act_hl = [], None, None
        today = dt.date.today()
        c.create_text(p(20), p(24), text="공부 활동", anchor="w", font=self.f(UI, 13, "bold"), fill=FG)
        x = w - p(20)
        for key, label in (("cum", "누적"), ("week", "주간"), ("day", "일별")):  # 오른쪽부터 배치
            on = key == self.act_tab
            tag = "tab_" + key
            t = c.create_text(x, p(24), text=label, anchor="e", fill=FG if on else MUTED, tags=(tag,),
                              font=self.f(UI, 11, "bold") if on else self.f(UI, 11))
            bb = c.bbox(t)
            if on:
                tw = max(bb[2] - bb[0], self.est_w(label, 11))
                c.create_line(x - tw, bb[3] + p(3), x, bb[3] + p(3), fill=HEAT[3], width=max(1, p(2)))
            c.tag_bind(tag, "<Button-1>", lambda e, k=key: self.set_act_tab(k))
            c.tag_bind(tag, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda e: c.config(cursor=""))
            x -= max(bb[2] - bb[0], self.est_w(label, 11)) + p(18)  # 글꼴 측정이 어긋나도 탭끼리 안 겹치게

        st = self.day_stats(today.isoformat())
        r7, _, _ = self.ratio_over([today - dt.timedelta(days=i) for i in range(7)])
        r30, s30, o30 = self.ratio_over([today - dt.timedelta(days=i) for i in range(30)])
        pct = lambda r: "—" if r is None else f"{int(r * 100)}%"
        c.create_text(p(20), p(50), anchor="w", font=self.f(UI, 11), fill=FG,
                      text=f"켜진 시간 중 공부 · 오늘 {pct(st['ratio'] if st else None)} · 최근 7일 {pct(r7)}"
                           f" · 최근 30일 {pct(r30)} (켜짐 {hm(o30)} 중 공부 {hm(s30)})")
        c.create_text(p(20), p(70), anchor="w", font=self.f(UI, 9), fill=DIM,
                      text="켜진 시간은 이 위젯이 켜져 있던 시간이에요 (절전·잠자기 제외). "
                           "Windows 켤 때 자동 실행을 켜두면 컴퓨터가 켜진 시간과 같아요.")
        {"day": self.draw_heat, "week": self.draw_weeks, "cum": self.draw_cumul}[self.act_tab](c, p(96), w, h)

    def draw_heat(self, c, top, w, h):
        p = self.p
        cell, pitch, weeks, left = p(12), p(15), 53, p(44)
        today = dt.date.today()
        start = today - dt.timedelta(days=today.weekday() + 7 * (weeks - 1))  # 53주 전 월요일
        for wk in range(weeks):
            for wd in range(7):
                d = start + dt.timedelta(days=wk * 7 + wd)
                if d > today:
                    break
                st = self.day_stats(d.isoformat())
                x1, y1 = left + wk * pitch, top + wd * pitch
                rid = self.round_rect(x1, y1, x1 + cell, y1 + cell, p(3), canvas=c,
                                      fill=self.heat_color(st), outline="")
                self.act_hits.append((x1, y1, x1 + cell, y1 + cell, self.day_tip(d, st), [rid], "cell"))
        for wd, name in ((0, "월"), (2, "수"), (4, "금")):
            c.create_text(left - p(8), top + wd * pitch + cell / 2, text=name, anchor="e",
                          font=self.f(UI, 9), fill=MUTED)
        ylab = top + 7 * pitch + p(8)
        for wk in range(weeks):
            for wd in range(7):
                d = start + dt.timedelta(days=wk * 7 + wd)
                if d.day == 1 and d <= today:
                    c.create_text(left + wk * pitch, ylab, text=f"{d.month}월", anchor="nw",
                                  font=self.f(UI, 9), fill=MUTED)
        # 범례: 0% [빈칸][20% 미만][20~40%][40~60%][60% 이상] 60%+
        ly = ylab + p(30)
        x = left + weeks * pitch - (pitch - cell)  # 마지막 칸의 오른쪽 끝
        t = c.create_text(x, ly, text="60% 이상", anchor="e", font=self.f(UI, 9), fill=MUTED)
        bb = c.bbox(t)
        x -= max(bb[2] - bb[0], self.est_w("60% 이상", 9)) + p(6)
        ranges = ("60% 이상", "40~60%", "20~40%", "20% 미만", "공부 없음")
        for color, label in zip((HEAT[3], HEAT[2], HEAT[1], HEAT[0], HEAT_EMPTY), ranges):
            rid = self.round_rect(x - cell, ly - cell / 2, x, ly + cell / 2, p(3), canvas=c, fill=color, outline="")
            self.act_hits.append((x - cell, ly - cell / 2, x, ly + cell / 2, f"켜진 시간 중 공부 {label}", [rid], "cell"))
            x -= pitch
        c.create_text(x + pitch - cell - p(6), ly, text="0%", anchor="e", font=self.f(UI, 9), fill=MUTED)
        c.create_text(left, ly, text="칸에 마우스를 올리면 그날 기록이 보여요", anchor="w",
                      font=self.f(UI, 9), fill=DIM)

    def draw_weeks(self, c, top, w, h):
        p = self.p
        n = 26
        today = dt.date.today()
        monday = today - dt.timedelta(days=today.weekday())
        x0, x1 = p(56), w - p(24)
        y0, y1 = top + p(4), top + p(118)
        for frac in (0, 0.25, 0.5, 0.75, 1.0):
            y = y1 - (y1 - y0) * frac
            c.create_line(x0, y, x1, y, fill=DIM if frac == 0 else LINE)
            c.create_text(x0 - p(8), y, text=f"{int(frac * 100)}%", anchor="e", font=self.f(MONO, 9), fill=MUTED)
        slot = (x1 - x0) / n
        bw = min(p(18), slot - p(4))
        last = None
        for i in range(n):
            ws = monday - dt.timedelta(weeks=n - 1 - i)
            we = ws + dt.timedelta(days=6)
            r, s, o = self.ratio_over([ws + dt.timedelta(days=k) for k in range(7)
                                       if ws + dt.timedelta(days=k) <= today])
            cx = x0 + slot * (i + 0.5)
            tip = f"{ws.month}/{ws.day} ~ {we.month}/{we.day} · " + (
                f"공부 {hm(s)} / 켜짐 {hm(o)} · {int(r * 100)}%" if r is not None else "기록 없음")
            items = []
            if r:
                bh = max(p(2), (y1 - y0) * r)
                items.append(self.round_rect(cx - bw / 2, y1 - bh, cx + bw / 2, y1, min(p(4), bh / 2),
                                             canvas=c, fill=HEAT[2], outline=""))
                items.append(c.create_rectangle(cx - bw / 2, y1 - min(bh, p(4)), cx + bw / 2, y1,
                                                fill=HEAT[2], outline=""))  # 바닥 쪽은 각지게
                last = (i, r, cx, y1 - bh)
            self.act_hits.append((cx - slot / 2, y0, cx + slot / 2, y1, tip, items, "bar"))
            for k in range(7):
                d = ws + dt.timedelta(days=k)
                if d.day == 1:
                    c.create_text(cx, y1 + p(14), text=f"{d.month}월", font=self.f(UI, 9), fill=MUTED)
        if last and last[0] == n - 1:  # 이번 주 값만 직접 표시
            c.create_text(last[2], last[3] - p(8), text=f"{int(last[1] * 100)}%",
                          font=self.f(MONO, 9, "bold"), fill=FG)
        c.create_text(x0, y1 + p(34), anchor="w", font=self.f(UI, 9), fill=DIM,
                      text="주마다 켜진 시간 중 공부한 비율 · 막대에 마우스를 올리면 자세히 보여요")

    def draw_cumul(self, c, top, w, h):
        p = self.p
        today = dt.date.today()
        studied = sorted(d for d, v in self.hist.items() if v.get("study", 0) > 0)
        first = dt.date.fromisoformat(studied[0]) if studied else today
        first = min(first, today - dt.timedelta(days=13))  # 최소 2주 폭
        n = (today - first).days + 1
        x0, x1 = p(56), w - p(24)
        y0, y1 = top + p(4), top + p(118)
        cum, totals, tips = 0.0, [], []
        for i in range(n):
            d = first + dt.timedelta(days=i)
            st = self.day_stats(d.isoformat())
            day_s = st["study"] if st else 0.0
            cum += day_s
            totals.append(cum)
            tips.append(f"{d.month}/{d.day} · 누적 공부 {hm(cum)} · 이날 {hm(day_s)}"
                        + (f" (켜진 시간의 {int(st['ratio'] * 100)}%)" if st else ""))
        top_h = max(1.0, totals[-1] / 3600)
        step = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000) if top_h / s <= 4)
        ymax = math.ceil(top_h / step) * step
        for k in range(int(ymax / step) + 1):
            v = k * step
            y = y1 - (y1 - y0) * v / ymax
            c.create_line(x0, y, x1, y, fill=DIM if k == 0 else LINE)
            c.create_text(x0 - p(8), y, text=f"{v:g}h", anchor="e", font=self.f(MONO, 9), fill=MUTED)
        xs = [x0 + (x1 - x0) * (i / max(1, n - 1)) for i in range(n)]
        ys = [y1 - (y1 - y0) * (t / 3600) / ymax for t in totals]
        line = [v for xy in zip(xs, ys) for v in xy]
        c.create_polygon([x0, y1] + line + [xs[-1], y1], fill=mix(HEAT[1], BG, 0.55), outline="")
        if n >= 2:
            c.create_line(*line, fill=HEAT[3], width=max(1, p(2)))
        c.create_oval(xs[-1] - p(4), ys[-1] - p(4), xs[-1] + p(4), ys[-1] + p(4), fill=HEAT[3],
                      outline=BG, width=max(1, p(2)))
        c.create_text(xs[-1] - p(8), ys[-1] - p(10), text=hm(totals[-1]), anchor="e",
                      font=self.f(MONO, 10, "bold"), fill=FG)
        for i, anchor in ((0, "w"), (n // 2, "center"), (n - 1, "e")):
            d = first + dt.timedelta(days=i)
            c.create_text(xs[i], y1 + p(14), text=f"{d.month}/{d.day}", anchor=anchor,
                          font=self.f(MONO, 9), fill=MUTED)
        c.create_text(x0, y1 + p(34), anchor="w", font=self.f(UI, 9), fill=DIM,
                      text=f"지금까지 공부 {hm(totals[-1])} · 공부로 지킨 돈 {man(totals[-1] * self.avg())}"
                           " · 그래프에 마우스를 올리면 날짜별로 보여요")
        self.act_cum = (xs, ys, tips, y0, y1)

    def act_motion(self, e):
        if self.act_tab == "cum":
            self.cum_hover(e.x)
            return
        hit = next((hh for hh in self.act_hits
                    if hh[0] - 1 <= e.x <= hh[2] + 1 and hh[1] - 1 <= e.y <= hh[3] + 1), None)
        if hit is not self.act_hl:
            self.act_hover(hit)

    def act_hover(self, hit):
        c = self.ac
        if self.act_hl:
            for i in self.act_hl[5]:
                if self.act_hl[6] == "cell":
                    c.itemconfig(i, outline="")
                else:
                    c.itemconfig(i, fill=HEAT[2])
        self.act_hl = hit
        c.delete("tip")
        if not hit:
            return
        x1, y1, x2, y2, tip, items, kind = hit
        for i in items:
            if kind == "cell":
                c.itemconfig(i, outline=FG, width=1)
            else:
                c.itemconfig(i, fill=HEAT[3])
        self.act_tip(tip, (x1 + x2) / 2, y1 - self.p(6))

    def cum_hover(self, x):
        c, p = self.ac, self.p
        c.delete("tip")
        if not self.act_cum:
            return
        xs, ys, tips, y0, y1 = self.act_cum
        if x < xs[0] - p(12) or x > xs[-1] + p(12):
            return
        i = min(range(len(xs)), key=lambda k: abs(xs[k] - x))
        c.create_line(xs[i], y0, xs[i], y1, fill=MUTED, dash=(2, 3), tags=("tip",))
        c.create_oval(xs[i] - p(4), ys[i] - p(4), xs[i] + p(4), ys[i] + p(4), fill=HEAT[3], outline=FG,
                      tags=("tip",))
        self.act_tip(tips[i], xs[i], y0 - p(4))

    def act_tip(self, text, x, y):
        """마우스를 올린 칸 위에 뜨는 작은 설명 상자 (창 밖으로 나가지 않게)"""
        c, p = self.ac, self.p
        w, _ = self.act_size
        t = c.create_text(x, y, text=text, anchor="s", font=self.f(UI, 10), fill=FG, tags=("tip",))
        bb = c.bbox(t)
        half = max(bb[2] - bb[0], self.est_w(text, 10)) / 2
        cx = min(max(x, p(12) + half), w - p(12) - half)
        c.coords(t, cx, y)
        bb = c.bbox(t)
        box = self.round_rect(cx - half - p(8), bb[1] - p(5), cx + half + p(8), bb[3] + p(5), p(6), canvas=c,
                              fill=TIP_BG, outline=LINE, tags=("tip",))
        c.tag_raise(t, box)

    # ---------- 최근 7일 기록 ----------
    def streak(self):
        def studied(day):
            return self.hist.get(day.isoformat(), {}).get("study", 0) >= 3600
        d = dt.date.today()
        if not studied(d):  # 오늘 아직 1시간 전이면 어제부터 셈
            d -= dt.timedelta(days=1)
        n = 0
        while studied(d):
            n += 1
            d -= dt.timedelta(days=1)
        return n

    def show_history(self):
        self.flush()
        if self.hwin is not None and self.hwin.winfo_exists():
            self.hwin.destroy()
        p = self.p
        w, h = p(360), p(272)
        win = self.hwin = tk.Toplevel(self.root)
        win.title("최근 7일 공부 기록")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        x, y = self.clamp(self.root.winfo_x() + self.root.winfo_width() - w,
                          self.root.winfo_y() - h - p(48), w, h)
        win.geometry(f"{w}x{h}+{x}+{y}")
        c = tk.Canvas(win, width=w, height=h, bg=BG, highlightthickness=0)
        c.pack()

        days = [dt.date.today() - dt.timedelta(days=i) for i in range(6, -1, -1)]
        vals = [self.hist.get(d.isoformat(), {}).get("study", 0) / 3600 for d in days]
        slack = sum(self.hist.get(d.isoformat(), {}).get("slack", 0) for d in days)
        study_all = sum(v.get("study", 0) for v in self.hist.values())
        slack_all = sum(v.get("slack", 0) for v in self.hist.values())
        goal = max(0.1, num(self.cfg, "daily_goal_h"))
        avg = self.avg()
        total = sum(vals) * 3600

        c.create_text(p(16), p(20), anchor="w", font=self.f(UI, 11), fill=FG,
                      text=f"7일 공부 {hm(total)} · 하루 평균 {hm(total / 7)} · 연속 {self.streak()}일")
        c.create_text(p(16), p(41), anchor="w", font=self.f(UI, 10), fill=GOOD,
                      text=f"공부로 지킨 돈 · 7일 {man(total * avg)} · 지금까지 {man(study_all * avg)}")
        c.create_text(p(16), p(60), anchor="w", font=self.f(UI, 10), fill=BAD,
                      text=f"딴짓으로 흘러간 돈 · 7일 {man(slack * avg)} · 지금까지 {man(slack_all * avg)}")

        top = max([goal] + vals) * 1.15
        base, height = p(212), p(115)
        right = w - p(58)  # 오른쪽 여백에 목표선 이름을 둠
        slot = (right - p(16)) / 7
        gy = base - goal / top * height
        c.create_line(p(16), gy, right, gy, fill=DIM, dash=(3, 3))
        c.create_text(right + p(6), gy, text=f"목표 {goal:g}시간", anchor="w", font=self.f(UI, 9), fill=DIM)
        for i, (d, v) in enumerate(zip(days, vals)):
            cx = p(16) + slot * (i + 0.5)
            bh = v / top * height
            color = GOLD if v >= goal else (GOOD if v > 0 else LINE)
            c.create_rectangle(cx - p(11), base - max(bh, p(2)), cx + p(11), base, fill=color, outline="")
            if v > 0:
                c.create_text(cx, base - bh - p(9), text=hm(v * 3600), font=self.f(MONO, 9), fill=FG)
            c.create_text(cx, base + p(14), text=f"{d.month}/{d.day}", font=self.f(MONO, 9), fill=MUTED)
            c.create_text(cx, base + p(28), text="오늘" if i == 6 else "월화수목금토일"[d.weekday()],
                          font=self.f(UI, 9), fill=FG if i == 6 else MUTED)


if __name__ == "__main__":
    Meter()
