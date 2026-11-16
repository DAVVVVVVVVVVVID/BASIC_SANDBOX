# 上课系统 v1 · 沙盒侧方案（会话 B，2026-11-16 草案）

依据：whale `docs/systems/class-system.md`（0ebfa5c，主播 11-16 晚拍板）§2 / §4–§6。沙盒负责：课程表、上课中状态、10 分钟分段推送、打瞌睡、提问 / 作答、考勤、课堂笔记物品与转交、作业提交箱、api-spec。
节奏：11-17 起对课案格式，11-18（周二）开工，11-19（周四）前 bench 能跑一节完整课，11-22（周日）10:00 窗上线，11-23（周一）开学；封测周内不进主镇。

## 1. 课程表配置 `game/school.json`（新文件，进 mapVersion 外的配置指纹）

```json
{
  "schema": 1,
  "term_start": "2026-11-23",
  "weeks": ["游戏 BGM", "City Pop", "摇滚", "民谣", "电子舞曲", "R&B", "动画歌曲", "国风"],
  "courses": {
    "genre":   {"name": "类型创作", "required": true},
    "lyrics":  {"name": "歌词写作", "required": true},
    "harmony": {"name": "和声学",   "required": true},
    "writing": {"name": "写作",     "required": false},
    "review":  {"name": "作业讲评", "required": true}
  },
  "timetable": {
    "mon": [["09:00", "genre"],   ["10:45", "lyrics"]],
    "tue": [["09:00", "harmony"], ["10:45", "genre"],   ["14:00", "writing"]],
    "wed": [["09:00", "lyrics"],  ["10:45", "harmony"]],
    "thu": [["09:00", "genre"],   ["10:45", "lyrics"],  ["14:00", "writing"]],
    "fri": [["09:00", "harmony"], ["10:45", "review"]]
  },
  "lesson_minutes": 90,
  "segment_minutes": 10,
  "segments_per_lesson": 9,
  "late_after_minutes": 10,
  "students": ["whale", "claudine"],
  "elective_students": {"writing": ["whale"]},
  "room": "classroom",
  "desks": ["classroom_desk_1", "classroom_desk_2"],
  "doze": {"per_segment": {"whale": 0.05}, "seed": "class-v1"},
  "homework": {"due": "fri 10:45", "box": "homework_box"},
  "lesson_dir": "school"
}
```

- 课时段：`start` 起 90 分钟。时段外 `use` 课桌 = 普通自习（现行为不变）。
- 课案找不到（A 当晚没生成 / 文件坏）：这节课照常开、考勤照记，讲授段推「老师今天讲得比较散，没记住要点」占位，日志 `lesson_missing`，不报错。

## 2. 课案文件（**请 A 确认**）`run/data/<town>/school/<YYYY-MM-DD>.json`

沙盒只读、不改。沙盒按 `SANDBOX_DATA_DIR` 向上找 `data/<town>/school/`（与 interventions 同规则；`SANDBOX_SCHOOL_DIR` 可覆盖）。

```json
{
  "schema": 1,
  "date": "2026-11-23",
  "town": "main",
  "generated_at": "2026-11-22T23:30:12+08:00",
  "syllabus_ref": {"week": 1, "genre": "游戏 BGM"},
  "lessons": [
    {
      "lesson_id": "2026-11-23-0900-genre",
      "start": "09:00",
      "course": "genre",
      "title": "游戏 BGM：战斗音乐",
      "segments": [
        {"i": 1, "text": "（≤ 400 字，一段讲授原文）"},
        {"i": 2, "text": "…"}
      ],
      "questions": [
        {"qid": "q1", "phase": "mid", "after_segment": 5, "text": "…", "answer": "…", "explanation": "…"},
        {"qid": "q2", "phase": "end", "after_segment": 9, "text": "…", "answer": "…", "explanation": "…"}
      ],
      "homework_note": "（必修课最后一段后推；无作业 null）"
    }
  ]
}
```

约定：
- `segments` 恰好 9 段（少于 9 段沙盒补占位、多于 9 段截断，都记日志）；`text` 是**会原样进笔记物品**的文字。
- `lesson_id` = `<date>-<HHMM>-<course>`，全局唯一，作答 / 笔记 / 考勤都用它。
- `questions`：课中 1 问（`phase: mid`）+ 课末 1–2 问（`phase: end`）；`answer` 给标准答案，作答后**当场公布**（和声学按设计稿）。写作选修的作文题 `answer` 可为空：**不当堂打分，改下课后出分**（总控 11-16 定）——作文随 `answer` 落 answers.jsonl，A 的评分器下课后 10 分钟内出分，调沙盒 `POST /school/grade` 推给本人（见 §6）。
- 作业讲评课（`review`）的段落由 A 读 `school/submissions.jsonl` 生成；沙盒不区分。

## 3. 上课过程

- **入座**：课时段内学生 `use` 课桌 → 记入座时刻；tag `in_class`、`stateLabel`「<名字>在上<课名>」；`GET /player.lesson` / perceive `lesson`：`{lesson_id, course, title, start, end, segment_i, attendance, next_segment_at, question?}`。
- **推送**：开课后第 `k` 段在 `start + (k−1)×10 分钟` 推（第 1 段开课即推）；只推给此刻坐在课桌上的学生：`pendingMessage`「【<课名>】<段落原文>」，perceive `lesson.segment {i, text}`；迟到者从入座时的当前段起收，错过的段在笔记里记「（没来）」。
- **打瞌睡**：每推一段先掷骰：`hash(seed, town, lesson_id, agent_id, i) / 2^64 < p`（p 按 `doze.per_segment`，缺省 0；目前只有鲸仔 0.05）→ 这段不推，笔记记「……（这段睡着了）」，下一段推送前缀「（刚才走神睡着了）」；external 日志 `school action=doze`。同一 lesson / 学生 / 段结果固定，重启 / 重放可复现。
- **提问**：到 `after_segment` 那段推完时推问题（pendingMessage + perceive `lesson.question {qid, text, phase, deadline}`），作答窗到下一段推送或下课（课末题到下课后 10 分钟）。
- **作答**：新动作 `answer {qid, text}`（≤ 500 字）——坐着上课也能用（不受 no_use / no_interact 限制）；每人每题一次；成功即回 `result {qid, correct_answer, explanation}`（当场公布）；`school/answers.jsonl` 一行 `{ts, game_time, town, lesson_id, qid, phase, agent_id, player, text, answered_at_segment, late}`；超窗 `question_closed`、重复 `already_answered`、不在课上 `not_in_class`。
- **考勤**：开课 10 分钟内入座 = `present`，之后 = `late`，下课时没入座过 = `absent`；早退（下课前离座且没回来）记 `left_early_at`。`GET /school/today?player=` 给当天全部课的考勤，**同学互相可见**；`school/attendance.jsonl` 每节下课写一行 / 人。
- **作业提醒**：必修课第 9 段推完后推 `homework_note`。
- **下课**：`start + 90 分钟` 自动结束：在座学生离座（reason `class_over`）、发笔记、写考勤。

## 4. 课堂笔记物品 `class_notes`

- items.json 新类型（class `note`，不坏、可叠吗：**不叠**——每本 meta 不同）。下课时给每个出勤 / 迟到学生发一本：`meta {lesson_id, course, title, date, owner, segments: [{i, text | null, status: "heard" | "slept" | "absent"}]}`；`text` 就是她实际收到的原文。
- **读**：新动作 `read_item {item: "class_notes", match: {lesson_id}}` → `result.message` 拼好的全文（睡着段「……（这段睡着了）」、没来段「（没来）」）；不占时间。
- **借**：`give {target, item: "class_notes", lesson_id}` 转交整本（meta 跟着走——把 v1.3.10 给 CD 写的「按张转交、meta 随行」推广到所有带 meta 的物品，修掉现在通用 give 会丢 meta 的问题）。读完还不还随她。

## 5. 作业提交箱 `homework_box`（11-16 夜按总控 whale-c2 口径改：Suno MCP 搁置）

背景：作业改为「创作单 + 歌词」交，每人每周只挑 1 首走主播代做出音频，其余没有音频、永远到不了 final——所以提交箱**不再只收 final**。

- 新物品类型（instant、interactable），摆在教学楼 (8,4)（门内格 (5,4) 不挡；站 (8,3) 朝 down）；`/world.objects[]` 带 `hint`。
- `use {request_id?}`（不带 = 本周还没交过的最近一张 CD）→ 提交：
  - 收 `pending / delivered / final` 的 compose CD（meta 里有创作单即可）；`redo`（鲸仔自己收到成品后评满意度 < 3）→ `cd_redo`，**但这首已以创作单身份交上的那条提交保留、不作废**；没 CD → `no_item`。
  - `school/submissions.jsonl` 一行 `{ts, game_time, town, week, agent_id, request_id, title, receipt_id, late, audio, creation_sheet_complete, meta 快照}`。
  - `audio`：CD `status: final`（她验收过的成品）→ `final`；meta `proxy: true`（本周代做那首，含已送达待她评、redo 重做中）→ `pending`；否则 `none`。**delivered 不算 final**——成品送达后她可能判重做。
  - `creation_sheet_complete`：`title / genre / scene / mood / form / chords / arrangement` 齐（有词时再加 `lyrics`）。
  - **CD 不没收**；回执 = `result {message, receipt_id, late, due, audio}` + 背包一张 `homework_receipt`（meta 同行）。
- **同一 request_id 再 use = 更新这条**：只更新 `audio`（及 meta 快照），**沿用原 `receipt_id`、`late` 按首次提交时刻不变**；submissions.jsonl 追加一行 `action: update`（不改旧行），回执物品的 meta 同步更新；`result.updated: true`。同一张 CD 交到**另一周** → `already_submitted`。
- 自动更新：她用 `edit_item` 把代做那首标 `final` 时，沙盒**顺带**把**同一周**的那条提交更新为 `audio: final`（她再 use 一次也一样）；管理口标 `delivered` 不触发（还待她评）。redo 在 music v1 里是对同一张 CD 改状态（request_id 不变、`redo_count` +1），重做成品 final 后同周照常更新。**过了本周才 final 的不更新**，那条提交的 audio 停在 pending（与跨周 `already_submitted` 一致）。
- 标代做：她（agent）用 `edit_item {match: {request_id}, set: {proxy: true}}`（`proxy` 加进 edit_item 白名单）；C 侧每人周三 23:00 前挑一首，没挑默认第一首——逻辑在 C。
- 截止：本周 `fri 10:45`（配置）；之后首次提交 `late: true`。
- 评分在 A：只读创作单 + 歌词，不依赖音频；结果经 `POST /school/grade {kind: homework, receipt_id, …}` 推本人。

## 6. 接口一览（v1.4.0 目标）

| 接口 | 说明 |
|---|---|
| `GET /school/timetable` | 配置课表 + 本周类型 |
| `GET /school/today?player=` | 今天各节：课名、时段、状态（未开 / 进行中 / 已下课）、我的考勤、同学考勤 |
| `GET /player.lesson` / perceive `lesson` | 当前课：段号、最近一段、待答问题、考勤 |
| 动作 `answer {qid, text}` | 作答（当场公布答案） |
| 动作 `read_item {item, match}` | 读笔记 |
| `give` | 笔记 / CD 等带 meta 物品按本转交 |
| `use homework_box {request_id?}` | 交作业 |
| ws `lesson` 事件 | `{event: start / segment / question / end, lesson_id, …}`（不带段落正文，正文走 GET；同 qq 口径） |
| `POST /school/grade` | A 的评分器回写：`{agent_id, lesson_id?, qid?, receipt_id?, grade: A|B|C, comment ≤ 200 字, kind: writing|homework}` → 本人 `pendingMessage`「写作课成绩：B，评语…」/「作业成绩：…」、`school/grades.jsonl` 一行、ws `lesson {event: grade}`；作业成绩另按配置影响心情（A=+5 / B=0 / C=−3，可调）。不受 SANDBOX_SCENARIO 门控，用 SELF_TOKEN 鉴权 |
| 数据 | `school/answers.jsonl`、`attendance.jsonl`、`submissions.jsonl`、`grades.jsonl`（沙盒写），`syllabus.json`、`<日期>.json`（A 写） |

## 7. 估工

| 块 | d |
|---|---|
| school.json + 课表 / 时段判定 + 课案加载与容错 | 0.4 |
| 上课中状态、分段推送、打瞌睡、perceive / GET lesson、ws | 0.5 |
| 提问 / 作答 / answers.jsonl | 0.3 |
| 考勤 / attendance.jsonl / GET /school/today | 0.2 |
| 笔记物品、read_item、带 meta 物品 give 推广 | 0.3 |
| 作业提交箱（物品、地图摆放、截止、回执、submissions.jsonl） | 0.3 |
| 单测 + bench 一节完整课冒烟 + api-spec | 0.4 |
| **合计** | **≈ 2.4 d** |

## 8. 待定（请总控 / A / C 回）

**总控 11-16 已拍**：① 提交 CD 不没收，只记快照 + 回执；同一张 CD 交两次（跨周 / 跨课）都拒。② 写作选修不做同步评分，下课后 10 分钟内由 A 出分经 `POST /school/grade` 推本人。③ 小克不打瞌睡（`doze.per_segment` 只给 whale 0.05）。剩 A 认课案 schema、C 认创作单字段名。

1. 课案格式（§2）A 确认或改。
2. 提交 CD 后不没收、只记快照 + 发回执——OK？
3. 写作选修「当堂打分」：沙盒记答案，分数由 A 事后打并写回？还是当堂要出分（那需要 A 提供一个同步评分接口）？
4. 小克是否也有打瞌睡概率（设计稿只写鲸仔，缺省 0）。
5. 课时段内教学楼门 08:00–20:00 已覆盖，不改。

## 9. 前端需求（会话 E 11-16，v1.4.0 一并给）

1. `GET /world.players[]` 与 ws upsert 每人带精简 `lesson {lesson_id, course, title, dozing}`（不在课为 null；`dozing` = 当前段睡着了），头顶「上课中 / zZ」不用逐人轮询；ws `lesson` 事件 `doze` 带 `entity`（player id）。
2. `GET /player.inventory[]` 原样带 `class_notes` 的完整 `meta.segments[{i, text, status}]` 与 `homework_receipt` 的 meta——跟随视角只读也能看全文（`read_item` 只是 agent 用的便捷入口）。
3. CD 创作单字段名（建议 C 在 compose 时放进 meta）：`title / genre / scene / mood / form / chords / lyrics / arrangement`；前端缺字段就不显示。待 C 确认后定稿。
4. `homework_box` 在 `/world.objects[]` 带 `hint`：「带着 CD 使用 = 交作业，截止周五 10:45（之后算迟交）」（截止时刻按配置拼）；前端只展示 `result.message / late / due`，不判断能不能交。
5. `GET /school/today?player=` 返回结构落地后贴样例给 E。

## 10. agent 侧加项（会话 C 11-16，v1.4.0 一并给）

1. perceive `lesson` / `GET /player.lesson` 加 `dozed_prev: bool`——刚推的这段的**前一段**睡着了（C 据此出「找小克借笔记」意图）；与 pendingMessage 前缀「（刚才走神睡着了）」同源。
2. `GET /school/today?player=` 带本周作业状态 `homework {week, due, submitted: [{receipt_id, request_id, title, late, audio, at}], count}`（`audio` 让待办显示「代做那首还没回来」）。
3. compose 的 meta 透传白名单（v1.3.10）加创作单字段 `genre / scene / mood / form / chords / arrangement / homework_week`（`title / lyrics` 已有）；**字段名定稿**，E 按这套显示、A 评分直接读。
4. **睡着那段正好是 `after_segment`：问题照推，人被叫醒**——这段讲授不推（笔记记 slept），问题推送前缀「（刚才走神睡着了）」，作答窗照常（到下一段推送 / 课末题到下课后 10 分钟）。打瞌睡只吞讲授，不吞问题。
