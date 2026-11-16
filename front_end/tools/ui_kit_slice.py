"""把总控的 UI 素材包（品红底 1024² 三张）切成带 alpha 的单件 PNG → public/assets/ui/kit/。
用法：tools/.venv/bin/python tools/ui_kit_slice.py [kit 目录]
命名表按连通域包围盒的位置手工对应（素材是 gpt-image-2 出的，位置固定）。"""
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

K = Path(sys.argv[1] if len(sys.argv) > 1 else '/home/shan-dw/Project/run/data/art/ui-redo/kit-final')
OUT = Path(__file__).resolve().parent.parent / 'public/assets/ui/kit'
OUT.mkdir(parents=True, exist_ok=True)

def load(kit):
    rgb = np.array(Image.open(K / f'{kit}.png').convert('RGB')).astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # 品红度：r、b 高且 g 低；软阈值做 alpha，吃掉 1px 品红晕
    mag = np.clip((np.minimum(r, b) - g) / 120.0, 0, 1)          # 1 = 纯品红
    alpha = (1 - mag)
    alpha = np.where(mag > 0.75, 0, np.where(mag < 0.35, 1, alpha)) # 两头截断
    rgba = np.dstack([rgb.clip(0, 255).astype(np.uint8), (alpha * 255).astype(np.uint8)])
    return rgba, mag < 0.5

def boxes(fg):
    lab, _ = ndimage.label(fg, structure=np.ones((3, 3)))
    out = []
    for sl in ndimage.find_objects(lab):
        if sl is None: continue
        y0, y1 = sl[0].start, sl[0].stop; x0, x1 = sl[1].start, sl[1].stop
        if x1 - x0 < 14 or y1 - y0 < 10: continue
        out.append((x0, y0, x1, y1))
    return out

def in_band(bs, y0, y1):
    return sorted([b for b in bs if y0 <= b[1] < y1], key=lambda b: b[0])

def union(bs):
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))

def save(rgba, box, name, pad=1):
    x0, y0, x1, y1 = box
    im = Image.fromarray(rgba[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad])
    im.save(OUT / f'{name}.png')
    return [name, im.size]

made = []
# ── kit01 ──
rgba, fg = load('kit01_panels_buttons'); bs = boxes(fg)
row = in_band(bs, 0, 300); made += [save(rgba, row[0], 'panel_sky'), save(rgba, row[1], 'panel_mint'), save(rgba, row[2], 'title_bar')]
for i, (y0, y1, st) in enumerate([(300, 365, 'normal'), (365, 425, 'hover'), (425, 500, 'pressed')]):
    row = in_band(bs, y0, y1)
    for b, col in zip(row, ['teal', 'coral', 'neutral']): made.append(save(rgba, b, f'btn_{col}_{st}'))
row = in_band(bs, 530, 620)
for b, st in zip(row, ['normal', 'hover', 'pressed', 'active']): made.append(save(rgba, b, f'sq_{st}'))
row = in_band(bs, 660, 720)
for b, nm in zip(row, ['pill_sky', 'pill_pink', 'pill_peach', 'pill_mint', 'pill_lavender', 'pill_red', 'pill_amber']): made.append(save(rgba, b, nm))
row = [b for b in in_band(bs, 760, 815) if b[3] - b[1] > 20]
for b, nm in zip(row, ['icon_bread', 'bar_fullness', 'icon_bolt', 'bar_energy', 'icon_people', 'bar_social', 'icon_star', 'bar_fun']): made.append(save(rgba, b, nm))
row = in_band(bs, 870, 1000)
for b, nm in zip(row, ['toast_pill', 'close_x', 'hotkey_badge']): made.append(save(rgba, b, nm))
# ── kit02 ──
rgba, fg = load('kit02_icons'); bs = boxes(fg)
names = ['people', 'map', 'bag', 'log', 'chat', 'settings']
for b, nm in zip([x for x in in_band(bs, 30, 160) if x[3] - x[1] > 40], names): made.append(save(rgba, b, f'summon_{nm}'))
for b, nm in zip([x for x in in_band(bs, 160, 290) if x[3] - x[1] > 40], names): made.append(save(rgba, b, f'summon_{nm}_on'))
row = [x for x in in_band(bs, 360, 460) if x[3] - x[1] > 30]
made.append(save(rgba, union(row[:2]), 'dir_back'))     # 箭头 + 小人两块
for b, nm in zip(row[2:], ['dir_camera', 'dir_thought', 'toggle_on', 'toggle_off']): made.append(save(rgba, b, nm))
row = [x for x in in_band(bs, 555, 620) if x[3] - x[1] > 25]
for b, nm in zip(row, ['mi_clock', 'mi_sun', 'mi_cloud', 'mi_rain', 'mi_moon', 'mi_coin', 'mi_bread', 'mi_bolt', 'mi_people', 'mi_star', 'mi_happy', 'mi_meh', 'mi_sad', 'mi_dnd', 'mi_stairs', 'mi_door', 'mi_eye', 'mi_unread']): made.append(save(rgba, b, nm))
row = [x for x in in_band(bs, 690, 830) if x[3] - x[1] > 100]
for b, nm in zip(row, ['phone_icon', 'minimap_frame']): made.append(save(rgba, b, nm))
row = [x for x in in_band(bs, 800, 850) if 20 < x[3] - x[1] < 40]
for b, nm in zip(row, ['dot_blue', 'dot_pink', 'dot_orange', 'dot_green', 'dot_purple', 'dot_yellow']): made.append(save(rgba, b, nm))
# ── kit03 ──
rgba, fg = load('kit03_bubbles_phone'); bs = boxes(fg)
row = [x for x in in_band(bs, 30, 160) if x[3] - x[1] > 40]
for b, nm in zip(row, ['speech_s', 'speech_m', 'speech_l', 'speech_r']): made.append(save(rgba, b, nm))
clouds = [x for x in in_band(bs, 170, 330) if x[3] - x[1] > 40]
dots = [x for x in bs if 270 <= x[1] < 340 and x[3] - x[1] <= 30]
for b, nm in zip(clouds, ['thought_s', 'thought_m', 'thought_l', 'thought_dots']):
    mine = [d for d in dots if b[0] - 10 <= d[0] <= b[2] + 10]
    made.append(save(rgba, union([b] + mine), nm))
row = [x for x in in_band(bs, 340, 440) if x[3] - x[1] > 30]
for b, nm in zip(row, ['name_tag_a', 'name_tag_b', 'tag_sleep', 'tag_live', 'knock_burst']): made.append(save(rgba, b, nm))
row = sorted([x for x in bs if x[1] >= 460], key=lambda b: (b[1] // 90, b[0]))
for b, nm in zip(row, ['phone_shell', 'contact_row', 'send_btn', 'input_box', 'login_ribbon', 'login_big_btn']): made.append(save(rgba, b, nm))
# toast_pill 内有示例文字：做一张空白版（内缘以内填成底色）
tp = np.array(Image.open(OUT / 'toast_pill.png').convert('RGBA'))
h, w = tp.shape[:2]; m = 14
fill = tp[h // 2, m + 6].copy()
tp[m:h - m, m:w - m] = fill
Image.fromarray(tp).save(OUT / 'toast_blank.png'); made.append(['toast_blank', (w, h)])
json.dump(dict((n, s) for n, s in made), open(OUT / 'index.json', 'w'), ensure_ascii=False, indent=0)
print(len(made), 'slices'); print(made)
