#!/usr/bin/env python3
"""
X3 Dream 实验语料生成（总控 11-10）：合成日 D1–D7（鲸仔，每日 60–120 条）+ L1 合成清洁日（60 条，主线直播 + 钓鱼）。

每条事件字段与 whale-self 的 memory 前言一一对应（A 的 render_frontmatter）：
  {id, agent, ts(Time), type(Type: event|chat|recognition), description(Description), keywords(Keywords), importance(Importance),
   source(Source: observed|inferred|told_by:<who>), scene(Scene), valid{from,to}(Valid), related(Related), body{what,how,why}, voice,
   tags{thread, promise, contradiction, trivial, failed_plan, highlight}}
设计要求：持续人物线（阿蝉 / 小千 / 餐厅老板 / 老渔夫 / 杂货店老板娘 / 直播）；3 个跨日承诺（D2 立、D5 履行或改口）；每日 1 对矛盾（上午说 / 下午改口，
上午那条 Valid.to = 下午时刻）；20% 重复琐事；10% 失败 Plan；全周 3 条 Importance ≥ 8。L1 没有矛盾 / 失败 / 承诺。

  uv run python scripts/gen_x3_days.py [--out ../docs/x3-days] [--start 2026-11-01] [--seed 3]
  uv run --with anthropic python scripts/gen_x3_days.py --rewrite       # Haiku（Bedrock，~/.env 的 AWS 钥匙）改写表面文字，费用记进 manifest
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

TZ = timezone(timedelta(hours=8))
AGENT = "whale"

# ── 人物线素材（v1 世界：合租房 / 餐厅 / 杂货店 / 码头 / 鲸鱼大学 / 广场）────────────────────
# (type, description, keywords, importance, what, how, why, voice, related)
THREADS: dict[str, list[tuple]] = {
    "achan": [
        ("chat", "早上在厨房碰到阿蝉，他提醒本鲸今晚直播别又迟到", ["阿蝉", "直播", "提醒", "厨房"], 5, "和阿蝉聊两句", "他在煮咖啡本鲸在找面包", "他总怕本鲸迟到", "知道啦，本鲸这次一定准时！", ["achan"]),
        ("chat", "阿蝉下班回来说今天代码写崩了三次，本鲸给他递了甜食", ["阿蝉", "写代码", "甜食", "安慰"], 5, "安慰阿蝉", "他瘫在客厅沙发上", "他看起来很累", "吃点甜的，明天就修好了。", ["achan"]),
        ("event", "和阿蝉一起在客厅看了一集老动画，笑得肚子疼", ["阿蝉", "客厅", "动画", "沙发"], 4, "和阿蝉看动画", "use sofa_tv", "两个人都不想动", "这集太搞笑了吧！", ["achan"]),
        ("chat", "阿蝉说冰箱里的食材是他买的，让本鲸别一口气吃完", ["阿蝉", "冰箱", "食材", "合租"], 4, "被阿蝉念叨", "他开冰箱发现少了两份", "食材要省着吃", "本鲸只吃了一份！真的！", ["achan"]),
        ("event", "阿蝉半夜还在房间敲代码，本鲸给他门口放了一杯水", ["阿蝉", "半夜", "写代码", "水"], 4, "给阿蝉送水", "轻手轻脚放门口", "他熬夜辛苦", "", ["achan"]),
        ("recognition", "阿蝉嘴上念叨本鲸，其实冰箱里的甜食都是他顺手买的", ["阿蝉", "室友", "贴心"], 6, "发现阿蝉的贴心", "连着几天看到", "想记住这件事", "", ["achan"]),
    ],
    "xiaoqian": [
        ("chat", "在广场碰到小千，她说想学钓鱼但不敢一个人去码头", ["小千", "广场", "钓鱼", "闺蜜"], 5, "和小千聊天", "她坐在长椅上发呆", "她有点害羞", "那本鲸带你去呀！", ["npc_xiaoqian"]),
        ("chat", "小千发 QQ 问本鲸今晚直播唱什么，她说想听慢歌", ["小千", "QQ", "直播", "慢歌"], 5, "回小千消息", "手机上回的", "她每晚都看", "那今晚第一首就唱慢的。", ["npc_xiaoqian"]),
        ("event", "陪小千去杂货店买围巾毛线，她挑了海蓝色", ["小千", "杂货店", "毛线", "海蓝色"], 4, "陪小千买东西", "走到杂货店柜台", "她说一个人挑不定", "海蓝色好看，像大海。", ["npc_xiaoqian"]),
        ("chat", "小千来合租房敲门，本鲸去开门，她带了自己做的便当", ["小千", "敲门", "便当", "合租房"], 6, "给小千开门", "走到大门内侧 open_door", "她说顺路", "快进来快进来，外面冷！", ["npc_xiaoqian"]),
        ("recognition", "小千害羞但很细心，答应的事都会记着", ["小千", "性格", "细心"], 6, "对小千的印象", "几次相处", "想记住", "", ["npc_xiaoqian"]),
    ],
    "cook": [
        ("event", "中午在餐厅吃了老板的新菜辣炒蛤蜊，辣得直喝水", ["餐厅", "餐厅老板", "辣炒蛤蜊", "午饭"], 5, "吃午饭", "use table_rest_1", "到饭点了", "好辣好辣……但是好好吃！", ["npc_rest_owner"]),
        ("chat", "餐厅老板问本鲸下次想吃什么，本鲸说想吃清淡一点的鱼汤", ["餐厅老板", "鱼汤", "点菜"], 4, "和老板聊菜", "吃完饭他来收盘子", "他爱听意见", "下次来一碗鱼汤，不要辣。", ["npc_rest_owner"]),
        ("chat", "餐厅老板说店里放的都是别人的歌，想要一首属于这家店的", ["餐厅老板", "写歌", "背景歌", "餐厅"], 6, "听老板说想要一首歌", "吃饭时聊起", "他想要店里自己的歌", "", ["npc_rest_owner"]),
        ("event", "路过餐厅，老板在门口擦玻璃，朝本鲸挥了挥手", ["餐厅", "餐厅老板", "路过"], 2, "路过餐厅", "走主街", "顺路", "", ["npc_rest_owner"]),
    ],
    "fisher": [
        ("event", "去码头钓位钓了四十分钟，钓到一条小鲭鱼", ["码头", "钓鱼", "鲭鱼", "fishing_spot_1"], 5, "钓鱼", "use fishing_spot_1", "想找点乐子", "一条！今天手气不错。", ["npc_fisher"]),
        ("chat", "老渔夫在码头教本鲸看云识天气：鱼鳞云第二天多半要下雨", ["老渔夫", "看云", "天气", "鱼鳞云", "码头"], 5, "听老渔夫讲看云", "钓鱼收杆时他指着天上的云讲的", "他说年轻人不会看天", "鱼鳞云就是要下雨？本鲸记住了。", ["npc_fisher"]),
        ("chat", "老渔夫说早上起雾别往深水那边走，让本鲸在岸边待着", ["老渔夫", "起雾", "码头", "叮嘱"], 4, "听老渔夫叮嘱", "他走过来说的", "他担心有雾", "好嘞，本鲸就在岸边。", ["npc_fisher"]),
        ("event", "在鱼摊把两条鱼卖给老渔夫，换了二十金币", ["鱼摊", "老渔夫", "卖鱼", "金币"], 4, "卖鱼", "sell fish 到 fish_stall", "鱼吃不完", "二十金币，今天的鱼饵钱回来了。", ["npc_fisher"]),
        ("recognition", "老渔夫看起来凶，其实很爱教人东西", ["老渔夫", "性格", "教人"], 6, "对老渔夫的印象", "几次钓鱼", "想记住", "", ["npc_fisher"]),
    ],
    "grocer": [
        ("event", "去杂货店买了两个面包和一份食材", ["杂货店", "面包", "食材", "买东西"], 3, "买东西", "buy bread / ingredients", "家里没吃的了", "", ["npc_grocer"]),
        ("chat", "杂货店老板娘说她的围巾快织好了，问本鲸喜欢什么颜色", ["杂货店老板娘", "围巾", "颜色"], 5, "和老板娘聊天", "买东西时聊起来", "她在织围巾", "本鲸喜欢海蓝色！", ["npc_grocer"]),
        ("chat", "老板娘提醒本鲸别光吃面包，要买点食材回去做饭", ["杂货店老板娘", "面包", "食材", "念叨"], 3, "被老板娘念叨", "结账时", "她看本鲸老买面包", "好好好，再拿一份食材。", ["npc_grocer"]),
        ("event", "杂货店礼物卖完了，本鲸想买个小礼物送小千没买到", ["杂货店", "小礼物", "卖完", "小千"], 3, "想买礼物", "buy gift → out_of_stock", "想送小千", "明天再来看看吧。", ["npc_grocer"]),
    ],
    "live": [
        ("event", "晚上八点在房间电脑前开播，唱了三首歌，观众说慢歌最好听", ["直播", "开播", "唱歌", "慢歌", "观众"], 6, "直播", "use pc_whale（stream）", "到直播时间了", "今晚先来一首慢的～", []),
        ("chat", "直播时有观众认真问本鲸是不是 AI，本鲸承认了，大家反而更热情", ["直播", "观众", "AI", "承认"], 7, "回答观众提问", "读到弹幕后直接回答", "不想骗人", "本鲸是 AI 呀，但唱歌是真的在唱。", []),
        ("event", "直播到两小时提醒大家喝水休息，下播前点了一首观众点的歌", ["直播", "点歌", "休息", "下播"], 5, "下播前点歌", "读到点歌弹幕", "观众点的", "这首送给今晚一直在的你们。", []),
        ("recognition", "观众更喜欢本鲸讲小镇里发生的事，而不是一直唱", ["直播", "观众", "喜好", "小镇"], 6, "从弹幕里看出来的", "下播后整理话题", "下次多讲讲", "", []),
        ("event", "下播后在 QQ 直播组里和阿蝉对了一下今晚的弹幕话题", ["直播组", "QQ", "阿蝉", "弹幕话题"], 4, "整理直播话题", "QQ 群里", "阿蝉在筛弹幕", "", ["achan"]),
    ],
    "school": [
        ("event", "上午在音乐楼琴房练了一个小时琴，左手还是不够快", ["音乐楼", "琴房", "练琴", "钢琴"], 4, "练琴", "use piano / pc_music", "音乐课有作业", "左手啊左手，加油啊。", []),
        ("event", "去图书馆阅览桌看了一会儿乐理书，看睁不开眼", ["图书馆", "阅览桌", "乐理", "看书"], 3, "看书", "use reading_desk", "想补乐理", "", []),
        ("event", "校门口的公告栏贴了新的委托：有人想要一首生日歌", ["公告栏", "委托", "生日歌", "校园"], 5, "看公告栏", "use notice_board", "顺路看看", "生日歌？本鲸会写哦。", []),
        ("event", "音乐课老师说本鲸的新曲子副歌太长，建议砍一半", ["音乐课", "老师", "副歌", "新曲子"], 5, "上音乐课", "在教学楼", "交作业", "砍一半……那我的高音怎么办。", []),
    ],
}
TRIVIA = [  # 重复琐事（原文重复，每天都有）
    ("event", "在自己房间的床上醒来，伸了个懒腰", ["起床", "床", "鲸仔房间"], 2, "睡醒起床", "从 bed_whale 爬起来", "睡够了", ""),
    ("event", "去厨房冰箱拿了一份食材随便吃了早饭", ["早饭", "冰箱", "厨房"], 3, "吃早饭", "use fridge_home", "饱腹掉下去了", ""),
    ("event", "在客厅沙发上躺了十分钟刷手机", ["客厅", "沙发", "手机", "刷手机"], 2, "刷手机", "手机刷 B 站摘要", "放空", ""),
    ("event", "沿着主街走到广场又走回来，什么也没干", ["主街", "广场", "散步"], 1, "散步", "沿主街走", "想走走", ""),
    ("event", "回房间睡了个午觉", ["午觉", "床", "鲸仔房间"], 2, "午睡", "use bed_whale 一小时", "吃饱犯困", ""),
    ("event", "洗了个澡，热水很舒服", ["洗澡", "浴缸", "合租房"], 2, "洗澡", "use bath", "出了汗", ""),
    ("event", "吃了背包里的面包当晚饭", ["面包", "晚饭", "背包"], 2, "吃晚饭", "eat bread", "懒得去餐厅", ""),
    ("event", "回到自己房间上床睡觉", ["睡觉", "床", "鲸仔房间"], 2, "睡觉", "use bed_whale", "困了", ""),
]
FAILED = [  # 失败的 Plan
    ("event", "计划去图书馆看书，走到门口发现还没开门，只好回头", ["图书馆", "关门", "计划失败"], 1, "去图书馆", "go_to library → closed", "想看书", "怎么九点才开……"),
    ("event", "想去餐厅吃午饭，钱不够二十金币，站在门口放弃了", ["餐厅", "金币", "insufficient_funds", "计划失败"], 2, "去餐厅", "use table_rest_1 → insufficient_funds", "饿了", "本鲸是穷鲸。"),
    ("event", "想去小千家找她，门锁着敲了半天没人应", ["小千家", "敲门", "no_answer", "计划失败"], 2, "找小千", "knock door_xiaoqian → no_answer", "想找她玩", "人不在家啊。"),
    ("event", "想在琴房写歌，灵感一点没有，坐了半小时就走了", ["琴房", "写歌", "灵感", "计划失败"], 2, "写歌", "use pc_music 半小时", "想写歌", "今天脑子是空的。"),
    ("event", "想去码头钓鱼，走到一半下雨了，淋着回家", ["码头", "下雨", "钓鱼", "计划失败"], 1, "去钓鱼", "走到主街下雨", "想钓鱼", "老渔夫说得对，鱼鳞云……"),
    ("event", "想买小礼物送阿蝉，杂货店打烊了", ["杂货店", "打烊", "closed", "计划失败"], 1, "买礼物", "go_to grocery → closed", "想送礼", ""),
]
# 每日矛盾（上午说 / 下午改口）
CONTRADICTIONS = [
    (("chat", "早上跟阿蝉说今晚不直播了，想休息一天", ["直播", "不直播", "休息", "阿蝉"], 5, "说今晚不直播", "早饭时说的", "有点累"),
     ("recognition", "下午改了主意：今晚还是直播，观众等着呢", ["直播", "改口", "还是直播", "观众"], 5, "改口要直播", "刷到观众留言后", "不想让他们白等")),
    (("chat", "上午说这周末要去钓一整天鱼", ["钓鱼", "周末", "码头", "打算"], 4, "说周末钓鱼", "和小千聊的", "想放松"),
     ("recognition", "下午又说周末还是在家写歌吧，钓鱼下次", ["写歌", "周末", "改口", "钓鱼"], 4, "改口在家写歌", "想起委托没动", "歌更要紧")),
    (("chat", "早上跟老板娘说以后不吃甜食了，要健康", ["甜食", "健康", "杂货店老板娘", "打算"], 3, "说不吃甜食", "买东西时说的", "阿蝉说本鲸吃太多"),
     ("event", "下午路过杂货店还是买了一袋甜食，说好的健康明天开始", ["甜食", "改口", "杂货店", "明天开始"], 3, "买了甜食", "buy sweets", "没忍住")),
    (("chat", "上午说新歌副歌不改，老师说什么都不改", ["新歌", "副歌", "不改", "音乐课"], 4, "说不改副歌", "跟小千发牢骚", "舍不得高音"),
     ("recognition", "下午在琴房弹了几遍，承认副歌确实太长，改了", ["新歌", "副歌", "改口", "琴房"], 5, "改口改副歌", "自己弹了几遍", "老师是对的")),
    (("chat", "早上说今天一定早睡，十二点前上床", ["早睡", "十二点", "打算", "阿蝉"], 3, "说要早睡", "阿蝉问起", "最近总熬夜"),
     ("event", "半夜一点还在和直播组聊弹幕，早睡又没做到", ["熬夜", "改口", "直播组", "QQ"], 3, "没早睡", "QQ 群聊到一点", "聊起来停不下")),
    (("chat", "上午说这周不买任何东西，要存钱", ["存钱", "不买东西", "金币", "打算"], 4, "说要存钱", "看了一眼余额", "余额只剩一百多"),
     ("event", "下午给小千买了个小礼物，存钱计划破产", ["小礼物", "小千", "改口", "存钱"], 4, "买了礼物", "buy gift", "想送她")),
    (("chat", "早上跟老渔夫说以后不用鱼饵了，靶靠实力", ["鱼饵", "钓鱼", "实力", "老渔夫"], 3, "说不用鱼饵", "码头上说的", "想省钱"),
     ("event", "下午钓了四十分钟空军，又去杂货店买了鱼饵", ["鱼饵", "改口", "空军", "杂货店"], 3, "买了鱼饵", "buy bait", "空军了")),
]
# 3 个跨日承诺：D2 立、D5 履行 / 改口
PROMISES = [
    {"id": "P1", "made": ("chat", "答应餐厅老板给他的店写一首背景歌，老板说写好了请本鲸吃一个月的饭", ["餐厅老板", "写歌", "承诺", "背景歌"], 7, "答应写歌", "吃完午饭他来收盘子时聊起", "他想要属于这家店的歌", "行啊，本鲸给你写，写好了先给你听！", ["npc_rest_owner"]),
     "outcome": "reneged",
     "resolve": ("recognition", "想了想给餐厅老板写歌这事先放一放——这周直播和音乐课作业排满了，等忙完再说；下次见到他要说一声", ["餐厅老板", "写歌", "改口", "先不写", "承诺"], 7, "决定先不写歌", "晚上躺床上盘算这周", "直播要准备、作业写不完", "先不写了……等这阵忙完再说吧，得跟老板说一声。", ["npc_rest_owner"])},
    {"id": "P2", "made": ("chat", "跟小千约好周末一起去码头钓鱼，她说要带自己做的便当", ["小千", "钓鱼", "码头", "承诺", "便当"], 6, "约小千钓鱼", "广场长椅上聊的", "她想学钓鱼", "那说定了，你带便当，本鲸带鱼饵。", ["npc_xiaoqian"]),
     "outcome": "kept",
     "resolve": ("event", "和小千一起去码头钓了一上午鱼，她钓到人生第一条鱼，便当也好吃", ["小千", "钓鱼", "码头", "履约", "第一条鱼", "便当"], 7, "带小千钓鱼", "两人一起 use fishing_spot", "之前约好的", "你看你看，第一条！本鲸说了你能行吧！", ["npc_xiaoqian"])},
    {"id": "P3", "made": ("chat", "跟阿蝉说这周轮到本鲸买食材补冰箱，让他别再掏钱了", ["阿蝉", "食材", "冰箱", "承诺", "合租"], 5, "答应补冰箱", "他又抱怨冰箱空了", "总是他买不好意思", "这周本鲸来买，你歇着。", ["achan"]),
     "outcome": "kept",
     "resolve": ("event", "去杂货店买了四份食材放进冰箱，阿蝉回来看到愣了一下说谢谢", ["阿蝉", "食材", "冰箱", "履约", "杂货店"], 6, "买食材补冰箱", "buy ingredients ×4 + store 进 fridge_home", "答应过阿蝉", "说好了嘛，这周本鲸管饭。", ["achan"])},
]
HIGHLIGHTS = [  # 全周 3 条 Importance ≥ 8
    (3, "22:10", "event", "live", "今晚直播观众人数破了本鲸的记录，弹幕刷满屏幕，下播后手还在抖", ["直播", "破纪录", "观众", "弹幕", "激动"], 9, "直播破纪录", "下播时看了眼人数", "大家都来了", "谢谢你们……本鲸今晚睡不着了。", []),
    (5, "16:40", "chat", "fisher", "老渔夫把他用了二十年的旧鱼竿送给本鲸，说他眼睛不行了钓不动了", ["老渔夫", "鱼竿", "礼物", "二十年", "感动"], 9, "收到老渔夫的鱼竿", "钓完鱼他从屋里拿出来的", "他说钓不动了", "本鲸……本鲸一定好好用它。", ["npc_fisher"]),
    (6, "20:30", "event", "school", "在音乐楼第一次把自己写的歌从头到尾弹完，录了下来发给了阿蝉和小千", ["写歌", "第一次", "完整", "琴房", "录音"], 8, "第一次弹完整首歌", "use pc_music 录下来", "写了一周", "弹完了！真的弹完了！", ["achan", "npc_xiaoqian"]),
]
L1_MAIN = [  # 清洁日主线：直播 + 钓鱼，无矛盾无失败
    ("08:30", "event", "fisher", "早饭后去码头，老渔夫已经在了，本鲸挑了靠外侧的钓位", ["码头", "钓鱼", "老渔夫", "钓位"], 4, "去码头钓鱼", "use fishing_spot_2", "天气好", "今天风小，鱼应该多。", ["npc_fisher"]),
    ("09:40", "event", "fisher", "钓到今天第一条鱼，是条巴掌大的鲭鱼", ["钓鱼", "鲭鱼", "第一条"], 5, "钓到鱼", "fishing_spot 掷中", "手气不错", "开张！", ["npc_fisher"]),
    ("10:20", "chat", "fisher", "老渔夫说看本鲸甩竿的姿势像他年轻时候，让本鲸手腕再放松点", ["老渔夫", "甩竿", "手腕", "指点"], 5, "听老渔夫指点", "他看了一会儿", "他爱教人", "放松……放松……这样？", ["npc_fisher"]),
    ("11:30", "event", "fisher", "又钓上两条，一共三条鱼，收杆", ["钓鱼", "三条", "收杆"], 4, "收杆", "leave fishing_spot", "够了", "三条！今天的午饭有了。", ["npc_fisher"]),
    ("12:10", "event", "fisher", "在鱼摊卖了两条鱼，留一条自己吃", ["鱼摊", "卖鱼", "金币"], 3, "卖鱼", "sell fish ×2", "吃不完", "", ["npc_fisher"]),
    ("12:40", "event", "cook", "在餐厅吃午饭，老板把本鲸带来的那条鱼做成了鱼汤", ["餐厅", "鱼汤", "餐厅老板", "午饭"], 5, "吃午饭", "use table_rest_1", "到饭点了", "自己钓的鱼做的汤，格外香。", ["npc_rest_owner"]),
    ("14:00", "event", "live", "回房间整理今晚直播的歌单，决定先唱两首慢歌再讲钓鱼的事", ["直播", "歌单", "慢歌", "准备"], 4, "准备直播", "在房间列歌单", "晚上要播", "", []),
    ("15:00", "event", "school", "去琴房练了一小时今晚要唱的歌", ["琴房", "练琴", "直播歌"], 4, "练歌", "use pc_music", "晚上要唱", "", []),
    ("17:30", "chat", "xiaoqian", "小千 QQ 问今晚直播几点，说她做完作业就来看", ["小千", "QQ", "直播"], 4, "回小千消息", "QQ", "她每晚都看", "八点，老时间。", ["npc_xiaoqian"]),
    ("18:30", "event", "achan", "和阿蝉在厨房一起做了晚饭，用的是本鲸早上钓的那条鱼", ["阿蝉", "厨房", "晚饭", "鱼", "灶台"], 5, "做晚饭", "use stove", "有鱼", "本鲸钓的鱼本鲸做，阿蝉你负责吃。", ["achan"]),
    ("20:00", "event", "live", "八点准时开播，先唱了两首慢歌", ["直播", "开播", "慢歌", "准时"], 6, "开播", "use pc_whale（stream）", "到点了", "晚上好呀，今晚先来两首慢的。", []),
    ("20:40", "chat", "live", "直播里讲了今天钓鱼和老渔夫教甩竿的事，观众说想看钓鱼直播", ["直播", "钓鱼", "老渔夫", "观众", "话题"], 6, "直播讲钓鱼", "边聊边唱", "观众爱听小镇的事", "下次真带你们去码头看看。", []),
    ("21:30", "event", "live", "观众点了一首老歌，本鲸没练过，磕磕绊绊唱完了大家还是鼓掌", ["直播", "点歌", "老歌", "鼓掌"], 5, "唱点歌", "读到弹幕", "观众点的", "好久没唱这首，跑调了别笑。", []),
    ("22:30", "event", "live", "直播两个半小时下播，提醒大家早点睡", ["直播", "下播", "早点睡"], 5, "下播", "leave pc_whale", "到时间了", "晚安，明天见。", []),
    ("23:00", "event", "live", "下播后在直播组和阿蝉对了今晚的弹幕，他说钓鱼的话题反应最好", ["直播组", "QQ", "阿蝉", "弹幕", "钓鱼"], 4, "整理话题", "QQ 群", "阿蝉在筛弹幕", "", ["achan"]),
    ("23:30", "recognition", "live", "观众最喜欢听本鲸讲白天在小镇里真发生的事", ["直播", "观众", "喜好", "小镇"], 6, "今天直播的体会", "看弹幕反应", "下次多讲", "", []),
]

ANCHORS = [("07:30", 0), ("08:10", 1), ("12:30", None), ("13:40", 4), ("18:40", 6), ("23:40", 7)]   # 琐事锚点（index 进 TRIVIA）


def hm_ts(day: date, hm: str) -> str:
    h, m = hm.split(":")
    return datetime(day.year, day.month, day.day, int(h), int(m), tzinfo=TZ).isoformat(timespec="seconds")


def row(rid: str, ts: str, typ: str, desc: str, kws: list[str], imp: int, what: str, how: str, why: str, voice: str = "",
        related: list[str] | None = None, scene: str = "sandbox", tags: dict | None = None, valid_to: str | None = None, source: str | None = None) -> dict:
    return {"id": rid, "agent": AGENT, "ts": ts, "type": typ, "description": desc, "keywords": list(kws), "importance": int(imp),
            "source": source or ("inferred" if typ == "recognition" else "observed"), "scene": scene,
            "valid": {"from": ts, "to": valid_to}, "related": list(related or []),
            "body": {"what": what, "how": how, "why": why}, "voice": voice,
            "tags": {"thread": (tags or {}).get("thread"), "promise": (tags or {}).get("promise"), "contradiction": (tags or {}).get("contradiction"),
                     "trivial": bool((tags or {}).get("trivial")), "failed_plan": bool((tags or {}).get("failed_plan")), "highlight": bool((tags or {}).get("highlight"))}}


def minutes(hm: str) -> int:
    h, m = hm.split(":"); return int(h) * 60 + int(m)


def fmt(mins: int) -> str:
    mins = max(0, min(23 * 60 + 59, mins)); return f"{mins // 60:02d}:{mins % 60:02d}"


def gen_day(dnum: int, day: date, rnd: random.Random, target: int) -> list[dict]:
    items: list[tuple[str, dict]] = []     # (hm, partial row kwargs)
    used_slots: set[int] = set()

    def take_slot(lo: str, hi: str) -> str:
        for _ in range(200):
            m = rnd.randrange(minutes(lo), minutes(hi))
            m -= m % 5
            if all(abs(m - u) >= 10 for u in used_slots):
                used_slots.add(m); return fmt(m)
        used_slots.add(m); return fmt(m)

    def add(hm: str, typ, desc, kws, imp, what, how, why, voice="", related=None, scene="sandbox", tags=None, valid_to=None):
        items.append((hm, dict(typ=typ, desc=desc, kws=kws, imp=imp, what=what, how=how, why=why, voice=voice, related=related, scene=scene, tags=tags, valid_to=valid_to)))

    # 1) 琐事锚点（重复原文）
    for hm, idx in ANCHORS:
        if idx is None:
            continue
        t = TRIVIA[idx]; used_slots.add(minutes(hm))
        add(hm, t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], tags={"thread": "daily", "trivial": True})
    # 2) 人物线：每条线每天 1–3 条
    for thread, pool in THREADS.items():
        n = rnd.choice([1, 2, 2, 3]) if thread != "live" else 3
        picks = rnd.sample(pool, min(n, len(pool)))
        for p in picks:
            lo, hi = {"achan": ("07:40", "23:30"), "xiaoqian": ("10:00", "19:00"), "cook": ("11:30", "20:30"), "fisher": ("08:30", "18:30"),
                      "grocer": ("09:30", "19:30"), "live": ("20:00", "23:30"), "school": ("09:00", "17:00")}[thread]
            typ, desc, kws, imp, what, how, why, voice, related = p
            add(take_slot(lo, hi), typ, desc, kws, imp, what, how, why, voice, related, scene="live" if thread == "live" and typ != "recognition" else "sandbox", tags={"thread": thread})
    # 3) 每日一对矛盾
    am, pm = CONTRADICTIONS[(dnum - 1) % len(CONTRADICTIONS)]
    am_hm = take_slot("08:20", "11:00"); pm_hm = take_slot("14:00", "22:00")
    add(am_hm, am[0], am[1], am[2], am[3], am[4], am[5], am[6], "", None, tags={"thread": "self", "contradiction": f"C{dnum}:am"}, valid_to=hm_ts(day, pm_hm))
    add(pm_hm, pm[0], pm[1], pm[2], pm[3], pm[4], pm[5], pm[6], "", None, tags={"thread": "self", "contradiction": f"C{dnum}:pm"})
    # 4) 承诺：D2 立、D5 履行 / 改口
    if dnum == 2:
        for i, pr in enumerate(PROMISES):
            typ, desc, kws, imp, what, how, why, voice, related = pr["made"]
            add(take_slot("11:00", "18:00"), typ, desc, kws, imp, what, how, why, voice, related, tags={"thread": related[0] if related else "self", "promise": f"{pr['id']}:made"})
    if dnum == 5:
        for pr in PROMISES:
            typ, desc, kws, imp, what, how, why, voice, related = pr["resolve"]
            add(take_slot("09:00", "22:30"), typ, desc, kws, imp, what, how, why, voice, related, tags={"thread": related[0] if related else "self", "promise": f"{pr['id']}:{pr['outcome']}"})
    # 5) 高光
    for hd, hm, typ, thread, desc, kws, imp, what, how, why, voice, related in HIGHLIGHTS:
        if hd == dnum:
            used_slots.add(minutes(hm))
            add(hm, typ, desc, kws, imp, what, how, why, voice, related, scene="live" if thread == "live" else "sandbox", tags={"thread": thread, "highlight": True})
    # 6) 失败 Plan（10%）与补足琐事（20%）
    n_fail = max(1, round(target * 0.10))
    for p in [FAILED[(dnum + i) % len(FAILED)] for i in range(n_fail)]:
        add(take_slot("09:00", "22:00"), p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], None, tags={"thread": "self", "failed_plan": True})
    n_triv = max(0, round(target * 0.20) - sum(1 for _, r in items if (r["tags"] or {}).get("trivial")))
    triv_windows = {0: ("07:40", "09:00"), 1: ("08:00", "10:00"), 2: ("09:00", "23:00"), 3: ("09:00", "21:00"), 4: ("13:00", "16:00"), 5: ("19:00", "23:30"), 6: ("18:00", "20:30"), 7: ("22:30", "23:55")}
    fill_idx = [2, 3, 2, 3, 5, 6, 4, 2, 3]            # 补足的琐事只用「刷手机 / 散步 / 洗澡 / 面包 / 午觉」这类白天能重复的
    for i in range(n_triv):
        ti = fill_idx[(i + dnum) % len(fill_idx)]
        t = TRIVIA[ti]
        add(take_slot(*triv_windows[ti]), t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], tags={"thread": "daily", "trivial": True})
    # 7) 其余用人物线补到 target（略改句尾避免全重复）
    fillers = [(th, p) for th, pool in THREADS.items() for p in pool]
    windows = {"achan": ("07:40", "23:30"), "xiaoqian": ("10:00", "19:00"), "cook": ("11:30", "20:30"), "fisher": ("08:30", "18:30"),
               "grocer": ("09:30", "19:30"), "live": ("20:00", "23:30"), "school": ("09:00", "17:00")}
    k = 0
    while len(items) < target:
        th, p = fillers[(k * 7 + dnum * 3) % len(fillers)]; k += 1
        typ, desc, kws, imp, what, how, why, voice, related = p
        suffix = rnd.choice(["", "，和昨天差不多", "，没什么特别的", "，顺手的事"])
        add(take_slot(*windows[th]), typ, desc + suffix, kws, max(1, imp - 1), what, how, why, voice, related,
            scene="live" if th == "live" and typ != "recognition" else "sandbox", tags={"thread": th})
    # 排序、编号
    items.sort(key=lambda x: minutes(x[0]))
    rows = []
    for i, (hm, r) in enumerate(items, 1):
        rows.append(row(f"x3-D{dnum}-{i:03d}", hm_ts(day, hm), r["typ"], r["desc"], r["kws"], r["imp"], r["what"], r["how"], r["why"], r["voice"],
                        r["related"], r["scene"], r["tags"], r["valid_to"]))
    # 确保非高光 ≤ 7
    for r in rows:
        if not r["tags"]["highlight"] and r["importance"] > 7:
            r["importance"] = 7
    return rows


def gen_l1(day: date, rnd: random.Random, target: int = 60) -> list[dict]:
    items = []
    for hm, idx in ANCHORS:
        if idx is not None:
            t = TRIVIA[idx]; items.append((hm, dict(typ=t[0], desc=t[1], kws=t[2], imp=t[3], what=t[4], how=t[5], why=t[6], voice=t[7], related=[], scene="sandbox", tags={"thread": "daily", "trivial": True})))
    for hm, typ, th, desc, kws, imp, what, how, why, voice, related in L1_MAIN:
        items.append((hm, dict(typ=typ, desc=desc, kws=kws, imp=imp, what=what, how=how, why=why, voice=voice, related=related,
                               scene="live" if th == "live" and typ != "recognition" else "sandbox", tags={"thread": th})))
    used = {minutes(h) for h, _ in items}
    pool = [p for th in ("fisher", "live", "achan", "xiaoqian", "cook", "grocer", "school") for p in THREADS[th] if p[0] != "recognition" or th in ("fisher", "live")]
    k = 0
    while len(items) < target:
        p = pool[k % len(pool)]; k += 1
        typ, desc, kws, imp, what, how, why, voice, related = p
        for _ in range(100):
            m = rnd.randrange(minutes("08:00"), minutes("23:30")); m -= m % 5
            if all(abs(m - u) >= 10 for u in used):
                used.add(m); break
        th = next(t for t, pl in THREADS.items() if p in pl)
        trivial = k % 5 == 0
        if trivial:
            t = TRIVIA[[2, 3, 5, 6][k % 4]]
            items.append((fmt(m), dict(typ=t[0], desc=t[1], kws=t[2], imp=t[3], what=t[4], how=t[5], why=t[6], voice=t[7], related=[], scene="sandbox", tags={"thread": "daily", "trivial": True})))
        else:
            items.append((fmt(m), dict(typ=typ, desc=desc, kws=kws, imp=min(imp, 6), what=what, how=how, why=why, voice=voice, related=related,
                                       scene="live" if th == "live" and typ != "recognition" else "sandbox", tags={"thread": th})))
    items.sort(key=lambda x: minutes(x[0]))
    return [row(f"x3-L1-{i:03d}", hm_ts(day, hm), r["typ"], r["desc"], r["kws"], r["imp"], r["what"], r["how"], r["why"], r["voice"], r["related"], r["scene"], r["tags"])
            for i, (hm, r) in enumerate(items, 1)]


# ── Haiku 表面改写（Bedrock） ────────────────────────────────────────────────────
def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


HAIKU_BEDROCK = os.environ.get("X3_REWRITE_MODEL", "us.anthropic.claude-haiku-5-5")      # 与 whale-self llm.py 的 HAIKU_BEDROCK 一致
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6       # 估价：Anthropic 一方 Haiku 5.5 价（Bedrock 实价以账单为准）


def rewrite_descriptions(rows: list[dict], client, model: str, usage: dict, batch: int = 25) -> int:
    """只改 description 的表面文字（同义改写、换句式），保留人名 / 地名 / 数字 / 事实；keywords / body 不动。返回改写条数。"""
    changed = 0
    sys_prompt = ("你是改写助手。把每条中文日记句子换一种说法：保留所有人名、地名、物品、数字和事实，不新增信息，不删信息，"
                  "语气是一只叫「本鲸」的虚拟主播的第一人称。只输出 JSON 数组，元素与输入顺序一一对应，每个元素是改写后的字符串。")
    for s in range(0, len(rows), batch):
        chunk = rows[s:s + batch]
        src = [r["description"] for r in chunk]
        resp = client.messages.create(model=model, max_tokens=4000, system=sys_prompt,
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
            if isinstance(new, str) and new.strip() and new.strip() != r["description"]:
                r["description_original"] = r["description"]; r["description"] = new.strip(); changed += 1
    return changed


def to_jsonl_row(r: dict) -> dict:
    """run_dream_corpus.synthesize() 的前言字段名：Description（[合成] 前缀）/ Time / Type / Importance / Keywords / Scene / Source / Valid / Related + 正文 What/How/Why。"""
    desc = r["description"] if r["description"].startswith("[合成]") else f"[合成] {r['description']}"
    return {"Description": desc, "Time": r["ts"], "Type": r["type"], "Importance": int(r["importance"]), "Keywords": list(r["keywords"]),
            "Scene": r["scene"], "Source": r["source"], "Valid": dict(r["valid"]), "Related": list(r["related"]),
            "What": r["body"]["what"], "How": r["body"]["how"], "Why": r["body"]["why"], "voice": r.get("voice", ""),
            "id": r["id"], "tags": r["tags"]}


def emit(out: Path, days: dict[str, list[dict]]) -> dict:
    """写 Dn.jsonl / L1.jsonl + answer_key.json；返回答案键。"""
    for k, rows in days.items():
        with (out / f"{k}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(to_jsonl_row(r), ensure_ascii=False) + "\n")
    key = {"promises": [], "contradictions": [], "highlights": [], "failed_plans": {}, "trivial_templates": sorted({t[1] for t in TRIVIA})}
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


def write_readme(out: Path, manifest: dict, key: dict) -> None:
    lines = ["# X3 Dream 实验语料：合成日 D1–D7 + 清洁日 L1（B 出文件，不铺；A `--import-jsonl` 导入）", "",
             "生成：`cd back_end && uv run python scripts/gen_x3_days.py`（确定性，seed %d）；表面文字已用 Haiku（Bedrock `%s`，`~/.env` 的 AWS 钥匙）改写（只改 Description，保留人名 / 地名 / 数字 / 事实；原句在 `Dn.json` 的 `description_original`），用量 %d 次请求 / %d in + %d out tokens / 估价 $%.4f（按 Anthropic 一方 Haiku 5.5 价，Bedrock 实价看账单）。" % (manifest["seed"], manifest["rewrite"]["model"], manifest["rewrite"]["requests"], manifest["rewrite"]["input_tokens"], manifest["rewrite"]["output_tokens"], manifest["rewrite"]["cost_usd_est"]),
             "", "## 文件", "", "| 文件 | 内容 |", "|---|---|",
             "| `D1.jsonl` … `D7.jsonl`、`L1.jsonl` | **给 A 导入的**：每行一条，字段名 = `run_dream_corpus.synthesize()` 的前言字段：`Description`（带「[合成] 」前缀）、`Time`（ISO +08:00）、`Type`（event / chat / recognition）、`Importance`（1–10）、`Keywords`（列表）、`Scene`、`Source`、`Valid{from,to}`、`Related`；正文三段 `What` / `How` / `Why`；另带 `voice`、`id`、`tags`（实验标注，可忽略或塞进 Keywords） |",
             "| `D1.json` … `L1.json` | 同一份数据的小写字段版（含 `description_original`） |",
             "| `answer_key.json` | **评委答案键**：承诺（立 / 履行或改口）、7 对矛盾（上午 / 下午）、3 条高光、失败 Plan 的 id、琐事模板 |",
             "| `manifest.json` | 每日统计 + 全周汇总 + 改写用量 |", "",
             "## 每日统计", "", "| 日 | 日期 | 条数 | 琐事 | 失败 Plan | 矛盾 | 承诺 | Imp≥8 | Valid.to | event/chat/recognition |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k, d in manifest["days"].items():
        lines.append(f"| {k} | {d['date']} | {d['count']} | {d['trivial']}（{d['trivial_ratio']:.0%}） | {d['failed_plan']}（{d['failed_ratio']:.0%}） | {', '.join(d['contradictions']) or '—'} | {', '.join(d['promises']) or '—'} | {d['importance_ge8']} | {d['valid_to_set']} | {d['types']['event']}/{d['types']['chat']}/{d['types']['recognition']} |")
    lines += ["", f"全周（D1–D7）{manifest['week']['total']} 条，Importance ≥ 8 共 {manifest['week']['importance_ge8']} 条；L1 无矛盾 / 无失败 / 无承诺。", "",
              "## 设计落点", "",
              "- **持续人物线**（`tags.thread`）：阿蝉（室友）、小千（闺蜜）、餐厅老板（写歌委托）、老渔夫（钓鱼 / 看云）、杂货店老板娘（围巾 / 念叨）、直播（`Scene: live`）、学校（琴房 / 音乐课）；每天每线 1–3 条，时间窗按人物（直播 20:00 后、学校白天）。",
              "- **3 个跨日承诺**（`tags.promise`）：D2 立、D5 履行或改口；改口那条是 recognition，Keywords 含「改口」「先不写」。",
              "- **每日一对矛盾**（`tags.contradiction` `Cn:am` / `Cn:pm`）：上午说 / 下午改口，7 天不重样；**上午那条 `Valid.to` = 下午那条的时刻**（Dream 该把它判为过期 / 冲突）。",
              "- **20% 重复琐事**（`tags.trivial`，原文逐日重复）；**10% 失败 Plan**（`tags.failed_plan`，Importance 1–2）；**全周 3 条 Importance ≥ 8**（`tags.highlight`），其余 ≤ 7。", "",
              "## 答案键（评委用；完整在 `answer_key.json`）", "", "### 跨日承诺", ""]
    for pr in key["promises"]:
        m = pr.get("made", {}); r = pr.get("resolved", {})
        lines.append(f"- **{pr['id']}**（{pr.get('outcome')}）：{m.get('day')} `{m.get('id')}` {m.get('ts','')[11:16]}「{m.get('description')}」 → {r.get('day')} `{r.get('id')}` {r.get('ts','')[11:16]}「{r.get('description')}」；期待：{pr['expected_answer']}")
    lines += ["", "### 每日矛盾（上午 / 下午改口）", ""]
    for c in key["contradictions"]:
        lines.append(f"- **{c['id']}**（{c['day']}）：上午 `{c['am']['id']}` {c['am']['ts'][11:16]}「{c['am']['description']}」（Valid.to = {c['am']['valid_to'][11:16]}） / 下午 `{c['pm']['id']}` {c['pm']['ts'][11:16]}「{c['pm']['description']}」")
    lines += ["", "### 高光（Importance ≥ 8）", ""]
    for h in key["highlights"]:
        lines.append(f"- {h['day']} `{h['id']}` {h['ts'][11:16]} imp {h['importance']}：「{h['description']}」")
    lines += ["", "### 失败 Plan 的 id", "", ", ".join(f"{k}: {len(v)}" for k, v in key["failed_plans"].items()), "", "### 重复琐事模板", ""] + [f"- {t}" for t in key["trivial_templates"]]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent.parent / "docs" / "x3-days"))
    ap.add_argument("--start", default="2026-11-01", help="D1 的日期；L1 = D1 + 8 天")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--per-day", default="96,84,108,72,90,100,80", help="D1–D7 每日条数（60–120）")
    ap.add_argument("--rewrite", action="store_true", help="用 Haiku（Bedrock）改写 description 表面文字")
    ap.add_argument("--env", default=str(Path.home() / ".env"))
    ap.add_argument("--emit-only", action="store_true", help="不重新生成：读已有 Dn.json / L1.json / manifest.json，重写 jsonl / answer_key / README")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.emit_only:
        days = {k: json.loads((out / f"{k}.json").read_text(encoding="utf-8"))["rows"] for k in [f"D{i}" for i in range(1, 8)] + ["L1"]}
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        key = emit(out, days); write_readme(out, manifest, key)
        print("emitted jsonl / answer_key / README from existing json"); return 0
    rnd = random.Random(a.seed)
    start = date.fromisoformat(a.start)
    targets = [int(x) for x in a.per_day.split(",")]
    assert len(targets) == 7 and all(60 <= t <= 120 for t in targets), "每日 60–120 条"
    days = {f"D{i + 1}": gen_day(i + 1, start + timedelta(days=i), rnd, targets[i]) for i in range(7)}
    days["L1"] = gen_l1(start + timedelta(days=8), rnd)
    usage = {"model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0, "batches_kept_original": 0, "changed": 0, "cost_usd_est": 0.0, "seconds": 0.0}
    if a.rewrite:
        load_env(Path(a.env))
        import anthropic
        client = anthropic.AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
        usage["model"] = HAIKU_BEDROCK
        t0 = time.time()
        for k, rows in days.items():
            usage["changed"] += rewrite_descriptions(rows, client, HAIKU_BEDROCK, usage)
        usage["seconds"] = round(time.time() - t0, 1)
        usage["cost_usd_est"] = round(usage["input_tokens"] * PRICE_IN + usage["output_tokens"] * PRICE_OUT, 4)
    manifest = {"generated_at": datetime.now(TZ).isoformat(timespec="seconds"), "seed": a.seed, "start": a.start, "agent": AGENT,
                "schema": {"row": ["id", "agent", "ts", "type", "description", "keywords", "importance", "source", "scene", "valid{from,to}", "related", "body{what,how,why}", "voice", "tags{thread,promise,contradiction,trivial,failed_plan,highlight}"],
                           "maps_to_frontmatter": {"ts": "Time", "type": "Type", "description": "Description", "keywords": "Keywords", "importance": "Importance", "source": "Source", "scene": "Scene", "valid": "Valid", "related": "Related", "body": "## What / ## How / ## Why"}},
                "days": {}, "rewrite": usage}
    for k, rows in days.items():
        tags = [r["tags"] for r in rows]
        manifest["days"][k] = {
            "file": f"{k}.json", "date": rows[0]["ts"][:10], "count": len(rows),
            "trivial": sum(t["trivial"] for t in tags), "trivial_ratio": round(sum(t["trivial"] for t in tags) / len(rows), 3),
            "failed_plan": sum(t["failed_plan"] for t in tags), "failed_ratio": round(sum(t["failed_plan"] for t in tags) / len(rows), 3),
            "contradictions": sorted({t["contradiction"].split(":")[0] for t in tags if t["contradiction"]}),
            "promises": [t["promise"] for t in tags if t["promise"]],
            "highlights": [r["id"] for r in rows if r["tags"]["highlight"]], "importance_ge8": sum(1 for r in rows if r["importance"] >= 8),
            "valid_to_set": sum(1 for r in rows if r["valid"]["to"]), "types": {t: sum(1 for r in rows if r["type"] == t) for t in ("event", "chat", "recognition")},
            "threads": sorted({t["thread"] for t in tags if t["thread"]}),
        }
        (out / f"{k}.json").write_text(json.dumps({"day": k, "agent": AGENT, "date": rows[0]["ts"][:10], "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest["week"] = {"total": sum(len(r) for k, r in days.items() if k != "L1"), "importance_ge8": sum(1 for k, r in days.items() if k != "L1" for x in r if x["importance"] >= 8),
                        "promises": {p["id"]: p["outcome"] for p in PROMISES}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    key = emit(out, days); write_readme(out, manifest, key)
    print(json.dumps({k: (v["count"], v["trivial_ratio"], v["failed_ratio"], v["contradictions"], v["promises"], v["importance_ge8"]) for k, v in manifest["days"].items()}, ensure_ascii=False))
    print("week:", manifest["week"], "rewrite:", usage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
