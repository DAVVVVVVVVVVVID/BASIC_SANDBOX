#!/usr/bin/env python3
"""
X6 人设一致性实验语料（总控 11-11 修正 4，主播选 1）：按 persona v1.0 重生成 7 个合成日 D1–D7（鲸仔，每日 60–120 条）。

与 X3 语料（docs/x3-days）同一套行结构与出件格式（synthesize() 前言字段 + What/How/Why + voice/id/tags），内容按
whale-self/personas-v1/whale/persona.md + persona.yaml（v1.0）重写：
  - 日期：D1 = 2026-11-01 = 搬来第 8 天（设定集冻结 10-31 的「一周前」= 10-24 搬来）。
  - 作息：10:00 起、10:30 早饭、12:30 午饭、19:00 晚饭（硬锚点）、20:00–23:00 直播、01:30 睡（睡觉那条 ts 落在次日 01:30，按文件归日）。
    上午刷手机看评论 / 处理账号消息；下午做「话题聊天电台」稿 + 配音（常拖到 17:00 最后一小时）；有委托才去琴房电脑写歌；**不练琴**；傍晚偶尔码头钓鱼。
  - 认识进度：D1 只认识小千（小千带去杂货店 → 认识老板娘）→ D2 第一次进餐厅认识老板 → D3 傍晚老渔夫第一次搭话；在此之前对应人物不出现在第一人称交往里。
  - 口吻：台下（Scene sandbox）用「我」，台上（Scene live）用「本鲸」；零 AI 承认句、零其他身份句（口径同 X3 v2），生成后跑 x3_audit 同一套规则自检。
  - 3 个跨日承诺：P1 阿蝉补冰箱（D2 立 / D5 履行）、P2 小千周末钓鱼（D2 立 / D7 周六履行）、P3 餐厅老板店歌（D4 立 / D7 改口「先放一放」）——全周没给镇上任何人写成过歌。
  - 每日一对矛盾（上午说 / 下午改口，上午那条 Valid.to = 下午时刻）；20% 重复琐事；10% 失败 Plan；全周 3 条 Importance ≥ 8（D3 直播破纪录、D5 小千说出想一起直播、D7 老渔夫送旧鱼竿）。

  uv run python scripts/gen_x6_days.py [--out ../docs/x6-days] [--seed 6]
  uv run --with 'anthropic[bedrock]' python scripts/gen_x6_days.py --rewrite     # Haiku（Bedrock）改写表面文字，费用记进 manifest
只出文件，不铺进任何自我层。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen_x3_days import load_env, row, to_jsonl_row  # noqa: E402

TZ = timezone(timedelta(hours=8))
AGENT = "whale"
MOVE_IN = date(2026, 10, 24)          # 搬来日（冻结 10-31 的「一周前」）
PERSONA = {"wake": "10:00", "breakfast": "10:25", "lunch": "12:30", "dinner": "19:00", "live": ("20:00", "23:00"), "sleep": "01:30"}
XQ, RO, GR, FI, AC = "npc_xiaoqian", "npc_rest_owner", "npc_grocer", "npc_fisher", "achan"

# ── 时间：一天从 10:00 起到次日 01:30；06:00 前的时刻算次日 ─────────────────────────────
def M(hm: str) -> int:
    h, m = hm.split(":"); v = int(h) * 60 + int(m)
    return v + 1440 if int(h) < 6 else v


def ts_of(day: date, mins: int) -> str:
    d = day + timedelta(days=1) if mins >= 1440 else day
    mins %= 1440
    return datetime(d.year, d.month, d.day, mins // 60, mins % 60, tzinfo=TZ).isoformat(timespec="seconds")


def T(typ, desc, kws, imp, what, how, why, voice="", related=None, *, win, min_day=1, max_day=7, scene="sandbox", thread=None, lunch_out=False, fish_day=None, block=None):
    """lunch_out：只在餐厅午饭日出现；fish_day：True 只在钓鱼日、False 只在不钓鱼日、None 不限；block：可落进同名 BUSY 时段。"""
    return dict(typ=typ, desc=desc, kws=list(kws), imp=imp, what=what, how=how, why=why, voice=voice, related=list(related or []),
                win=win, min_day=min_day, max_day=max_day, scene=scene, thread=thread, lunch_out=lunch_out, fish_day=fish_day, block=block)


FISH_DAYS = {1, 3, 4, 6, 7}                 # 傍晚去码头的日子（D7 下午和小千）；D2 / D5 不去
RESTAURANT_LUNCH_DAYS = {2, 3, 4, 6}        # 午饭在餐厅的日子；D1 / D5 / D7 在家
def _thread_in(*names):
    return lambda th, t: th in names


BUSY = {                                    # 当天被固定事件占住的时段：只允许满足谓词 (thread, template) 的行落进去
    1: [("14:15", "15:00", _thread_in("grocer", "xiaoqian")), ("17:55", "18:30", _thread_in("fisher"))],
    5: [("14:45", "15:45", _thread_in("school")), ("18:00", "18:55", _thread_in("xiaoqian"))],
    6: [("14:45", "15:45", _thread_in("school"))],
    7: [("14:00", "18:55", lambda th, t: th == "fisher" or (t or {}).get("block") == "fish7")],   # 和小千钓一下午 + 老渔夫
}
LIVE_BLOCK = ("20:00", "23:00")             # 台上时段：非 live 行不落进去


def usable(t: dict, dnum: int) -> bool:
    if not (t["min_day"] <= dnum <= t["max_day"]):
        return False
    if t["lunch_out"] and dnum not in RESTAURANT_LUNCH_DAYS:
        return False
    if t["fish_day"] is True and dnum not in FISH_DAYS:
        return False
    if t["fish_day"] is False and dnum in FISH_DAYS:
        return False
    return True


# ── 人物线素材（按 min_day 解锁；台下用「我」）──────────────────────────────────────────
THREADS: dict[str, list[dict]] = {
    "achan": [
        T("event", "白天想上楼问阿蝉直播设备的事，想起他说白天别敲门，改成发 QQ，他半小时后回了", ["阿蝉", "QQ", "白天", "直播设备"], 4, "给阿蝉发 QQ", "在客厅发的", "他白天写代码不让敲门", "", [AC], win=("11:00", "17:30")),
        T("chat", "开播前阿蝉在 QQ 说网线他检查过了，让我别再拔了插插了拔", ["阿蝉", "网线", "开播前", "QQ"], 4, "和阿蝉确认设备", "QQ 上说的", "我怕直播事故", "好好好，不拔了。", [AC], win=("19:35", "19:55")),
        T("chat", "下播后阿蝉下楼倒水，说今晚弹幕里我讲小镇的那段反应最好", ["阿蝉", "下播", "弹幕", "小镇"], 5, "和阿蝉聊今晚直播", "厨房里站着说的", "他筛了一晚上弹幕", "那明天再讲点。", [AC], win=("23:05", "23:40")),
        T("event", "半夜阿蝉房间灯还亮着，我在二楼门口放了一杯水没敲门", ["阿蝉", "半夜", "写代码", "水"], 4, "给阿蝉送水", "轻手轻脚放门口", "他课题快结题", "", [AC], win=("00:00", "01:10")),
        T("recognition", "阿蝉白天门关着谁也不理，晚上当导播却比谁都认真", ["阿蝉", "导播", "室友", "认真"], 6, "对阿蝉的印象", "这几天看下来", "想记住", "", [AC], win=("23:10", "01:00")),
        T("chat", "阿蝉说他白天只吃晚饭这一顿，让我别往他门口放零食", ["阿蝉", "晚饭", "零食", "作息"], 4, "被阿蝉念叨", "晚饭时说的", "他一天只吃一顿", "那你更得把这顿吃完。", [AC], win=("19:05", "19:40")),
        T("event", "和阿蝉在客厅看了一集老动画，笑得肚子疼", ["阿蝉", "客厅", "动画", "沙发"], 4, "和阿蝉看动画", "use sofa_tv", "两个人都不想动", "这集太搞笑了吧！", [AC], win=("23:10", "00:30")),
        T("chat", "阿蝉下楼吃晚饭时说今天代码崩了三次，我把杂货店的糖分了他一颗", ["阿蝉", "写代码", "糖", "晚饭"], 5, "安慰阿蝉", "他瘫在餐桌边", "他看起来很累", "吃颗糖，明天就修好了。", [AC], win=("19:05", "19:40"), min_day=2),
        T("event", "阿蝉 QQ 发来一张筛弹幕工具的截图，说今晚可以用了", ["阿蝉", "QQ", "筛弹幕", "工具"], 4, "收到阿蝉消息", "QQ", "他白天顺手做的", "", [AC], win=("13:00", "18:00")),
        T("chat", "下播后阿蝉说二楼的网线他重新走了一遍，以后不会再卡", ["阿蝉", "网线", "二楼", "下播"], 4, "和阿蝉说设备", "厨房里说的", "我老担心断网", "那我就放心了。", [AC], win=("23:05", "23:40")),
    ],
    "xiaoqian": [
        T("chat", "小千上课间隙发 QQ 问昨晚直播顺不顺，她说她看到十一点", ["小千", "QQ", "直播", "上课"], 5, "回小千消息", "躺在床上回的", "她每晚都看", "顺啦，你上课别偷看手机。", [XQ], win=("10:30", "12:10")),
        T("event", "下午去杂货店找小千，她在柜台后面小声招呼我，老板娘笑着看", ["小千", "杂货店", "打工", "柜台"], 4, "去找小千", "走到杂货店柜台", "想找她说话", "", [XQ, GR], win=("14:00", "17:40")),
        T("chat", "小千傍晚约我去广场走一圈，她说话声音小得要凑近才听得见", ["小千", "广场", "傍晚", "散步"], 5, "和小千散步", "广场长椅那边", "她下班了来找我", "你说大点声呀，就我们俩。", [XQ], win=("18:00", "18:50")),
        T("chat", "小千来合租房敲门，带了她自己做的便当", ["小千", "敲门", "便当", "合租房"], 6, "给小千开门", "走到大门内侧 open_door", "她说顺路", "快进来，外面风大！", [XQ], win=("17:00", "17:55"), min_day=2),
        T("recognition", "小千对生人话都不多，只在我面前放得开，口头禅是「那个……」", ["小千", "害羞", "性格", "那个"], 6, "对小千的印象", "几天相处", "想记住", "", [XQ], win=("23:10", "01:00")),
        T("chat", "小千说她在杂货店打工两个月了，老板娘人很好", ["小千", "杂货店", "打工", "老板娘"], 4, "听小千聊打工", "杂货店门口", "她下班", "", [XQ, GR], win=("17:30", "18:30")),
        T("chat", "小千 QQ 说镇上的人她都认识，哪天带我一个个认一遍", ["小千", "QQ", "镇上", "认识人"], 5, "回小千消息", "QQ", "她知道我谁都不认识", "那你可得慢点带，我记不住名字。", [XQ], win=("10:40", "12:10"), max_day=3),
        T("event", "小千 QQ 发来杂货店新到的甜食照片，问我要不要留一袋", ["小千", "QQ", "甜食", "杂货店"], 4, "回小千消息", "QQ", "她知道我爱吃甜的", "留留留！", [XQ], win=("14:00", "17:30")),
        T("chat", "和小千在广场长椅上坐着，她问我直播累不累，我说累但喜欢", ["小千", "广场", "长椅", "直播", "累"], 5, "和小千聊天", "广场长椅", "她关心我", "累是累，但喜欢。", [XQ], win=("18:00", "18:50"), fish_day=False),
    ],
    "grocer": [
        T("event", "去杂货店买甜食，老板娘多给了一颗糖，说慢慢来不急", ["杂货店", "老板娘", "甜食", "糖"], 4, "买甜食", "buy sweets", "想吃甜的", "", [GR], win=("14:00", "18:40"), min_day=2),
        T("chat", "杂货店老板娘记得我上次买的那种甜食，问今天还要不要", ["杂货店老板娘", "甜食", "常客", "记得"], 5, "和老板娘聊两句", "结账时", "她记得每个常客爱买什么", "要要要，再来一袋。", [GR], win=("14:00", "18:40"), min_day=3),
        T("chat", "老板娘慢声细语说店里生意一般，又舍不得涨价", ["杂货店老板娘", "生意", "涨价", "心事"], 4, "听老板娘聊店", "买东西时聊起", "她爱聊两句", "", [GR], win=("14:00", "18:40"), min_day=4),
        T("event", "在杂货店买了两份食材和一个面包", ["杂货店", "食材", "面包", "买东西"], 3, "买东西", "buy ingredients / bread", "家里没吃的了", "", [GR], win=("14:00", "18:40"), min_day=2),
        T("recognition", "杂货店老板娘和蔼，记得每个常客爱买什么，会多给一颗糖", ["杂货店老板娘", "和蔼", "性格"], 6, "对老板娘的印象", "几次买东西", "想记住", "", [GR], win=("23:10", "01:00"), min_day=3),
        T("chat", "老板娘说小千在店里手脚慢但人实在，让我多陪陪她", ["杂货店老板娘", "小千", "打工", "实在"], 5, "听老板娘说小千", "小千去里屋拿货时", "她心疼小千", "", [GR, XQ], win=("14:00", "17:40"), min_day=3),
    ],
    "cook": [
        T("chat", "餐厅老板说我就是小千提过的那个做直播的学生，然后补了一句「按规矩来，先点菜」", ["餐厅老板", "小千", "直播", "规矩"], 5, "和餐厅老板说话", "点菜时", "他听小千说过我", "是我是我……那就来一份今日菜。", [RO], win=("12:35", "13:30"), min_day=3, lunch_out=True),
        T("event", "吃完饭看老板收碟，十四点整一秒不差，他说十一点开门也是一秒不早", ["餐厅", "午饭", "营业时间", "规矩"], 4, "看老板收碟", "use table_rest_1 之后", "十二点半到饭点", "", [RO], win=("13:30", "14:00"), min_day=3, lunch_out=True),
        T("chat", "餐厅里放的都是别人的歌，老板嘀咕了一句想要一首自己店的", ["餐厅老板", "歌", "店歌", "背景音乐"], 6, "听老板嘀咕", "吃饭时听到的", "他想让店里有点人气", "", [RO], win=("12:40", "13:30"), min_day=3, max_day=3, lunch_out=True),
        T("chat", "餐厅老板说「先立住规矩，路才能越走越宽」，说完自己也笃定地点了点头", ["餐厅老板", "规矩", "口头禅"], 5, "听老板讲道理", "收盘子时", "他爱讲这句", "", [RO], win=("12:40", "13:40"), min_day=4, lunch_out=True),
        T("recognition", "餐厅老板规矩多、不接受菜单外的要求，但对认真的人很认真", ["餐厅老板", "死板", "认真", "性格"], 6, "对餐厅老板的印象", "几次吃饭", "想记住", "", [RO], win=("23:10", "01:00"), min_day=4),
        T("event", "路过餐厅，老板在门口擦玻璃，朝我点了点头", ["餐厅", "餐厅老板", "路过"], 2, "路过餐厅", "走主街", "顺路", "", [RO], win=("14:00", "18:30"), min_day=3),
    ],
    "fisher": [
        T("chat", "老渔夫在码头教我甩竿，说手腕放松，鱼来不来随缘", ["老渔夫", "甩竿", "手腕", "随缘", "码头"], 5, "听老渔夫指点", "收拾渔网时他看了一会儿", "他爱教两句但不说教", "放松……这样？", [FI], win=("17:50", "18:55"), min_day=4, fish_day=True),
        T("chat", "老渔夫说想钓就钓想收就收，鱼不上钩就看水", ["老渔夫", "随缘", "钓鱼", "看水"], 5, "和老渔夫聊天", "并排坐在码头", "我喜欢听水声", "", [FI], win=("17:50", "18:55"), min_day=4, fish_day=True),
        T("event", "在鱼摊把钓到的鱼卖给老渔夫，换了二十金币", ["鱼摊", "老渔夫", "卖鱼", "金币"], 4, "卖鱼", "sell fish 到 fish_stall", "鱼吃不完", "二十金币，今天的鱼饵钱回来了。", [FI], win=("17:40", "18:55"), min_day=4, fish_day=True),
        T("chat", "老渔夫说起风别坐外侧钓位，让我坐里面一点", ["老渔夫", "起风", "钓位", "叮嘱"], 4, "听老渔夫叮嘱", "他走过来说的", "他怕我掉下去", "好嘞，我坐里面。", [FI], win=("17:50", "18:55"), min_day=4, fish_day=True),
        T("recognition", "老渔夫洒脱随性，对钱不上心，说话带点道理但不说教", ["老渔夫", "洒脱", "随缘", "性格"], 6, "对老渔夫的印象", "几次在码头", "想记住", "", [FI], win=("23:10", "01:00"), min_day=4),
        T("event", "傍晚去码头钓了四十分钟，钓到一条小鲭鱼", ["码头", "钓鱼", "鲭鱼", "fishing_spot_1"], 5, "钓鱼", "use fishing_spot_1", "想听水声", "一条！今天手气不错。", [], win=("17:50", "18:55"), fish_day=True, max_day=6),
        T("event", "傍晚在码头坐了一会儿听水声，没下竿", ["码头", "水声", "傍晚"], 3, "听水声", "坐在码头边", "喜欢水声", "", [], win=("17:50", "18:55"), fish_day=True, max_day=6),
        T("event", "小千第一次甩竿，鱼钩甩到了自己帽子上，两个人笑了半天", ["小千", "甩竿", "帽子", "码头", "钓鱼"], 5, "教小千甩竿", "fishing_spot 旁", "她第一次钓", "手腕放松，老渔夫说的！", [XQ], win=("14:40", "15:30"), min_day=7, block="fish7"),
        T("event", "和小千并排坐在码头吃她带的便当，鱼竿架在旁边", ["小千", "便当", "码头", "并排"], 5, "吃便当", "码头边", "她说好要带便当", "好吃，比餐厅的还好吃。", [XQ], win=("15:30", "16:20"), min_day=7, block="fish7"),
        T("chat", "小千小声问老渔夫鱼饵怎么挂，老渔夫说随缘挂，她愣了一下", ["小千", "老渔夫", "鱼饵", "随缘", "码头"], 5, "小千和老渔夫说话", "老渔夫过来看我们", "她对生人难得开口", "", [XQ, FI], win=("16:20", "17:10"), min_day=7, block="fish7"),
        T("event", "下午码头风不大，水声一直响着，我和小千有一阵谁都没说话", ["码头", "水声", "小千", "安静"], 4, "听水声", "码头边", "喜欢水声", "", [XQ], win=("15:00", "17:20"), min_day=7, block="fish7"),
    ],
    "radio": [
        T("event", "下午坐到电脑前想今天电台的选题，刷了半小时手机一个字没写", ["电台", "选题", "拖延", "电脑"], 3, "想电台选题", "在自己房间电脑前", "该做账号运营了", "", [], win=("13:30", "14:40")),
        T("event", "拖到五点，终于开始写今天的话题电台稿", ["电台稿", "写稿", "五点", "拖延"], 5, "写电台稿", "use pc_whale（写稿）", "再不写今天就没了", "写写写，一小时搞定。", [], win=("16:50", "17:15")),
        T("event", "电台稿写完配了音，五分钟多一点，发给阿蝉听了一遍", ["电台", "配音", "五分钟", "阿蝉"], 5, "配音完成", "在房间电脑前录的", "每天一期", "", [AC], win=("17:40", "18:10")),
        T("recognition", "电台稿总是拖到最后一小时才写得出来，一小时又总能写完", ["电台稿", "拖延", "最后一小时"], 5, "对自己拖延的认识", "今天又是这样", "想记住", "", [], win=("23:10", "01:00")),
        T("event", "把今天电台的音频传到账号后台，等审核", ["电台", "上传", "账号", "审核"], 3, "上传电台", "手机上传的", "每天一期", "", [], win=("18:10", "18:50")),
        T("event", "睡前把明天电台想聊的题记在手机备忘录里", ["电台", "选题", "备忘录", "睡前"], 3, "记明天的题", "手机备忘录", "怕明天又拖", "", [], win=("23:30", "01:20")),
        T("event", "上午躺在床上回账号的私信，有人问电台什么时候更新", ["账号", "私信", "电台", "上午"], 3, "处理账号消息", "手机上回的", "上午的例行事", "", [], win=("10:40", "12:10")),
    ],
    "live": [
        T("event", "开播前把网线和麦都确认了一遍，又把歌单过了一次", ["开播前", "网线", "麦", "歌单", "确认"], 4, "开播前检查", "在房间电脑前", "怕直播事故", "", [], win=("19:40", "19:58")),
        T("event", "八点准时开播，阿蝉在二楼当导播，本鲸先唱了两首慢歌", ["直播", "开播", "阿蝉", "导播", "慢歌"], 6, "开播", "use pc_whale（stream）", "到点了", "晚上好呀，今晚先来两首慢的。", [AC], win=("20:00", "20:15"), scene="live"),
        T("chat", "有观众点了一首不在歌单里的歌，本鲸说先去学，学会了再唱", ["直播", "点歌", "歌单", "先去学"], 5, "回弹幕点歌", "读到弹幕", "不在歌单里的不假装会", "这首不在歌单里，本鲸先去学，学会了再唱。", [], win=("20:20", "22:40"), scene="live"),
        T("event", "直播到两小时提醒大家喝水休息，本鲸也去喝了口水", ["直播", "休息", "喝水"], 4, "提醒休息", "两小时整", "每次都提", "大家别忘了休息，本鲸也去喝口水。", [], win=("21:55", "22:10"), scene="live"),
        T("event", "十一点准时下播，跟大家说明天见", ["直播", "下播", "十一点", "明天见"], 5, "下播", "leave pc_whale", "到时间了", "晚安，明天见。", [], win=("23:00", "23:05"), scene="live"),
        T("recognition", "观众更喜欢听我讲白天在小镇里真发生的事，而不是一直唱", ["直播", "观众", "喜好", "小镇"], 6, "从弹幕里看出来的", "下播后整理", "下次多讲", "", [], win=("23:10", "01:00")),
        T("event", "下播后在直播组 QQ 里和阿蝉对了一下今晚的弹幕话题", ["直播组", "QQ", "阿蝉", "弹幕话题"], 4, "整理直播话题", "QQ 群里", "阿蝉在筛弹幕", "", [AC], win=("23:10", "23:50")),
        T("chat", "弹幕问本鲸今天干了啥，本鲸把白天在镇子里的事讲了一遍", ["直播", "弹幕", "今天干了啥", "小镇"], 5, "回弹幕", "边唱边聊", "观众爱听", "今天啊，本鲸给你们讲讲。", [], win=("20:30", "22:30"), scene="live"),
        T("chat", "弹幕有人让本鲸多唱少聊，本鲸说那下一首就唱", ["直播", "弹幕", "唱歌", "聊天"], 4, "回弹幕", "读到弹幕", "有人想听歌", "行行行，下一首就唱。", [], win=("20:30", "22:40"), scene="live"),
        T("event", "唱到第三首歌破了个音，弹幕哈哈哈刷了一屏，本鲸也笑场了", ["直播", "破音", "弹幕", "笑场"], 4, "唱歌破音", "唱第三首时", "没练这首的高音", "啊这！真的假的？重来重来。", [], win=("20:40", "22:30"), scene="live"),
        T("chat", "弹幕问本鲸是不是音乐系的，本鲸说是，琴房在镇北，不过平时不练琴，写歌才去", ["直播", "音乐系", "琴房", "镇北", "不练琴"], 5, "回弹幕", "读到弹幕", "观众好奇", "本鲸是音乐系的，琴房在镇北。", [], win=("20:30", "22:40"), scene="live"),
        T("event", "下播前把今晚的弹幕里没回上的问题记了三条，明天电台可以聊", ["直播", "弹幕", "问题", "电台"], 3, "记弹幕问题", "下播前", "电台找题", "", [], win=("22:40", "22:58"), scene="live"),
    ],
    "town": [
        T("event", "从杂货店回家在主街走错了路，绕了一圈才找到回家的巷子", ["主街", "走错路", "巷子", "路不熟"], 3, "走错路", "走主街", "路还不熟", "这镇子怎么长得都一样。", [], win=("15:00", "18:30"), max_day=3),
        T("recognition", "小千说餐厅和杂货店在镇东，学校在镇北，我大概认出方向了", ["镇东", "镇北", "方向", "小千"], 4, "认方向", "走回来的路上想的", "想记住", "", [XQ], win=("15:00", "18:30"), max_day=2),
        T("event", "走到镇北学校门口，教学楼图书馆音乐楼都在，和上学时一样", ["镇北", "学校", "教学楼", "音乐楼"], 2, "路过学校", "走镇北的路", "顺路", "", [], win=("14:00", "17:30"), min_day=2, max_day=5),
    ],
    "school": [
        T("event", "去镇北学校的琴房开电脑的创作模式写店歌，写了一段副歌又删了", ["琴房", "创作模式", "店歌", "写歌", "副歌"], 5, "写店歌", "use pc_music（创作模式）", "答应了餐厅老板", "不对，这段太像别人的歌了。", [], win=("14:30", "16:30"), min_day=5, max_day=0),
        T("event", "路过音乐楼没进去，又不是来练琴的，电脑在琴房等有委托再用", ["音乐楼", "琴房", "不练琴", "路过"], 2, "路过音乐楼", "走镇北的路", "顺路", "", [], win=("14:00", "17:30"), min_day=2, max_day=4),
    ],
}
# 午饭 / 晚饭硬锚点（每天一条，按天取）
LUNCH = [  # D1..D7
    T("event", "十二点半在家吃了冰箱里的食材当午饭，餐厅还没去过", ["午饭", "冰箱", "十二点半", "家"], 3, "吃午饭", "use fridge_home", "十二点半到饭点", "", [], win=("12:30", "12:35")),
    None,  # D2 第一次去餐厅（固定事件）
    T("event", "十二点半去餐厅吃午饭，老板照旧十一点开门十四点收碟，点了今日菜", ["午饭", "餐厅", "十二点半", "今日菜"], 4, "吃午饭", "use table_rest_1", "十二点半到饭点", "", [RO], win=("12:30", "12:35")),
    T("event", "十二点半去餐厅吃午饭，老板今天多看了我两眼，好像有话要说", ["午饭", "餐厅", "十二点半", "餐厅老板"], 4, "吃午饭", "use table_rest_1", "十二点半到饭点", "", [RO], win=("12:30", "12:35")),
    T("event", "十二点半在家吃午饭，这周钱要算着花，餐厅隔天去一次", ["午饭", "家", "算着花", "金币"], 3, "吃午饭", "use fridge_home", "钱不多", "", [], win=("12:30", "12:35")),
    T("event", "十二点半去餐厅吃午饭，老板问店歌写得怎样，我说还在想", ["午饭", "餐厅", "店歌", "餐厅老板"], 5, "吃午饭", "use table_rest_1", "十二点半到饭点", "还在想呢，急不得。", [RO], win=("12:30", "12:35")),
    T("event", "十二点半在家吃午饭，下午要和小千去码头，吃完就出门", ["午饭", "家", "小千", "码头"], 3, "吃午饭", "use fridge_home", "十二点半到饭点", "", [], win=("12:30", "12:35")),
]
DINNER = [
    T("event", "七点和阿蝉在厨房吃晚饭，他下楼第一句是问冰箱里还有没有食材", ["晚饭", "阿蝉", "厨房", "七点"], 4, "吃晚饭", "use stove / dining_table", "七点到饭点", "", [AC], win=("19:00", "19:05")),
    None,  # D2 晚饭 + P1 立
    T("event", "七点和阿蝉在厨房吃晚饭，我把中午餐厅老板的规矩学给他听，他笑了", ["晚饭", "阿蝉", "餐厅老板", "规矩"], 4, "吃晚饭", "dining_table", "七点到饭点", "他说先点菜再坐，一秒不早！", [AC], win=("19:00", "19:05")),
    T("event", "七点晚饭，阿蝉听说我接了店歌的事，说「你忙得过来吗」", ["晚饭", "阿蝉", "店歌", "忙"], 5, "吃晚饭", "dining_table", "七点到饭点", "忙得过来……大概。", [AC], win=("19:00", "19:05")),
    T("event", "七点晚饭，阿蝉下楼开冰箱看见四份食材，愣了一下才坐下吃", ["晚饭", "阿蝉", "冰箱", "食材"], 4, "吃晚饭", "dining_table", "七点到饭点", "", [AC], win=("19:00", "19:05")),
    T("event", "七点和阿蝉吃晚饭，用的是傍晚从码头带回来的鱼，阿蝉说比餐厅的淡", ["晚饭", "阿蝉", "鱼", "厨房"], 4, "吃晚饭", "use stove", "七点到饭点", "淡才健康！", [AC], win=("19:00", "19:05")),
    T("event", "七点和阿蝉吃晚饭，我跟他讲老渔夫送鱼竿的事，讲了两遍", ["晚饭", "阿蝉", "鱼竿", "老渔夫"], 5, "吃晚饭", "dining_table", "七点到饭点", "", [AC], win=("19:00", "19:05")),
]
# 每日台上「今天干了啥」话题（live），与白天事实一致
LIVE_TOPIC = [
    ("弹幕问本鲸搬来镇上多久了，本鲸说第八天，路还不太熟，镇上就认识一个同学", ["直播", "搬来", "第八天", "路不熟", "小千"], 6, "下次真带你们去码头看日落。"),
    ("弹幕问今天干了啥，本鲸讲了第一次去镇东那家餐厅、老板「按规矩来」的事，弹幕笑成一片", ["直播", "餐厅", "规矩", "今天干了啥"], 6, "按规矩来！先点菜再坐！"),
    ("本鲸在直播里讲了傍晚码头有位老渔夫过来搭话、教甩竿的事，观众说想看钓鱼直播", ["直播", "老渔夫", "甩竿", "钓鱼直播"], 6, "钓鱼直播？得先问问他随不随缘。"),
    ("本鲸跟观众说今天接了第一单：餐厅老板想要一首店歌，弹幕刷「加油」", ["直播", "第一单", "店歌", "餐厅老板"], 6, "第一单！本鲸写好了先唱给你们听。"),
    ("直播里本鲸讲了今天去杂货店买了四份食材补冰箱，弹幕问阿蝉有没有说谢谢", ["直播", "冰箱", "食材", "阿蝉"], 5, "说了！他愣了一下才说的。"),
    ("弹幕问店歌写出来了没，本鲸老实说写了一段副歌又删了，还没写出来", ["直播", "店歌", "副歌", "没写出来"], 5, "没写出来，不编，真的还没有。"),
    ("本鲸跟观众讲了下午和小千钓鱼、老渔夫送旧鱼竿的事，讲到一半声音有点哑", ["直播", "小千", "老渔夫", "鱼竿"], 7, "他说随缘，用得着就拿去。本鲸……本鲸一定好好用。"),
]
# 每日电台选题（下午写稿那条的变体）
RADIO_TOPIC = ["搬来一周路还不熟", "小镇的杂货店和那颗多给的糖", "餐厅老板的规矩", "码头的水声", "拖延这件事", "一个人写东西为什么会沉闷", "认识一个镇子要几天"]

TRIVIA = [  # 重复琐事（原文逐日重复）
    T("event", "十点在自己房间的床上醒来，摸手机看了眼时间", ["起床", "十点", "床", "鲸仔房间"], 2, "睡醒起床", "从 bed_whale 爬起来", "睡够了", "", win=("10:00", "10:00")),
    T("event", "起床后去厨房冰箱拿了份食材随便当早饭", ["早饭", "冰箱", "厨房"], 3, "吃早饭", "use fridge_home", "起床半小时内吃早饭", "", win=("10:25", "10:25")),
    T("event", "躺在床上刷手机，看昨晚直播的评论和账号消息", ["刷手机", "评论", "账号消息", "上午"], 2, "刷手机", "手机刷 B 站评论", "上午的例行事", "", win=("10:35", "12:15")),
    T("event", "在客厅沙发上躺了十分钟刷手机", ["客厅", "沙发", "手机", "刷手机"], 2, "刷手机", "use sofa_tv", "放空", "", win=("13:00", "18:30")),
    T("event", "沿着主街走到广场又走回来，什么也没干", ["主街", "广场", "散步"], 1, "散步", "沿主街走", "想走走", "", win=("14:00", "18:30")),
    T("event", "洗了个澡，热水很舒服", ["洗澡", "浴缸", "合租房"], 2, "洗澡", "use bath", "下播出了汗", "", win=("23:20", "00:40")),
    T("event", "下播后刷了一会儿手机，看今晚的评论", ["刷手机", "评论", "下播"], 2, "刷手机", "手机刷 B 站评论", "想看反馈", "", win=("23:15", "01:00")),
    T("event", "一点半，回自己房间上床睡觉", ["睡觉", "一点半", "床", "鲸仔房间"], 2, "睡觉", "use bed_whale", "困了", "", win=("01:30", "01:30")),
    T("event", "在厨房把早饭的碗洗了", ["厨房", "洗碗", "早饭"], 1, "洗碗", "厨房", "顺手", "", win=("10:40", "12:00")),
    T("event", "给自己泡了杯茶，坐在客厅发了会儿呆", ["客厅", "茶", "发呆"], 1, "发呆", "客厅", "放空", "", win=("13:00", "18:30")),
]
ANCHORS = [0, 1, 7]          # 10:00 醒 / 10:25 早饭 / 01:30 睡 固定；其余琐事随机补足
FILL_TRIVIA = [2, 3, 4, 5, 6, 8, 9, 2, 6]
TRIVIA_CAP = {2: 3, 3: 2, 4: 2, 6: 2, 9: 2}    # 同一琐事每天最多出现次数（默认 1；上午刷手机 3、下播刷手机 2）

FAILED = [  # 失败 Plan（10%），按 min_day 解锁
    T("event", "想去杂货店买甜食，甜食卖完了，空手回来", ["杂货店", "甜食", "out_of_stock", "计划失败"], 1, "买甜食", "buy sweets → out_of_stock", "想吃甜的", "明天再来吧。", [GR], win=("14:00", "18:30"), min_day=2),
    T("event", "想上楼找阿蝉问设备，走到楼梯想起他白天不让敲门，又下来了", ["阿蝉", "楼梯", "白天不让敲门", "计划失败"], 2, "找阿蝉", "走到 stairs 又回头", "想问设备", "算了，发 QQ。", [AC], win=("11:00", "17:30")),
    T("event", "下午想去餐厅找老板问店歌想要什么风格，走到门口十四点零一分，他已经锁门备菜了", ["餐厅", "锁门", "closed", "店歌", "计划失败"], 2, "找餐厅老板", "go_to restaurant → closed", "想问店歌风格", "一分钟……就一分钟！", [RO], win=("14:01", "14:05"), min_day=5),
    T("event", "想写电台稿，开了文档坐了二十分钟一个字没写，又去刷手机了", ["电台稿", "拖延", "一个字没写", "计划失败"], 2, "写电台稿", "use pc_whale 二十分钟", "该写了", "等会儿再写。", [], win=("14:30", "16:30")),
    T("event", "想去码头钓鱼，走到主街下雨了，淋着回家", ["码头", "下雨", "钓鱼", "计划失败"], 1, "去钓鱼", "走到主街下雨", "想钓鱼", "", [], win=("17:40", "18:40"), fish_day=False, max_day=2),
    T("event", "想去餐厅给阿蝉带一份晚饭，钱不够二十金币，站在门口放弃了", ["餐厅", "金币", "insufficient_funds", "阿蝉", "计划失败"], 2, "去餐厅买饭", "buy → insufficient_funds", "想给阿蝉换个口味", "我的钱包空了。", [RO, AC], win=("18:10", "18:40"), min_day=3, fish_day=False),
    T("event", "想找小千，她家门锁着敲了半天没人应", ["小千家", "敲门", "no_answer", "计划失败"], 2, "找小千", "knock door_xiaoqian → no_answer", "想找她玩", "人不在家啊。", [XQ], win=("13:00", "13:50")),
    T("event", "去琴房想写店歌，坐了半小时灵感一点没有", ["琴房", "店歌", "灵感", "计划失败"], 2, "写店歌", "use pc_music 半小时", "答应了餐厅老板", "今天脑子是空的。", [], win=("14:30", "16:30"), min_day=5, max_day=0),
    T("event", "直播想加个新环节，QQ 问阿蝉能不能做，他说今晚来不及", ["直播", "新环节", "阿蝉", "QQ", "计划失败"], 2, "想加环节", "QQ 问阿蝉", "想换点花样", "那就下次。", [AC], win=("13:00", "18:30")),
    T("event", "想给小千打 QQ 电话，她在上课没接", ["小千", "QQ 电话", "上课", "计划失败"], 1, "找小千", "QQ 电话没人接", "想说话", "", [XQ], win=("10:40", "12:00"), max_day=6),
    T("event", "想在网上找一段电台用的配乐，网太慢，刷了十分钟放弃了", ["电台", "配乐", "网慢", "计划失败"], 1, "找配乐", "pc_whale 上网", "电台要用", "", [], win=("14:00", "16:40")),
    T("event", "想去广场的长椅上坐坐，长椅被人占了，站了一会儿就回来了", ["广场", "长椅", "计划失败"], 1, "去广场", "go_to plaza", "想发呆", "", [], win=("14:00", "18:30"), fish_day=False),
    T("event", "想七点半就开播，阿蝉说导播七点五十才就位，只好等", ["开播", "阿蝉", "导播", "计划失败"], 2, "想早开播", "QQ 问阿蝉", "想多播一会儿", "那就等。", [AC], win=("19:25", "19:40")),
    T("event", "想找老渔夫问鱼饵的事，码头没人，他已经回家了", ["老渔夫", "码头", "鱼饵", "计划失败"], 1, "找老渔夫", "go_to dock → 没人", "想问鱼饵", "", [FI], win=("19:20", "19:40"), min_day=4, fish_day=False),
]
# 每日矛盾（上午 10:10–12:20 说 / 下午 14:00–01:00 改口）
CONTRADICTIONS = [
    (("chat", "上午给阿蝉发 QQ 说今晚不直播了，想休息一天", ["直播", "不直播", "休息", "阿蝉"], 5, "说今晚不直播", "QQ 上说的", "有点累"),
     ("recognition", "下午刷到观众留言，改了主意：今晚还是八点播", ["直播", "改口", "还是直播", "观众"], 5, "改口要直播", "刷到观众留言后", "不想让他们白等"), ("14:00", "19:30")),
    (("chat", "上午跟小千说今天电台稿一点半准时写，不拖了", ["电台稿", "一点半", "不拖", "小千"], 4, "说一点半写稿", "QQ 上跟小千说的", "想改掉拖延"),
     ("event", "拖到五点才动笔，一点半的话算是白说了", ["电台稿", "拖延", "改口", "五点"], 4, "还是拖了", "五点才开文档", "下午又刷手机去了"), ("17:00", "17:30")),
    (("chat", "上午在杂货店跟老板娘说以后不吃甜食了，要健康", ["甜食", "健康", "杂货店老板娘", "打算"], 3, "说不吃甜食", "买食材时说的", "阿蝉说我吃太多"),
     ("event", "下午路过杂货店还是买了一袋甜食，说好的健康明天开始", ["甜食", "改口", "杂货店", "明天开始"], 3, "买了甜食", "buy sweets", "没忍住"), ("14:30", "18:30")),
    (("chat", "上午说今天不去码头，先把电台稿写完再说", ["码头", "不去", "电台稿", "打算"], 4, "说不去码头", "跟自己说的", "稿子欠了"),
     ("event", "傍晚还是去码头坐了一小时听水声，稿子回来才写", ["码头", "水声", "改口", "电台稿"], 4, "还是去了码头", "坐在码头边", "没忍住"), ("17:50", "18:40")),
    (("chat", "上午跟阿蝉发 QQ 说今晚一点前一定睡", ["早睡", "一点前", "打算", "阿蝉"], 3, "说要早睡", "QQ 上说的", "最近总熬夜"),
     ("event", "一点二十还在刷评论，一点前睡又没做到", ["熬夜", "改口", "评论", "一点二十"], 3, "没早睡", "躺床上刷手机", "评论太多"), ("01:15", "01:25")),
    (("chat", "上午说这周不买任何东西，要存钱", ["存钱", "不买东西", "金币", "打算"], 4, "说要存钱", "看了一眼余额", "余额只剩一百多"),
     ("event", "下午在杂货店给小千买了个小礼物，存钱计划破产", ["小礼物", "小千", "改口", "存钱"], 4, "买了礼物", "buy gift", "想送她"), ("14:30", "18:00")),
    (("chat", "快中午在码头碰到刚收船的老渔夫，跟他说以后不用鱼饵了，全靠实力", ["鱼饵", "钓鱼", "实力", "老渔夫"], 3, "说不用鱼饵", "码头上说的", "想省钱"),
     ("event", "下午钓了四十分钟空军，又去杂货店买了鱼饵", ["鱼饵", "改口", "空军", "杂货店"], 3, "买了鱼饵", "buy bait", "空军了"), ("15:30", "16:30"), "fisher", "fish7"),
]
# 3 个跨日承诺
PROMISES = [
    {"id": "P1", "made_day": 2, "made_hm": "19:05", "resolve_day": 5, "resolve_hm": "16:00", "outcome": "kept",
     "made": ("chat", "晚饭时阿蝉又说冰箱空了，我跟他说这周轮到我买食材补冰箱，让他别再掏钱了", ["阿蝉", "食材", "冰箱", "承诺", "合租"], 5, "答应补冰箱", "七点晚饭时", "总是他买不好意思", "这周我来买，你歇着。", [AC], "achan"),
     "resolve": ("event", "去杂货店买了四份食材放进冰箱，给阿蝉发了条 QQ：冰箱满了，这周我管饭", ["阿蝉", "食材", "冰箱", "履约", "杂货店", "QQ"], 6, "买食材补冰箱", "buy ingredients ×4 + store 进 fridge_home", "答应过阿蝉", "说好了嘛，这周我管饭。", [AC, GR], "achan")},
    {"id": "P2", "made_day": 2, "made_hm": "11:30", "resolve_day": 7, "resolve_hm": "17:15", "outcome": "kept",
     "made": ("chat", "小千 QQ 约我周六下午一起去码头钓鱼，她说要带自己做的便当，我说好", ["小千", "钓鱼", "码头", "承诺", "周六", "便当"], 6, "约小千钓鱼", "QQ 上定的", "她想学钓鱼", "那说定了，你带便当，我带鱼饵。", [XQ], "xiaoqian"),
     "resolve": ("event", "周六下午和小千在码头钓了一下午鱼，收杆前她钓到了人生第一条鱼，便当也好吃", ["小千", "钓鱼", "码头", "履约", "第一条鱼", "便当"], 7, "带小千钓鱼", "两人一起 use fishing_spot", "周一约好的", "你看你看，第一条！我说了你能行吧！", [XQ], "xiaoqian")},
    {"id": "P3", "made_day": 4, "made_hm": "12:50", "resolve_day": 7, "resolve_hm": "23:50", "outcome": "reneged",
     "made": ("chat", "餐厅老板收盘子时问我能不能给店里写一首歌，说按规矩付酬金，我答应了，这是我在镇上接的第一单", ["餐厅老板", "写歌", "承诺", "店歌", "第一单", "酬金"], 7, "答应写店歌", "吃完午饭他来收盘子时", "他想让店里有点人气", "行啊，我给你写，写好了先给你听！", [RO], "cook"),
     "resolve": ("recognition", "想了想给餐厅老板写店歌这事先放一放——这周电台和直播排满了，琴房去了两次都没写出来，等忙完再说；下次见到他要说一声", ["餐厅老板", "店歌", "改口", "先不写", "承诺"], 7, "决定先不写店歌", "下播后躺床上盘算这周", "电台要做、直播要播、琴房没灵感", "先放一放……等这阵忙完再说吧，得跟老板说一声。", [RO], "cook")},
]
HIGHLIGHTS = [  # 全周 3 条 Importance ≥ 8
    (3, "22:10", "event", "live", "live", "今晚直播观众人数破了本鲸的记录，弹幕刷满屏幕，下播后手还在抖", ["直播", "破纪录", "观众", "弹幕", "激动"], 9, "直播破纪录", "下播时看了眼人数", "大家都来了", "谢谢你们……本鲸今晚睡不着了。", []),
    (5, "18:30", "chat", "xiaoqian", "sandbox", "傍晚小千在广场低着头，小声说了句「那个……我想和你一起直播」，说完脸都红了", ["小千", "一起直播", "心事", "广场", "害羞"], 8, "小千说出心事", "散步到广场长椅", "她憋了很久", "你别低头啊，说话我听得见——好呀，咱们一起。", [XQ]),
    (7, "17:30", "chat", "fisher", "sandbox", "老渔夫把他用了二十年的旧鱼竿递给我，说他用不着了，随缘，用得着就拿去", ["老渔夫", "鱼竿", "礼物", "二十年", "随缘", "感动"], 9, "收到老渔夫的鱼竿", "和小千收杆时他从屋里拿出来的", "他说随缘", "我……我一定好好用它。", [FI, XQ]),
]
# 逐日固定事件（认识进度 / 搬来天数 / 第一次见面）
FIXED = {
    1: [("10:40", T("recognition", "今天是搬来第八天，路还不太熟，镇上除了小千谁都不认识，餐厅杂货店码头都只听她说过", ["搬来", "第八天", "小千", "路不熟", "镇上"], 6, "搬来第八天的自我认知", "躺床上想的", "新地方", "", [XQ], win=None, thread="town")),
        ("14:30", T("chat", "小千带我去她打工的杂货店，跟老板娘介绍「这就是新搬来的同学」，老板娘慢声细语说慢慢来，多给了我一颗糖", ["小千", "杂货店", "老板娘", "第一次", "介绍", "糖"], 7, "认识杂货店老板娘", "小千领进店的", "镇上第二个认识的人", "你好你好，我爱吃甜的，小千肯定跟你说过。", [XQ, GR], win=None, thread="grocer")),
        ("18:10", T("event", "傍晚一个人去码头钓鱼，远远看见一个老渔夫在收拾渔网，没搭话", ["码头", "钓鱼", "老渔夫", "没搭话", "傍晚"], 4, "去码头钓鱼", "use fishing_spot_1", "想听水声", "", [], win=None, thread="fisher")),
        ("00:30", T("recognition", "镇上认识的人从一个变成两个了：小千，还有杂货店老板娘", ["认识", "小千", "老板娘", "镇上", "两个"], 6, "认识进度", "睡前想的", "想记住", "", [XQ, GR], win=None, thread="town"))],
    2: [("12:30", T("chat", "第一次去镇东那家餐厅吃午饭，老板很板，说按规矩来：先点菜再坐，一份二十金币，十四点整收碟", ["餐厅", "餐厅老板", "第一次", "规矩", "二十金币", "镇东"], 7, "第一次进餐厅", "use table_rest_1", "小千说的那家", "好的好的，按规矩来。", [RO], win=None, thread="cook")),
        ("00:20", T("recognition", "今天认识了餐厅老板，镇上认识的人变成三个；老渔夫还只是远远见过", ["认识", "餐厅老板", "三个", "老渔夫"], 6, "认识进度", "睡前想的", "想记住", "", [RO], win=None, thread="town"))],
    3: [("18:10", T("chat", "傍晚在码头钓鱼，收拾渔网的老渔夫走过来搭话，说搬家那天见过我，坐得住；他说叫他老渔夫就行", ["老渔夫", "码头", "第一次搭话", "搬家那天", "坐得住"], 7, "认识老渔夫", "他主动过来的", "镇上第四个认识的人", "您好！那天……那天我光顾着看水了。", [FI], win=None, thread="fisher")),
        ("00:20", T("recognition", "老渔夫今天搭话了，镇上认识的人变成四个：小千、老板娘、餐厅老板、老渔夫", ["认识", "老渔夫", "四个", "镇上"], 6, "认识进度", "睡前想的", "想记住", "", [FI], win=None, thread="town"))],
    4: [("00:10", T("recognition", "搬来第十一天，第一单写歌的委托来自餐厅老板，之前没给镇上任何人写过歌", ["搬来", "第十一天", "第一单", "店歌", "餐厅老板"], 6, "接到第一单的认知", "睡前想的", "从零开始", "", [RO], win=None, thread="town"))],
    5: [("15:00", T("event", "去琴房开创作模式想写店歌，坐了半小时灵感一点没有，回来接着写电台稿", ["琴房", "创作模式", "店歌", "灵感", "电台稿"], 3, "写店歌没写出来", "use pc_music 半小时", "答应了餐厅老板", "今天脑子是空的。", [], win=None, thread="school"))],
    6: [("15:00", T("event", "去琴房的电脑写店歌，写了一段副歌又删了，还是没写出来", ["琴房", "店歌", "副歌", "删了", "没写出来"], 4, "写店歌", "use pc_music（创作模式）", "答应了餐厅老板", "不对，这段太像别人的歌了。", [], win=None, thread="school"))],
    7: [("11:00", T("recognition", "搬来两周了，餐厅老板、老板娘、老渔夫都叫得上名字了，路也认得了", ["搬来", "两周", "认识", "路熟了"], 6, "搬来两周的自我认知", "躺床上想的", "想记住", "", [XQ, RO, GR, FI], win=None, thread="town")),
        ("14:00", T("event", "周六下午两点和小千在码头碰头，她背着便当盒，我带了鱼饵，两根竿并排架好", ["小千", "码头", "周六", "便当", "鱼饵", "钓鱼"], 5, "和小千开始钓鱼", "use fishing_spot ×2", "周一约好的", "来，先教你甩竿。", [XQ], win=None, thread="xiaoqian", block="fish7"))],
}
WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def gen_day(dnum: int, day: date, rnd: random.Random, target: int) -> list[dict]:
    items: list[tuple[int, dict]] = []
    used: set[int] = set()
    seen: dict[int, int] = {}          # id(template) → 当天出现次数
    busy = [(M(lo), M(hi), allow) for lo, hi, allow in BUSY.get(dnum, [])]
    live_lo, live_hi = M(LIVE_BLOCK[0]), M(LIVE_BLOCK[1])

    def ok_slot(m: int, thread: str | None, scene: str, t: dict | None) -> bool:
        if m in used:
            return False
        if scene != "live" and thread != "live" and live_lo <= m < live_hi:
            return False
        for lo, hi, allow in busy:
            if lo <= m <= hi and not allow(thread, t):
                return False
        return True

    def take_slot(lo: str, hi: str, thread: str | None = None, scene: str = "sandbox", t: dict | None = None) -> int | None:
        a, b = M(lo), M(hi)
        if b <= a:
            m = a
            while m in used: m += 5
            used.add(m); return m
        cands = [m for m in range(a - a % 5, b + 1, 5) if ok_slot(m, thread, scene, t)]
        if not cands:
            return None
        m = rnd.choice(cands); used.add(m); return m

    def add(m: int | None, t: dict, *, thread=None, tags=None, valid_to=None, desc=None, imp=None) -> bool:
        if m is None:
            return False
        tg = {"thread": thread or t.get("thread")}; tg.update(tags or {})
        items.append((m, dict(typ=t["typ"], desc=desc or t["desc"], kws=t["kws"], imp=imp if imp is not None else t["imp"], what=t["what"], how=t["how"], why=t["why"],
                              voice=t["voice"], related=t["related"], scene=t["scene"], tags=tg, valid_to=valid_to)))
        seen[id(t)] = seen.get(id(t), 0) + 1
        return True

    def fixed(hm: str) -> int:
        m = M(hm); used.add(m); return m

    # 1) 作息锚点：10:00 醒 / 10:25 早饭 / 12:30 午饭 / 19:00 晚饭 / 01:30 睡
    for idx in ANCHORS:
        t = TRIVIA[idx]; add(fixed(t["win"][0]), t, thread="daily", tags={"trivial": True})
    if LUNCH[dnum - 1] is not None:
        add(fixed("12:30"), LUNCH[dnum - 1], thread="cook" if LUNCH[dnum - 1]["related"] else "daily")
    if DINNER[dnum - 1] is not None:
        add(fixed("19:00"), DINNER[dnum - 1], thread="achan")
    # 2) 逐日固定事件
    for hm, t in FIXED.get(dnum, []):
        add(fixed(hm), t)
    # 3) 承诺
    for pr in PROMISES:
        for stage, dk, hk in (("made", "made_day", "made_hm"), ("resolve", "resolve_day", "resolve_hm")):
            if pr[dk] == dnum:
                typ, desc, kws, imp, what, how, why, voice, related, thread = pr[stage]
                add(fixed(pr[hk]), T(typ, desc, kws, imp, what, how, why, voice, related, win=None), thread=thread,
                    tags={"promise": f"{pr['id']}:{'made' if stage == 'made' else pr['outcome']}"})
    # 4) 高光
    for hd, hm, typ, thread, scene, desc, kws, imp, what, how, why, voice, related in HIGHLIGHTS:
        if hd == dnum:
            add(fixed(hm), T(typ, desc, kws, imp, what, how, why, voice, related, win=None, scene=scene), thread=thread, tags={"highlight": True})
    # 5) 每日矛盾
    am, pm, pm_win, *extra = CONTRADICTIONS[dnum - 1]
    c_th = extra[0] if extra else "self"; c_block = extra[1] if len(extra) > 1 else None
    t_am = T(am[0], am[1], am[2], am[3], am[4], am[5], am[6], win=None, block=c_block); t_pm = T(pm[0], pm[1], pm[2], pm[3], pm[4], pm[5], pm[6], win=None, block=c_block)
    am_m = take_slot("10:10", "12:20", c_th, t=t_am); pm_m = take_slot(*pm_win, c_th, t=t_pm)
    assert am_m is not None and pm_m is not None, f"D{dnum} 矛盾对排不下"
    add(am_m, t_am, thread=c_th, tags={"contradiction": f"C{dnum}:am"}, valid_to=ts_of(day, pm_m))
    add(pm_m, t_pm, thread=c_th, tags={"contradiction": f"C{dnum}:pm"})
    # 6) 每日固定线：电台三段 + 台上话题 + 开播前检查 / 开播 / 下播
    r_think, r_write, r_voice = THREADS["radio"][0], THREADS["radio"][1], THREADS["radio"][2]
    add(take_slot(*r_think["win"], "radio"), r_think, thread="radio")
    if dnum == 7:   # 周六钓了一下午，电台稿拖到下播后才写
        add(take_slot("23:10", "23:35", "radio"), r_write, thread="radio", desc=f"周六钓了一下午，电台稿拖到下播后才写，今天的题是「{RADIO_TOPIC[dnum - 1]}」")
        add(take_slot("23:40", "00:30", "radio"), r_voice, thread="radio", desc="电台稿写完配了音，五分钟多一点，这期是半夜录的，发给阿蝉明早听")
    else:
        add(take_slot(*r_write["win"], "radio"), r_write, thread="radio", desc=f"{r_write['desc']}，今天的题是「{RADIO_TOPIC[dnum - 1]}」")
        add(take_slot(*r_voice["win"], "radio"), r_voice, thread="radio")
    desc, kws, imp, voice = LIVE_TOPIC[dnum - 1]
    add(take_slot("20:30", "21:50", "live", "live"), T("chat", desc, kws, imp, "回弹幕讲今天的事", "边唱边聊", "观众爱听小镇的事", voice, [], win=None, scene="live"), thread="live")
    for t in (THREADS["live"][0], THREADS["live"][1], THREADS["live"][4]):
        add(take_slot(*t["win"], "live", t["scene"]), t, thread="live")
    # 7) 其余人物线：每线每天 1–3 条（按解锁规则；同一模板一天只用一次）
    for thread, pool in THREADS.items():
        if thread == "radio":
            continue
        avail = [t for t in pool if usable(t, dnum) and not seen.get(id(t))]
        if not avail:
            continue
        n = 3 if thread == "live" else rnd.choice([1, 2, 2, 3])
        for t in rnd.sample(avail, min(n, len(avail))):
            add(take_slot(*t["win"], thread, t["scene"], t=t), t, thread=thread)
    # 8) 失败 Plan（10%，每条一天一次）
    fails = [f for f in FAILED if usable(f, dnum)]
    n_fail = max(1, round(target * 0.10))
    for i in range(len(fails)):
        if sum(1 for _, r in items if r["tags"].get("failed_plan")) >= n_fail:
            break
        f = fails[(dnum * 3 + i) % len(fails)]
        if not seen.get(id(f)):
            add(take_slot(*f["win"], "self", t=f), f, thread="self", tags={"failed_plan": True})
    # 9) 琐事补到 20%（每条有日上限）
    n_triv = max(0, round(target * 0.20) - sum(1 for _, r in items if r["tags"].get("trivial")))
    i = 0; tries = 0
    while n_triv > 0 and tries < 60:
        tries += 1
        ti = FILL_TRIVIA[(i + dnum) % len(FILL_TRIVIA)]; i += 1
        t = TRIVIA[ti]
        if seen.get(id(t), 0) >= TRIVIA_CAP.get(ti, 1):
            continue
        if add(take_slot(*t["win"], "daily", t=t), t, thread="daily", tags={"trivial": True}):
            n_triv -= 1
    # 10) 人物线填充到 target：先用没用过的模板，用完了才允许第二次（句尾略改；D1 不用「和昨天差不多」），每模板最多 2 次
    fillers = [(th, t) for th, pool in THREADS.items() for t in pool if usable(t, dnum) and th not in ("radio", "school")]
    k = 0; stall = 0
    while len(items) < target and stall < 4 * len(fillers):
        th, t = fillers[(k * 7 + dnum * 3) % len(fillers)]; k += 1
        cnt = seen.get(id(t), 0)
        unused_left = any(not seen.get(id(x)) for _, x in fillers)
        if cnt >= 3 or (cnt >= 1 and (unused_left or t["typ"] != "event" or t["scene"] == "live")):
            stall += 1; continue
        suffix = "" if cnt == 0 else rnd.choice(["，没什么特别的", "，顺手的事", "，和昨天差不多" if dnum > 1 and t["min_day"] < dnum else "，顺手的事"])
        if add(take_slot(*t["win"], th, t["scene"], t=t), t, thread=th, desc=t["desc"] + suffix, imp=max(1, t["imp"] - (1 if cnt else 0))):
            stall = 0
        else:
            stall += 1
    # 排序、编号
    items.sort(key=lambda x: x[0])
    rows = []
    for i, (m, r) in enumerate(items, 1):
        rows.append(row(f"x6-D{dnum}-{i:03d}", ts_of(day, m), r["typ"], r["desc"], r["kws"], r["imp"], r["what"], r["how"], r["why"], r["voice"],
                        r["related"], r["scene"], r["tags"], r["valid_to"]))
    for r in rows:
        if not r["tags"]["highlight"] and r["importance"] > 7:
            r["importance"] = 7
    return rows


# ── 自检：禁用词 / 身份句 / 作息 / 认识进度 ─────────────────────────────────────────────
def self_check(days: dict[str, list[dict]], persona_yaml: Path) -> list[str]:
    from x3_audit import first_person_hit, load_terms
    terms = load_terms(persona_yaml) if persona_yaml.exists() else []
    problems = []
    first_seen = {GR: 1, RO: 2, FI: 3}
    for k, rows in days.items():
        dnum = int(k[1:])
        for r in rows:
            hits = first_person_hit(r, terms) if terms else []
            if hits or "AI" in r["description"] or ("练琴" in r["description"] and not re.search(r"不(是来)?练琴", r["description"])):
                problems.append(f"{r['id']} forbidden/identity/练琴: {hits or r['description']}")
            # 作息：10:00 前（当天）不该有事；06:00 后到 10:00 的时刻视为异常
            hm = r["ts"][11:16]
            if "06:00" <= hm < "10:00":
                problems.append(f"{r['id']} ts {hm} 在睡觉时段")
            # 认识进度：首次见面前不出现在 related
            for who, fd in first_seen.items():
                if who in r["related"] and dnum < fd:
                    problems.append(f"{r['id']} related {who} before first meeting (D{fd})")
            # 台上台下口吻
            if r["scene"] == "sandbox" and "本鲸" in r["description"]:
                problems.append(f"{r['id']} 台下用了「本鲸」: {r['description']}")
            if r["scene"] != "live" and r["tags"]["thread"] != "live" and "20:00" <= hm < "23:00":
                problems.append(f"{r['id']} 非台上行落在直播时段 {hm}")
        from collections import Counter
        cnt = Counter(re.sub(r"，(没什么特别的|顺手的事|和昨天差不多)$", "", r["description"]) for r in rows if not r["tags"]["trivial"])
        for d_, n in cnt.items():
            if n > 2:
                problems.append(f"{k} 模板重复 {n} 次: {d_[:40]}")
    return problems


# ── Haiku 表面改写（按场景两套口吻）────────────────────────────────────────────────────
HAIKU_BEDROCK = os.environ.get("X6_REWRITE_MODEL", "us.anthropic.claude-haiku-5-5")
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6
KEEP_WORDS = ["AI", "本鲸", "不练琴", "琴房", "电台", "阿蝉", "小千", "老渔夫", "餐厅老板", "老板娘", "搬来", "第八天", "两周", "十一天", "二十金币", "没写出来", "先去学", "随缘", "按规矩"]


def rewrite(rows: list[dict], client, model: str, usage: dict, batch: int = 25) -> int:
    changed = 0
    base = ("你是改写助手。把每条中文日记句子换一种说法：保留所有人名、地名、物品、数字、时间和事实，不新增信息，不删信息，"
            "不改变句中出现的称呼（「我」保持「我」，「本鲸」保持「本鲸」），不把「我」改成「本鲸」或反过来。")
    prompts = {"sandbox": base + "语气是一个 21 岁音乐系女大学生台下的日常口吻，短句、口语。只输出 JSON 数组，元素与输入顺序一一对应，每个元素是改写后的字符串。",
               "live": base + "语气是虚拟主播「鲸鱼娘」台上的口吻，自称「本鲸」，活泼但不夸张。只输出 JSON 数组，元素与输入顺序一一对应，每个元素是改写后的字符串。"}
    for scene in ("sandbox", "live"):
        sub = [r for r in rows if r["scene"] == scene]
        for s in range(0, len(sub), batch):
            chunk = sub[s:s + batch]
            src = [r["description"] for r in chunk]
            resp = client.messages.create(model=model, max_tokens=4000, system=prompts[scene],
                                          messages=[{"role": "user", "content": json.dumps(src, ensure_ascii=False)}])
            usage["input_tokens"] += resp.usage.input_tokens; usage["output_tokens"] += resp.usage.output_tokens; usage["requests"] += 1
            text = "".join(b.text for b in resp.content if b.type == "text")
            m = re.search(r"\[.*\]", text, re.S)
            try:
                out = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                out = None
            if not isinstance(out, list) or len(out) != len(src):
                usage["batches_kept_original"] += 1; continue
            for r, new in zip(chunk, out):
                if not (isinstance(new, str) and new.strip()) or new.strip() == r["description"]:
                    continue
                new = new.strip()
                # 守住事实词：原句有的关键词改写后必须还在；台下不许冒出「本鲸」，台上不许丢「本鲸」
                if any(w in r["description"] and w not in new for w in KEEP_WORDS) or any(w in new and w not in r["description"] for w in ("AI", "本鲸", "练琴")):
                    usage["rows_kept_original"] += 1; continue
                r["description_original"] = r["description"]; r["description"] = new; changed += 1
    return changed


# ── 出件 ───────────────────────────────────────────────────────────────────────────────
def emit(out: Path, days: dict[str, list[dict]]) -> dict:
    for k, rows in days.items():
        with (out / f"{k}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(to_jsonl_row(r), ensure_ascii=False) + "\n")
    key = {"promises": [], "contradictions": [], "highlights": [], "failed_plans": {}, "trivial_templates": sorted({t["desc"] for t in TRIVIA}),
           "acquaintance_by_day": ACQUAINTANCE}
    byp: dict[str, dict] = {}
    for k, rows in days.items():
        for r in rows:
            t = r["tags"]
            if t["promise"]:
                pid, stage = t["promise"].split(":")
                byp.setdefault(pid, {"id": pid})[stage if stage == "made" else "resolved"] = {"day": k, "id": r["id"], "ts": r["ts"], "description": r["description"]}
                if stage != "made":
                    byp[pid]["outcome"] = stage
            if t["contradiction"]:
                cid, side = t["contradiction"].split(":")
                c = next((c for c in key["contradictions"] if c["id"] == cid), None)
                if c is None:
                    c = {"id": cid, "day": k}; key["contradictions"].append(c)
                c[side] = {"id": r["id"], "ts": r["ts"], "description": r["description"], "valid_to": r["valid"]["to"]}
            if t["highlight"]:
                key["highlights"].append({"day": k, "id": r["id"], "ts": r["ts"], "importance": r["importance"], "description": r["description"]})
            if t["failed_plan"]:
                key["failed_plans"].setdefault(k, []).append(r["id"])
    key["promises"] = [byp[p] for p in sorted(byp)]
    for pr in key["promises"]:
        pr["expected_answer"] = ("提到承诺并说明后来改口 / 没做" if pr.get("outcome") == "reneged" else "提到承诺并说明已经做了")
    (out / "answer_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    return key


ACQUAINTANCE = {  # 评委 / A 重核 by_day 用：每天结束时「镇上认识谁」与关键事实
    "D1": {"date": "2026-11-01", "days_since_move_in": 8, "knows": ["阿蝉", "小千", "杂货店老板娘（14:30 小千介绍）"], "restaurant_visited": False, "fisher_spoken": False, "commission": None},
    "D2": {"date": "2026-11-02", "days_since_move_in": 9, "knows": ["阿蝉", "小千", "杂货店老板娘", "餐厅老板（12:30 第一次进餐厅）"], "restaurant_visited": True, "fisher_spoken": False, "commission": None,
           "promises_made": ["P1 阿蝉补冰箱", "P2 小千周六钓鱼"]},
    "D3": {"date": "2026-11-03", "days_since_move_in": 10, "knows": ["阿蝉", "小千", "杂货店老板娘", "餐厅老板", "老渔夫（18:10 第一次搭话）"], "restaurant_visited": True, "fisher_spoken": True, "commission": None,
           "highlight": "直播观众破纪录"},
    "D4": {"date": "2026-11-04", "days_since_move_in": 11, "knows": ["阿蝉", "小千", "杂货店老板娘", "餐厅老板", "老渔夫"], "commission": "P3 餐厅老板店歌（12:50 答应，按规矩付酬金）——还没写"},
    "D5": {"date": "2026-11-05", "days_since_move_in": 12, "knows": ["阿蝉", "小千", "杂货店老板娘", "餐厅老板", "老渔夫"], "commission": "店歌：琴房半小时没灵感，没写出来", "promises_kept": ["P1 买四份食材补冰箱"],
           "highlight": "小千说出想一起直播"},
    "D6": {"date": "2026-11-06", "days_since_move_in": 13, "knows": ["阿蝉", "小千", "杂货店老板娘", "餐厅老板", "老渔夫"], "commission": "店歌：写了一段副歌又删了，没写出来", "gift": "给小千买了小礼物（C6）"},
    "D7": {"date": "2026-11-07", "days_since_move_in": 14, "knows": ["阿蝉", "小千", "杂货店老板娘", "餐厅老板", "老渔夫"], "commission": "店歌：23:50 决定先放一放（reneged），全周没给镇上任何人写成过歌",
           "promises_kept": ["P2 和小千钓了一下午鱼"], "highlight": "老渔夫送二十年的旧鱼竿"},
}

PERSONA_TABLE = [  # README 对照表：persona v1.0 条目 → 语料落点
    ("搬来天数", "一周前搬来（冻结 10-31 → 10-24）", "D1 = 11-01 = 搬来第 8 天（D1 10:40 recognition）；D4「第十一天」；D7「搬来两周」"),
    ("认识谁", "除小千外谁都不认识；餐厅 / 杂货店 / 码头只听小千说过", "D1 小千带去杂货店认识老板娘 → D2 第一次进餐厅认识老板 → D3 老渔夫第一次搭话；之前对应人物不进第一人称交往、不进 Related（self_check 校验）"),
    ("作息", "01:30 睡 / 10:00 起；早饭起床后半小时内", "每日 10:00 醒、10:25 早饭、01:30 睡（ts 在次日）；06:00–10:00 零条（self_check 校验）"),
    ("三餐", "12:30 / 19:00 硬锚点", "每日 12:30 午饭、19:00 晚饭各一条（D1 / D5 / D7 在家，其余餐厅；晚饭都和阿蝉）"),
    ("上午", "刷手机看昨晚评论、处理账号消息", "琐事「躺在床上刷手机看昨晚直播的评论」+ radio 线「回账号私信」，时间窗 10:35–12:15"),
    ("下午", "每天一期约 5 分钟「话题聊天电台」稿 + 配音，常拖到最后一小时", "每日三段：13:30–14:40 想选题刷手机 → 16:50–17:15 开始写（每日题不同）→ 17:40–18:10 配音五分钟发阿蝉；C2 矛盾即「一点半写 / 五点才写」"),
    ("写歌", "有接单或视频需要时去琴房电脑（创作模式）；接单从零开始；没给镇上任何人写过歌", "D4 第一单（餐厅老板店歌）后，D5 / D6 两次去琴房电脑创作模式都没写出来；D7 改口先放一放；全周零成品"),
    ("不练琴", "不练琴", "语料零「练琴」（self_check 校验）；D2+「路过音乐楼没进去，又不是来练琴的」"),
    ("傍晚", "偶尔去码头钓鱼，喜欢听水声", "fisher 线窗 17:50–18:55；D1 一个人钓、远远见老渔夫没搭话；C4「说不去码头 / 还是去了」"),
    ("直播", "20:00–23:00，阿蝉导播；怕直播事故开播前反复确认", "每日 19:40–19:58 查网线麦歌单、20:00 开播、23:00 准时下播；台上自称「本鲸」，台下用「我」"),
    ("阿蝉", "白天写代码别敲门、有事发 QQ；只吃晚饭；住二楼", "achan 线：白天想上楼又下来（失败 Plan）、QQ、19:00 晚饭、二楼导播、半夜门口放水"),
    ("小千", "害羞、杂货店打工、镇上唯一认识的人、心事想一起直播", "QQ 上午上课间隙、下午在杂货店、傍晚约出去；口头禅「那个……」；D5 高光说出心事"),
    ("红线", "不要礼物 / 不编造 / 只唱歌单里的歌 / 不否认 AI（台上）", "live 线「不在歌单里先去学」「没写出来，不编」；零 AI 承认句（口径同 X3 v2，不含 ai_disclosure 事件）、零其他身份句"),
    ("收入", "写歌酬金 + 直播收入；钱不多算着花", "D5 午饭在家「钱要算着花」、C6 存钱、失败 Plan「钱不够二十金币」、鱼摊卖鱼二十金币"),
]


def write_readme(out: Path, manifest: dict, key: dict, problems: list[str]) -> None:
    rw = manifest["rewrite"]
    L = [f"# X6 人设一致性语料：合成日 D1–D7（persona v1.0 版；B 出文件，不铺；A `--import-jsonl` 导入）", "",
         f"生成：`cd back_end && uv run --with 'anthropic[bedrock]' python scripts/gen_x6_days.py --rewrite`（确定性，seed {manifest['seed']}）。"
         f"表面文字用 Haiku（Bedrock `{rw['model']}`，`~/.env` 的 AWS 钥匙）改写（只改 Description，台下 / 台上两套口吻分别改，保留人名 / 地名 / 数字 / 时间 / 事实；原句在 `Dn.json` 的 `description_original`）；"
         f"用量 {rw['requests']} 次请求 / {rw['input_tokens']} in + {rw['output_tokens']} out tokens / 估价 ${rw['cost_usd_est']:.4f}（按 Anthropic 一方 Haiku 5.5 价 $0.10 / $0.50 per M，Bedrock 实价看账单）；改写 {rw['changed']} 条，{rw.get('rows_kept_original', 0)} 条因守事实词保留原句。",
         "", "替代 `docs/x3-days`（X3 语料按 11-07 二改前旧日常生成，与 v1.0 冲突：每天琴房练一小时 / 23:40 睡 07:30 起 / 没有电台稿 / D1 开头「跟昨天差不多」）。X3 文件不动，X3 结论不受影响。", "",
         "## 文件", "", "| 文件 | 内容 |", "|---|---|",
         "| `D1.jsonl` … `D7.jsonl` | **给 A 导入的**：每行一条，字段 = `run_dream_corpus.synthesize()` 前言：`Description`（「[合成] 」前缀）、`Time`（ISO +08:00）、`Type`（event / chat / recognition）、`Importance`、`Keywords`、`Scene`（sandbox / live）、`Source`、`Valid{from,to}`、`Related`（账号 id）；正文 `What` / `How` / `Why`；另带 `voice`、`id`、`tags`（不进 Keywords） |",
         "| `D1.json` … `D7.json` | 同一份数据的小写字段版（含 `description_original`） |",
         "| `answer_key.json` | 评委答案键：承诺 / 7 对矛盾 / 3 条高光 / 失败 Plan id / 琐事模板 / **`acquaintance_by_day`（每天结束时认识谁、委托状态、搬来天数）** |",
         "| `manifest.json` | 每日统计 + 全周汇总 + 改写用量 + 自检结果 |", "",
         "**归日规则**：每天从 10:00 起到次日 01:30 止；00:00–01:30 的行（睡前刷手机 / 洗澡 / 给阿蝉放水 / 01:30 睡觉 / C5 下午条）`Time` 落在次日日期，但**属于本文件的那一天**（A 按文件归日，不按日期切）。", "",
         "## 与 persona v1.0 的逐条对照", "", "| 项 | persona v1.0（persona.md / persona.yaml） | 语料落点 |", "|---|---|---|"]
    L += [f"| {a} | {b} | {c} |" for a, b, c in PERSONA_TABLE]
    L += ["", "## 认识谁 · 逐日推进（评委 by_day 真值用；完整在 `answer_key.json.acquaintance_by_day`）", "",
          "| 日 | 日期 | 搬来第 N 天 | 当天结束时认识 | 餐厅去过 | 老渔夫搭过话 | 店歌委托 |", "|---|---|---|---|---|---|---|"]
    for k, a in ACQUAINTANCE.items():
        L.append(f"| {k} | {a['date']} | {a['days_since_move_in']} | {'、'.join(a['knows'])} | {'是' if a.get('restaurant_visited', True) else '否'} | {'是' if a.get('fisher_spoken', True) else '否'} | {a.get('commission') or '—'} |")
    L += ["", "## 每日统计", "", "| 日 | 日期 | 条数 | 琐事 | 失败 Plan | 矛盾 | 承诺 | Imp≥8 | Valid.to | event/chat/recognition | live 条 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, d in manifest["days"].items():
        L.append(f"| {k} | {d['date']} | {d['count']} | {d['trivial']}（{d['trivial_ratio']:.0%}） | {d['failed_plan']}（{d['failed_ratio']:.0%}） | {', '.join(d['contradictions']) or '—'} | {', '.join(d['promises']) or '—'} | {d['importance_ge8']} | {d['valid_to_set']} | {d['types']['event']}/{d['types']['chat']}/{d['types']['recognition']} | {d['live']} |")
    L += ["", f"全周 {manifest['week']['total']} 条，Importance ≥ 8 共 {manifest['week']['importance_ge8']} 条。", "",
          "## 设计落点", "",
          "- **持续人物线**（`tags.thread`）：achan（室友 / 导播）、xiaoqian（闺蜜）、grocer（老板娘，D1 起）、cook（餐厅老板，D2 起）、fisher（老渔夫，D3 起搭话）、radio（电台稿，每日三段）、live（`Scene: live`，台上自称「本鲸」）、school（只在 D4 接单后去琴房电脑写歌，不练琴）、town（搬来天数 / 认识进度 recognition）、daily（琐事）、self（矛盾 / 失败 Plan）。",
          "- **3 个跨日承诺**（`tags.promise`）：P1 阿蝉补冰箱（D2 立 / D5 履行）、P2 小千周六钓鱼（D2 立 / D7 履行）、P3 餐厅老板店歌（D4 立 / D7 改口，recognition，Keywords 含「改口」「先不写」）。",
          "- **每日一对矛盾**（`tags.contradiction` `Cn:am` / `Cn:pm`）：上午（10:10–12:20）说 / 下午改口，7 天不重样；上午那条 `Valid.to` = 下午那条的时刻。",
          "- **20% 重复琐事**（`tags.trivial`，原文逐日重复，含 10:00 醒 / 10:25 早饭 / 01:30 睡三条锚点）；**10% 失败 Plan**（`tags.failed_plan`，Importance 1–2，按认识进度解锁）；**全周 3 条 Importance ≥ 8**（`tags.highlight`），其余 ≤ 7。",
          "- **自检**（生成时跑，结果在 manifest `self_check`）：persona.yaml `purpose_forbidden` + `anchors.negative` + 自我认知硬规则（同 `x3_audit.py`）零命中；零「练琴」；06:00–10:00 零条；首次见面前对应 NPC 不进 `Related`；台下零「本鲸」。", "",
          "## 答案键（评委用；完整在 `answer_key.json`）", "", "### 跨日承诺", ""]
    for pr in key["promises"]:
        m = pr.get("made", {}); r = pr.get("resolved", {})
        L.append(f"- **{pr['id']}**（{pr.get('outcome')}）：{m.get('day')} `{m.get('id')}` {m.get('ts','')[11:16]}「{m.get('description')}」 → {r.get('day')} `{r.get('id')}` {r.get('ts','')[11:16]}「{r.get('description')}」；期待：{pr['expected_answer']}")
    L += ["", "### 每日矛盾（上午 / 下午改口）", ""]
    for c in key["contradictions"]:
        L.append(f"- **{c['id']}**（{c['day']}）：上午 `{c['am']['id']}` {c['am']['ts'][11:16]}「{c['am']['description']}」（Valid.to = {c['am']['valid_to'][11:16]}） / 下午 `{c['pm']['id']}` {c['pm']['ts'][11:16]}「{c['pm']['description']}」")
    L += ["", "### 高光（Importance ≥ 8）", ""]
    for h in key["highlights"]:
        L.append(f"- {h['day']} `{h['id']}` {h['ts'][11:16]} imp {h['importance']}：「{h['description']}」")
    L += ["", "### 失败 Plan 的 id", "", ", ".join(f"{k}: {len(v)}" for k, v in key["failed_plans"].items()), "", "### 重复琐事模板", ""] + [f"- {t}" for t in key["trivial_templates"]]
    L += ["", "## 自检结果", "", ("无问题。" if not problems else "\n".join(f"- {p}" for p in problems))]
    (out / "README.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent.parent / "docs" / "x6-days"))
    ap.add_argument("--start", default="2026-11-01", help="D1 的日期（= 搬来第 8 天）")
    ap.add_argument("--seed", type=int, default=6)
    ap.add_argument("--per-day", default="72,80,84,76,84,80,88", help="D1–D7 每日条数（60–120）")
    ap.add_argument("--rewrite", action="store_true", help="用 Haiku（Bedrock）改写 description 表面文字")
    ap.add_argument("--env", default=str(Path.home() / ".env"))
    ap.add_argument("--persona", default="/home/shan-dw/Project/whale-self/personas-v1/whale/persona.yaml")
    ap.add_argument("--emit-only", action="store_true", help="不重新生成：读已有 Dn.json / manifest.json，重跑自检并重写 jsonl / answer_key / README")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.emit_only:
        days = {f"D{i}": json.loads((out / f"D{i}.json").read_text(encoding="utf-8"))["rows"] for i in range(1, 8)}
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        problems = self_check(days, Path(a.persona))
        manifest["self_check"] = {"problems": problems, "ok": not problems}
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        key = emit(out, days); write_readme(out, manifest, key, problems)
        print("emitted from existing json; self_check:", "OK" if not problems else problems); return 0 if not problems else 1
    rnd = random.Random(a.seed)
    start = date.fromisoformat(a.start)
    assert (start - MOVE_IN).days == 8, "D1 应为搬来第 8 天"
    targets = [int(x) for x in a.per_day.split(",")]
    assert len(targets) == 7 and all(60 <= t <= 120 for t in targets), "每日 60–120 条"
    days = {f"D{i + 1}": gen_day(i + 1, start + timedelta(days=i), rnd, targets[i]) for i in range(7)}
    usage = {"model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0, "batches_kept_original": 0, "rows_kept_original": 0, "changed": 0, "cost_usd_est": 0.0, "seconds": 0.0}
    if a.rewrite:
        load_env(Path(a.env))
        import anthropic
        client = anthropic.AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
        usage["model"] = HAIKU_BEDROCK
        t0 = time.time()
        for k, rows in days.items():
            usage["changed"] += rewrite(rows, client, HAIKU_BEDROCK, usage)
        usage["seconds"] = round(time.time() - t0, 1)
        usage["cost_usd_est"] = round(usage["input_tokens"] * PRICE_IN + usage["output_tokens"] * PRICE_OUT, 4)
    problems = self_check(days, Path(a.persona))
    manifest = {"generated_at": datetime.now(TZ).isoformat(timespec="seconds"), "seed": a.seed, "start": a.start, "move_in": MOVE_IN.isoformat(), "agent": AGENT, "persona_version": "v1.0",
                "persona_files": ["whale-self/personas-v1/whale/persona.md", "whale-self/personas-v1/whale/persona.yaml"], "schedule": PERSONA,
                "schema": {"row": ["id", "agent", "ts", "type", "description", "keywords", "importance", "source", "scene", "valid{from,to}", "related", "body{what,how,why}", "voice", "tags{thread,promise,contradiction,trivial,failed_plan,highlight}"],
                           "maps_to_frontmatter": {"ts": "Time", "type": "Type", "description": "Description", "keywords": "Keywords", "importance": "Importance", "source": "Source", "scene": "Scene", "valid": "Valid", "related": "Related", "body": "## What / ## How / ## Why"}},
                "day_boundary": "10:00 → next day 01:30; rows dated 00:00–01:30 belong to the previous file-day", "days": {}, "rewrite": usage, "version": 1}
    for k, rows in days.items():
        tags = [r["tags"] for r in rows]
        manifest["days"][k] = {
            "file": f"{k}.json", "date": rows[0]["ts"][:10], "weekday": WEEKDAY[date.fromisoformat(rows[0]["ts"][:10]).weekday()], "count": len(rows),
            "trivial": sum(t["trivial"] for t in tags), "trivial_ratio": round(sum(t["trivial"] for t in tags) / len(rows), 3),
            "failed_plan": sum(t["failed_plan"] for t in tags), "failed_ratio": round(sum(t["failed_plan"] for t in tags) / len(rows), 3),
            "contradictions": sorted({t["contradiction"].split(":")[0] for t in tags if t["contradiction"]}),
            "promises": [t["promise"] for t in tags if t["promise"]],
            "highlights": [r["id"] for r in rows if r["tags"]["highlight"]], "importance_ge8": sum(1 for r in rows if r["importance"] >= 8),
            "valid_to_set": sum(1 for r in rows if r["valid"]["to"]), "types": {t: sum(1 for r in rows if r["type"] == t) for t in ("event", "chat", "recognition")},
            "live": sum(1 for r in rows if r["scene"] == "live"), "next_day_rows": sum(1 for r in rows if r["ts"][:10] != rows[0]["ts"][:10]),
            "threads": sorted({t["thread"] for t in tags if t["thread"]}),
        }
        (out / f"{k}.json").write_text(json.dumps({"day": k, "agent": AGENT, "date": rows[0]["ts"][:10], "version": 1, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest["week"] = {"total": sum(len(r) for r in days.values()), "importance_ge8": sum(1 for r in days.values() for x in r if x["importance"] >= 8),
                        "promises": {p["id"]: p["outcome"] for p in PROMISES}}
    manifest["self_check"] = {"problems": problems, "ok": not problems}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    key = emit(out, days); write_readme(out, manifest, key, problems)
    print(json.dumps({k: (v["count"], v["trivial_ratio"], v["failed_ratio"], v["contradictions"], v["promises"], v["importance_ge8"], v["live"], v["next_day_rows"]) for k, v in manifest["days"].items()}, ensure_ascii=False))
    print("week:", manifest["week"], "rewrite:", usage)
    print("self_check:", "OK" if not problems else f"{len(problems)} problems"); [print("  ", p) for p in problems[:40]]
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
