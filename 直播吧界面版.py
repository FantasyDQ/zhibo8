# -*- coding: utf-8 -*-
"""
NBA 实时战报 v8
- PNG 队徽：中文文件名，直接匹配
- 战报滚屏：自上而下
- 去重：已播报的 live_text id 不再重复插入
- 语音播报：pyttsx3 / Windows SAPI，可开关
"""

import requests, time, datetime, re, os
import tkinter as tk
from tkinter import ttk, messagebox
from threading import Thread
import queue as _queue
import asyncio as _asyncio
import tempfile as _tempfile
import threading as _threading

# ── 语音：edge-tts 微软神经网络语音，pip install edge-tts ──
try:
    import edge_tts as _edge_tts
    import pygame as _pygame
    _pygame.mixer.init()
    TTS_OK = True
except ImportError:
    TTS_OK = False

# 可选音色列表（在按钮菜单里切换）
TTS_VOICES = {
    '云扬（男·播报）': 'zh-CN-YunyangNeural',
    '晓晓（女·温柔）': 'zh-CN-XiaoxiaoNeural',
    '云希（男·低沉）': 'zh-CN-YunxiNeural',
    '晓伊（女·活泼）': 'zh-CN-XiaoyiNeural',
}
_tts_voice  = 'zh-CN-XiaoyiNeural'    # 默认晓伊
_tts_on     = False
_tts_queue: _queue.Queue = _queue.Queue(maxsize=6)
_tts_proc   = None

def _run_tts(text: str, voice: str):
    """联网合成 mp3，返回文件路径；失败返回 None。"""
    try:
        tmp = _tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        tmp.close()
        path = tmp.name
        async def _gen():
            # rate=+50% 语速加快，不跟不上文字
            comm = _edge_tts.Communicate(text, voice, rate='+30%')
            await comm.save(path)
        loop = _asyncio.new_event_loop()
        loop.run_until_complete(_gen())
        loop.close()
        return path
    except Exception as e:
        print(f'[tts] 合成失败: {e}')
        return None

def _tts_worker():
    """
    双缓冲流水线：
      合成线程（_prefetch_worker）提前把下一条 mp3 准备好放入 _play_queue，
      播放线程（本函数）从 _play_queue 取文件直接播，
      两者并行 → 合成延迟被播放时间掩盖，基本做到无缝衔接。
    """
    if not TTS_OK:
        return
    while True:
        item = _play_queue.get()
        if item is None:
            break
        path, should_play = item
        if should_play and _tts_on and path:
            try:
                _pygame.mixer.music.stop()
                _pygame.mixer.music.load(path)
                _pygame.mixer.music.play()
                while _pygame.mixer.music.get_busy():
                    _threading.Event().wait(0.05)
            except Exception as e:
                print(f'[tts] 播放失败: {e}')
        try:
            import os; os.unlink(path)
        except: pass
        _play_queue.task_done()

def _prefetch_worker():
    """预取线程：从 _tts_queue 拿文本 → 合成 mp3 → 放入 _play_queue。"""
    while True:
        text = _tts_queue.get()
        if text is None:
            _play_queue.put(None)
            break
        path = _run_tts(text, _tts_voice) if _tts_on else None
        _play_queue.put((path, _tts_on))
        _tts_queue.task_done()

_play_queue: _queue.Queue = _queue.Queue(maxsize=4)
Thread(target=_prefetch_worker, daemon=True).start()

_tts_thread = Thread(target=_tts_worker, daemon=True)
_tts_thread.start()

def _tts_say(text: str):
    if not _tts_on or not TTS_OK:
        return
    # 积压时丢旧留新
    while _tts_queue.full():
        try: _tts_queue.get_nowait()
        except: break
    try: _tts_queue.put_nowait(text)
    except: pass

# ══════════════════════════════════════════════════════
#  PNG Logo（中文文件名，直接匹配）
# ══════════════════════════════════════════════════════
ICON_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon')
_logo_cache: dict = {}

# 队名关键字 → 文件名（不含.png），文件名就是中文队名
TEAM_LOGO_MAP = {
    '76人':  '76人',
    '公牛':  '公牛',
    '凯尔特人': '凯尔特人',
    '勇士':  '勇士',
    '国王':  '国王',
    '太阳':  '太阳',
    '奇才':  '奇才',
    '华盛顿': '奇才',   # 同一队，别名
    '尼克斯': '尼克斯',
    '开拓者': '开拓者',
    '快船':  '快船',
    '掘金':  '掘金',
    '森林狼': '森林狼',
    '明尼苏达': '森林狼',
    '步行者': '步行者',
    '活塞':  '活塞',
    '湖人':  '湖人',
    '火箭':  '火箭',
    '灰熊':  '灰熊',
    '热火':  '热火',
    '爵士':  '爵士',
    '独行侠': '独行侠',
    '小牛':  '独行侠',
    '猛龙':  '猛龙',
    '篮网':  '篮网',
    '老鹰':  '老鹰',
    '雄鹿':  '雄鹿',
    '雷霆':  '雷霆',
    '马刺':  '马刺',
    '骑士':  '骑士',
    '魔术':  '魔术',
    '鹈鹕':  '鹈鹕',
    '黄蜂':  '黄蜂',
}

def _load_logo(team_name: str) -> 'tk.PhotoImage | None':
    if team_name in _logo_cache:
        return _logo_cache[team_name]

    stem = None
    for key, val in TEAM_LOGO_MAP.items():
        if key in team_name:
            stem = val
            break

    # 兜底：直接用队名本身查文件
    if stem is None:
        stem = team_name

    path = os.path.join(ICON_DIR, stem + '.png')
    if not os.path.exists(path):
        print(f'[logo] 文件不存在: {path}')
        _logo_cache[team_name] = None
        return None

    try:
        photo  = tk.PhotoImage(file=path)
        w, h   = photo.width(), photo.height()
        TARGET = 52
        factor = max(1, max(w, h) // TARGET)
        if factor > 1:
            photo = photo.subsample(factor, factor)
        _logo_cache[team_name] = photo
        return photo
    except Exception as e:
        print(f'[logo] 加载失败 {path}: {e}')
        _logo_cache[team_name] = None
        return None


# ══════════════════════════════════════════════════════
#  全局状态
# ══════════════════════════════════════════════════════
game_id        = ''
match_date     = ''
stop_fetching  = False
player_names: dict = {}   # {球员名: 'guest'|'host'}
_guest_name    = '客队'
_host_name     = '主队'

# ── 去重：已插入的播报条目 id 集合 ──
_seen_livetext_ids: set = set()

# ══════════════════════════════════════════════════════
#  配色
# ══════════════════════════════════════════════════════
BG_TOP     = '#1565C0'
BG_TOP2    = '#1976D2'
ACCENT     = '#FF6F00'
LIVE_RED   = '#F44336'
TEXT_WHITE = '#FFFFFF'
TEXT_OFF   = '#BBDEFB'
BG_BODY    = '#F4F6F8'
BG_CARD    = '#FFFFFF'
BG_TAB_BAR = '#FFFFFF'
TAB_LINE   = '#1565C0'
TEXT_H     = '#1A1A2E'
TEXT_B     = '#37474F'
TEXT_M     = '#78909C'
TEXT_LIGHT = '#B0BEC5'
ROW_ODD    = '#FFFFFF'
ROW_EVEN   = '#F8FAFB'
ROW_ON_BG  = '#E3F2FD'
ROW_ON_FG  = '#1565C0'
ROW_SEL    = '#BBDEFB'
BORDER     = '#E0E7EF'


# ══════════════════════════════════════════════════════
#  数据层
# ══════════════════════════════════════════════════════
def check_match():
    try:
        r = requests.get(
            f'https://dc4pc.qiumibao.com/dc/matchs/data/{match_date}/player_{game_id}.htm',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
        d = r.json()['data']
        return d['guest']['team_name_cn'], d['host']['team_name_cn']
    except:
        return '客队', '主队'

def check_time():
    try:
        r = requests.get(
            f'https://bifen4pc2.qiumibao.com/json/{match_date}/v2/{game_id}.htm',
            params={'t': str(int(time.time()))},
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
        return r.json().get('period_cn', '--')
    except:
        return '--'

def calculate_game_score(p):
    def parse(key):
        try:
            a, b = map(int, p.get(key, '0-0').split('-'))
            return a, b
        except:
            return 0, 0
    fm, fa = parse('field')
    raw    = p.get('free', '0-0').split('-')
    frm    = int(raw[0]) if raw else 0
    fra    = int(raw[1]) if len(raw) > 1 else 0
    return (int(p.get('points', 0)) + 0.4*fm - 0.7*fa
            - 0.4*(fra - frm)
            + 0.7*int(p.get('off', 0)) + 0.3*int(p.get('def', 0))
            + int(p.get('ste', 0)) + 0.7*int(p.get('ass', 0))
            + 0.7*int(p.get('blo', 0))
            - int(p.get('fouls', 0)) - int(p.get('turn', 0)))

def _fetch_page(sid: str) -> list:
    """拉取指定 sid 页的条目列表，失败返回空列表。"""
    for _ in range(3):
        try:
            r = requests.get(
                f'https://dingshi4pc.qiumibao.com/livetext/data/cache/livetext/{game_id}/0/lit_page_2/{sid}.htm',
                timeout=8)
            return r.json()
        except:
            time.sleep(0.1)
    return []

# 节次缓存：后台每 10 秒更新一次，不阻塞主轮询链路
_period_cache = '--'

def _period_updater():
    """后台线程：每 10 秒刷新一次节次，写入缓存。"""
    global _period_cache
    while True:
        try:
            r = requests.get(
                f'https://bifen4pc2.qiumibao.com/json/{match_date}/v2/{game_id}.htm',
                params={'t': str(int(time.time()))},
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
            _period_cache = r.json().get('period_cn', '--')
        except:
            pass
        time.sleep(10)

def _get_max_sid() -> 'str | None':
    """获取当前最大 sid，失败返回 None。"""
    try:
        r = requests.get(
            f'https://dingshi4pc.qiumibao.com/livetext/data/cache/livetext/{game_id}/0/max_sid.json',
            timeout=6)
        return str(r.json()['max_sid'])
    except:
        return None

def _dispatch_items(items: list, period: str):
    """过滤已见条目，按 sid 升序派发到 UI。"""
    # sid 升序 → 保证旧消息先显示
    def _item_sid(it):
        return int(it.get('id') or it.get('sid') or it.get('lid') or 0)

    new_items = []
    for item in items:
        iid = _item_sid(item)
        key = iid if iid else hash(item.get('live_text','') + str(item.get('guest_score','')))
        if key not in _seen_livetext_ids:
            _seen_livetext_ids.add(key)
            new_items.append((iid, item))

    for _, item in sorted(new_items, key=lambda x: x[0]):
        txt = item.get('live_text', '')
        for nm in sorted(player_names.keys(), key=len, reverse=True):
            side = player_names[nm]   # 'guest' or 'host'
            txt = txt.replace(nm, f'@@{side}:{nm}@@')
        gs = item.get('guest_score') or item.get('home_score', '0')
        hs = item.get('host_score') or item.get('visit_score', '0')
        root.after(0, lambda t=txt, pd=period, g=gs, h=hs:
                   ui_append_live(t, pd, g, h))

def fetch_live_text():
    global stop_fetching, player_names, _guest_name, _host_name, _seen_livetext_ids
    global _period_cache
    _guest_name, _host_name = check_match()
    root.after(0, lambda: ui_set_teams(_guest_name, _host_name))
    _seen_livetext_ids.clear()
    _period_cache = check_time()   # 启动时同步拿一次节次

    # 启动节次后台更新线程
    Thread(target=_period_updater, daemon=True).start()

    last_sid = None

    while not stop_fetching:
        try:
            cur_sid = _get_max_sid()
            if cur_sid is None:
                time.sleep(1)
                continue

            if last_sid is None:
                # 首次：只拉当前最新一页，不补历史
                items = _fetch_page(cur_sid)
                _dispatch_items(items, _period_cache)
                last_sid = cur_sid
                root.after(0, update_player_stats)
                time.sleep(0.1)
                continue

            if cur_sid == last_sid:
                # sid 没变，无新内容，短暂等待再试
                time.sleep(0.1)
                continue

            # sid 前进了：逐页补全，不丢包
            try:
                sid_from = int(last_sid) + 1
                sid_to   = int(cur_sid)
            except ValueError:
                sid_from = sid_to = int(cur_sid)

            all_items = []
            for sid_i in range(sid_from, sid_to + 1):
                page = _fetch_page(str(sid_i))
                all_items.extend(page)

            _dispatch_items(all_items, _period_cache)
            last_sid = cur_sid
            root.after(0, update_player_stats)
            time.sleep(0.1)   # 有新内容后也只等 0.5s 就继续轮询

        except:
            time.sleep(2)

def update_player_stats():
    global player_names
    try:
        r = requests.get(
            f'https://dc4pc.qiumibao.com/dc/matchs/data/{match_date}/player_{game_id}.htm',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
        d  = r.json().get('data', {})
        gn = d.get('guest', {}).get('team_name_cn', '客队')
        hn = d.get('host',  {}).get('team_name_cn', '主队')
        player_names.clear()
        for tree, key, lbl in [
            (guest_tree, 'guest', guest_stats_lbl),
            (host_tree,  'host',  host_stats_lbl)
        ]:
            nm      = gn if key == 'guest' else hn
            players = d.get(key, {}).get('on', [])
            for p in players:
                pname = p.get('player_name_cn', '')
                if pname:
                    player_names[pname] = key   # 'guest' 或 'host'
            sp = sorted(players, key=lambda p: (
                -int(p.get('points', 0)),
                -int(p.get('off', 0)) - int(p.get('def', 0)),
                -int(p.get('ass', 0))))
            root.after(0, lambda t=tree, ps=sp, lb=lbl, n=nm:
                       (_fill_tree(t, ps), lb.config(text=n)))
    except:
        pass

def _fill_tree(tree, players):
    tree.delete(*tree.get_children())
    for i, p in enumerate(players):
        try:    fm, fa = map(int, p.get('field', '0-0').split('-'))
        except: fm, fa = 0, 0
        try:    tm, ta = map(int, p.get('three', '0-0').split('-'))
        except: tm, ta = 0, 0
        try:
            fs = p.get('free', '0-0').split('-')
            frm, fra = int(fs[0]), int(fs[1])
        except: frm, fra = 0, 0
        reb   = int(p.get('off', 0)) + int(p.get('def', 0))
        fgpct = f"{fm/fa*100:.0f}%" if fa else '—'
        g3pct = f"{tm/ta*100:.0f}%" if ta else '—'
        gs    = calculate_game_score(p)
        on    = p.get('on_court') == '1'
        tag   = 'on' if on else ('even' if i % 2 == 0 else 'odd')
        dot   = '●' if on else ' '
        tree.insert('', 'end', tags=(tag,), values=(
            dot, p.get('player_name_cn', ''),
            p.get('points', 0), reb,
            p.get('ass', 0), p.get('ste', 0), p.get('blo', 0),
            p.get('turn', 0), p.get('fouls', 0),
            f"{gs:.1f}",
            p.get('minutes', '—'),
            f"{frm}/{fra}", fgpct,
            f"{tm}/{ta}", g3pct,
            f"{fm}/{fa}",
            p.get('plusMinus', 0),
        ))

def treeview_sort(tv, col, reverse=True):
    rows = []
    for k in tv.get_children(''):
        v = tv.set(k, col)
        try:    rows.append((float(v.replace('%','').replace('—','-1')), k))
        except: rows.append((v, k))
    rows.sort(key=lambda x: x[0], reverse=reverse)
    for i, (_, k) in enumerate(rows):
        tv.move(k, '', i)
    tv.heading(col, command=lambda: treeview_sort(tv, col, not reverse))


# ══════════════════════════════════════════════════════
#  UI 更新
# ══════════════════════════════════════════════════════
def ui_set_teams(guest, host):
    lbl_guest_name.config(text=guest)
    lbl_host_name.config(text=host)
    g_photo = _load_logo(guest)
    h_photo = _load_logo(host)
    if g_photo:
        lbl_guest_logo.config(image=g_photo)
        lbl_guest_logo.image = g_photo
    if h_photo:
        lbl_host_logo.config(image=h_photo)
        lbl_host_logo.image = h_photo


def ui_append_live(txt, period, gscore, hscore):
    lbl_guest_score.config(text=str(gscore))
    lbl_host_score.config(text=str(hscore))
    lbl_period.config(text=period)

    live_text.configure(state='normal')
    POS = '1.0'

    # 倒序插入 → 最终从上到下：⚡图标 | 正文 | 比分\n | 分隔线
    live_text.insert(POS, ' ' * 200 + '\n', 'div_line')
    live_text.insert(POS, '\n', 'tag_body')
    live_text.insert(POS, f'\t{gscore}-{hscore}  {period}', 'tag_right')
    parts = re.split(r'@@(.*?)@@', txt)
    for j in range(len(parts) - 1, -1, -1):
        if j % 2 == 1:
            # 奇数段是球员标记，格式为 "guest:名字" 或 "host:名字"
            seg = parts[j]
            if seg.startswith('guest:'):
                tag, display = 'tag_player_guest', seg[6:]
            elif seg.startswith('host:'):
                tag, display = 'tag_player_host', seg[5:]
            else:
                tag, display = 'tag_player_guest', seg
            live_text.insert(POS, display, tag)
        else:
            live_text.insert(POS, parts[j], 'tag_body')
    live_text.insert(POS, '  ⚡  ', 'tag_icon')

    live_text.see('1.0')
    live_text.configure(state='disabled')
    # 语音播报（去掉@@标记，只朗读纯文本）
    _tts_say(re.sub(r'@@(?:guest:|host:)?|@@', '', txt))


# ══════════════════════════════════════════════════════
#  控制逻辑
# ══════════════════════════════════════════════════════
def do_start():
    global game_id, match_date, stop_fetching
    game_id    = entry_id.get().strip()
    match_date = datetime.date.today().strftime('%Y-%m-%d')
    if not game_id:
        messagebox.showwarning('提示', '请输入比赛 ID'); return
    stop_fetching = False
    btn_start.config(state='disabled')
    btn_stop.config(state='normal')
    _blink()
    Thread(target=fetch_live_text, daemon=True).start()

def do_stop():
    global stop_fetching
    stop_fetching = True
    btn_start.config(state='normal')
    btn_stop.config(state='disabled')
    lbl_live_dot.config(text='○', fg=TEXT_LIGHT)

def do_clear():
    live_text.configure(state='normal')
    live_text.delete('1.0', 'end')
    live_text.configure(state='disabled')
    for t in [guest_tree, host_tree]:
        t.delete(*t.get_children())

_dot = True
def _blink():
    global _dot
    if stop_fetching: return
    _dot = not _dot
    lbl_live_dot.config(text='●' if _dot else '○',
                        fg=LIVE_RED if _dot else TEXT_LIGHT)
    root.after(700, _blink)

def _clock():
    lbl_clock.config(text=datetime.datetime.now().strftime('%H:%M:%S'))
    root.after(1000, _clock)

def switch_tab(name):
    for n, btn, frame in TAB_ITEMS:
        if n == name:
            btn.config(fg=TAB_LINE, font=('微软雅黑', 11, 'bold'))
            tab_underlines[n].config(bg=TAB_LINE)
            frame.tkraise()
        else:
            btn.config(fg=TEXT_M, font=('微软雅黑', 11))
            tab_underlines[n].config(bg=BG_TAB_BAR)


# ══════════════════════════════════════════════════════
#  构建 UI
# ══════════════════════════════════════════════════════
root = tk.Tk()
root.title('NBA 实时战报')
root.state('zoomed')
root.configure(bg=BG_BODY)

sty = ttk.Style()
sty.theme_use('clam')
sty.configure('TScrollbar',
    background=BORDER, troughcolor=BG_BODY,
    arrowcolor=TEXT_LIGHT, borderwidth=0, relief='flat', width=7)
sty.configure('Stats.Treeview',
    background=ROW_ODD, fieldbackground=ROW_ODD,
    foreground=TEXT_B, rowheight=31,
    font=('微软雅黑', 10), borderwidth=0, relief='flat')
sty.configure('Stats.Treeview.Heading',
    background='#EEF2F7', foreground=TEXT_M,
    font=('微软雅黑', 9, 'bold'), relief='flat', borderwidth=0, padding=(4, 6))
sty.map('Stats.Treeview',
    background=[('selected', ROW_SEL)],
    foreground=[('selected', ROW_ON_FG)])

# 顶部
top = tk.Frame(root, bg=BG_TOP)
top.pack(fill='x')

topbar = tk.Frame(top, bg=BG_TOP, pady=8)
topbar.pack(fill='x', padx=16)
tk.Label(topbar, text='🏀  NBA 实时战报',
         font=('微软雅黑', 12, 'bold'), fg=TEXT_WHITE, bg=BG_TOP).pack(side='left')
lbl_clock = tk.Label(topbar, text='', font=('Courier New', 11), fg=TEXT_OFF, bg=BG_TOP)
lbl_clock.pack(side='right', padx=(0, 8))
lbl_live_dot = tk.Label(topbar, text='○', font=('Helvetica', 13), fg=TEXT_LIGHT, bg=BG_TOP)
lbl_live_dot.pack(side='right')

scoreboard = tk.Frame(top, bg=BG_TOP)
scoreboard.pack(pady=(4, 0))

col_away = tk.Frame(scoreboard, bg=BG_TOP)
col_away.pack(side='left', padx=(40, 0))
lbl_guest_logo = tk.Label(col_away, text='', bg=BG_TOP)
lbl_guest_logo.pack()
lbl_guest_name = tk.Label(col_away, text='客队',
    font=('微软雅黑', 13, 'bold'), fg=TEXT_WHITE, bg=BG_TOP)
lbl_guest_name.pack()

col_scores = tk.Frame(scoreboard, bg=BG_TOP)
col_scores.pack(side='left', padx=30)
score_row = tk.Frame(col_scores, bg=BG_TOP)
score_row.pack()
lbl_guest_score = tk.Label(score_row, text='0',
    font=('Helvetica', 52, 'bold'), fg=TEXT_WHITE, bg=BG_TOP, width=3, anchor='e')
lbl_guest_score.pack(side='left')
mid_pill = tk.Frame(score_row, bg=ACCENT, padx=14, pady=6)
mid_pill.pack(side='left', padx=14)
lbl_period = tk.Label(mid_pill, text='待机',
    font=('微软雅黑', 11, 'bold'), fg=TEXT_WHITE, bg=ACCENT)
lbl_period.pack()
lbl_host_score = tk.Label(score_row, text='0',
    font=('Helvetica', 52, 'bold'), fg=TEXT_WHITE, bg=BG_TOP, width=3, anchor='w')
lbl_host_score.pack(side='left')

col_home = tk.Frame(scoreboard, bg=BG_TOP)
col_home.pack(side='left', padx=(0, 40))
lbl_host_logo = tk.Label(col_home, text='', bg=BG_TOP)
lbl_host_logo.pack()
lbl_host_name = tk.Label(col_home, text='主队',
    font=('微软雅黑', 13, 'bold'), fg=TEXT_WHITE, bg=BG_TOP)
lbl_host_name.pack()

ctrl_bar = tk.Frame(top, bg=BG_TOP2, pady=8)
ctrl_bar.pack(fill='x')

def _mk_btn(parent, text, cmd, bg, fg=TEXT_WHITE, state='normal'):
    return tk.Button(parent, text=text, command=cmd,
                     font=('微软雅黑', 10, 'bold'), bg=bg, fg=fg,
                     activebackground=bg, activeforeground=fg,
                     relief='flat', bd=0, padx=16, pady=5,
                     cursor='hand2', state=state)

tk.Label(ctrl_bar, text='比赛 ID：', font=('微软雅黑', 10),
         fg=TEXT_OFF, bg=BG_TOP2).pack(side='left', padx=(16, 4))
entry_frame = tk.Frame(ctrl_bar, bg='white', padx=1, pady=1)
entry_frame.pack(side='left')
entry_id = tk.Entry(entry_frame, font=('微软雅黑', 11), width=16,
                    bg='white', fg=TEXT_H, insertbackground=BG_TOP,
                    relief='flat', bd=4)
entry_id.pack()
btn_start = _mk_btn(ctrl_bar, '▶  开始直播', do_start, ACCENT)
btn_start.pack(side='left', padx=(10, 4))
btn_stop = _mk_btn(ctrl_bar, '⏹  停止', do_stop, '#C62828', state='disabled')
btn_stop.pack(side='left', padx=4)
_mk_btn(ctrl_bar, '清屏', do_clear, '#455A64').pack(side='left', padx=4)

# 语音开关 + 音色切换
def _toggle_tts():
    global _tts_on
    if not TTS_OK:
        messagebox.showinfo('提示', '请安装依赖：pip install edge-tts pygame')
        return
    _tts_on = not _tts_on
    btn_tts.config(
        text='🔊 语音 ON' if _tts_on else '🔇 语音 OFF',
        bg='#2E7D32' if _tts_on else '#546E7A'
    )

btn_tts = _mk_btn(ctrl_bar, '🔇 语音 OFF', _toggle_tts, '#546E7A')
btn_tts.pack(side='left', padx=4)

# 音色下拉菜单
import tkinter.font as _tkfont
_voice_var = tk.StringVar(value='晓伊（女·活泼）')

def _on_voice_change(*_):
    global _tts_voice
    _tts_voice = TTS_VOICES.get(_voice_var.get(), 'zh-CN-YunyangNeural')

tk.Label(ctrl_bar, text='音色:', font=('微软雅黑', 10),
         fg=TEXT_OFF, bg=BG_TOP2).pack(side='left', padx=(10, 2))
voice_menu = ttk.Combobox(ctrl_bar, textvariable=_voice_var,
                           values=list(TTS_VOICES.keys()),
                           state='readonly', width=12,
                           font=('微软雅黑', 10))
voice_menu.pack(side='left')
_voice_var.trace_add('write', _on_voice_change)

# 标签栏
tab_bar = tk.Frame(root, bg=BG_TAB_BAR,
                   highlightbackground=BORDER, highlightthickness=1)
tab_bar.pack(fill='x')
content = tk.Frame(root, bg=BG_BODY)
content.pack(fill='both', expand=True)

# Tab 直播
frame_live = tk.Frame(content, bg=BG_CARD)
frame_live.place(relx=0, rely=0, relwidth=1, relheight=1)
live_text = tk.Text(frame_live, wrap='word', state='disabled',
                    bg=BG_CARD, fg=TEXT_B,
                    font=('微软雅黑', 12), padx=0, pady=0,
                    relief='flat', borderwidth=0,
                    cursor='arrow', selectbackground=ROW_SEL,
                    tabs=('500p', 'right'),
                    spacing1=0, spacing2=0, spacing3=0)
vsb_live = ttk.Scrollbar(frame_live, orient='vertical', command=live_text.yview)
live_text.configure(yscrollcommand=vsb_live.set)
vsb_live.pack(side='right', fill='y')
live_text.pack(fill='both', expand=True)

live_text.tag_config('tag_icon',
    foreground='#F57C00', font=('微软雅黑', 11, 'bold'),
    background='#FFFDE7', lmargin1=0, lmargin2=60, spacing1=10, spacing3=0)
live_text.tag_config('tag_body',
    foreground=TEXT_B, font=('微软雅黑', 12),
    background='#FFFDE7', lmargin1=0, lmargin2=60, spacing1=0, spacing3=0)
live_text.tag_config('tag_player_guest',
    foreground='#C62828', font=('微软雅黑', 12, 'bold'), background='#FFFDE7')   # 客队红
live_text.tag_config('tag_player_host',
    foreground='#1565C0', font=('微软雅黑', 12, 'bold'), background='#FFFDE7')   # 主队蓝
live_text.tag_config('tag_right',
    foreground=TEXT_M, font=('微软雅黑', 10), background='#FFFDE7', spacing3=0)
live_text.tag_config('div_line',
    background=BORDER, font=('微软雅黑', 1), spacing1=0, spacing3=0)

# Tab 数据
frame_stats = tk.Frame(content, bg=BG_BODY)
frame_stats.place(relx=0, rely=0, relwidth=1, relheight=1)

COLS_DATA = ('●', '球员', '分', '篮', '助', '抢', '帽', '误', '犯', 'GS',
             '时间', '罚球', 'FG%', '三分', '3P%', '投篮', '±')
COLS_W    = [28, 110, 50, 50, 50, 50, 50, 50, 50, 62, 70, 72, 62, 68, 62, 68, 50]

def make_stats_panel(parent, side):
    pf  = tk.Frame(parent, bg=BG_BODY)
    hdr = tk.Frame(pf, bg=BG_TOP, pady=7)
    hdr.pack(fill='x')
    lbl = tk.Label(hdr, text='—', font=('微软雅黑', 12, 'bold'),
                   fg=TEXT_WHITE, bg=BG_TOP, padx=14)
    lbl.pack(side='left')
    tvf = tk.Frame(pf, bg=BG_BODY)
    tvf.pack(fill='both', expand=True)
    tv  = ttk.Treeview(tvf, columns=COLS_DATA, show='headings',
                       style='Stats.Treeview', selectmode='browse')
    for col, w in zip(COLS_DATA, COLS_W):
        tv.heading(col, text=col, anchor='center',
                   command=lambda c=col, t=tv: treeview_sort(t, c, True))
        tv.column(col, width=w, minwidth=w, anchor='center')
    tv.tag_configure('on',   background=ROW_ON_BG, foreground=ROW_ON_FG,
                              font=('微软雅黑', 10, 'bold'))
    tv.tag_configure('even', background=ROW_ODD)
    tv.tag_configure('odd',  background=ROW_EVEN)
    vsb = ttk.Scrollbar(tvf, orient='vertical',   command=tv.yview)
    hsb = ttk.Scrollbar(tvf, orient='horizontal', command=tv.xview)
    tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tv.grid(row=0, column=0, sticky='nsew')
    vsb.grid(row=0, column=1, sticky='ns')
    hsb.grid(row=1, column=0, sticky='ew')
    tvf.grid_columnconfigure(0, weight=1)
    tvf.grid_rowconfigure(0, weight=1)
    return pf, lbl, tv

stats_paned = tk.PanedWindow(frame_stats, orient='horizontal',
                              sashwidth=4, sashrelief='flat', bg=BORDER, bd=0)
stats_paned.pack(fill='both', expand=True)
guest_panel, guest_stats_lbl, guest_tree = make_stats_panel(stats_paned, 'left')
host_panel,  host_stats_lbl,  host_tree  = make_stats_panel(stats_paned, 'right')
stats_paned.add(guest_panel, stretch='always')
stats_paned.add(host_panel,  stretch='always')

TAB_ITEMS      = []
tab_underlines = {}

def _make_tab(label, frame):
    col = tk.Frame(tab_bar, bg=BG_TAB_BAR)
    col.pack(side='left')
    btn = tk.Button(col, text=label,
                    font=('微软雅黑', 11), fg=TEXT_M,
                    bg=BG_TAB_BAR, activebackground=BG_TAB_BAR,
                    activeforeground=TAB_LINE,
                    relief='flat', bd=0, padx=20, pady=10,
                    cursor='hand2',
                    command=lambda f=frame, n=label: switch_tab(n))
    btn.pack()
    line = tk.Frame(col, bg=BG_TAB_BAR, height=3)
    line.pack(fill='x')
    TAB_ITEMS.append((label, btn, frame))
    tab_underlines[label] = line

_make_tab('直播', frame_live)
_make_tab('数据', frame_stats)
switch_tab('直播')

footer = tk.Frame(root, bg='#ECEFF1', pady=5,
                  highlightbackground=BORDER, highlightthickness=1)
footer.pack(fill='x', side='bottom')
tk.Label(footer, text='数据来源：直播吧  ·  GS = Game Score  ·  ● 当前在场',
         font=('微软雅黑', 9), fg=TEXT_LIGHT, bg='#ECEFF1').pack(side='left', padx=14)

_clock()
root.mainloop()