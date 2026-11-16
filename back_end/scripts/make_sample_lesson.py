#!/usr/bin/env python3
"""
上课系统 v1：给某天写一份**示例课案**（A 的正式课案没出来时，bench 冒烟用）。格式 = docs/class-system-sandbox.md §2。

  cd back_end && uv run python scripts/make_sample_lesson.py --date 2026-11-19 --dir /home/shan-dw/Project/run/data/bench/school [--term-start 2026-11-16]

按 game/school.json 的课表生成当天每节：9 段讲授 + 课中 1 问（第 5 段后）+ 课末 1 问 + 作业提醒（必修）。已存在的文件不覆盖（--force 覆盖）。
"""
import argparse, json, os, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True); ap.add_argument("--dir", required=True); ap.add_argument("--term-start", default=None); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.term_start:
        os.environ["SANDBOX_SCHOOL_TERM_START"] = a.term_start
    from game import school
    school.reload_cfg()
    lessons = school.lessons_for_date(a.date)
    if not lessons:
        print(f"{a.date} 没有课（周末或开学前；可用 --term-start 提前）"); return 1
    w = school.week_of(a.date); genre = school.week_genre(w)
    out = {"schema": 1, "date": a.date, "town": os.environ.get("SANDBOX_TOWN", "bench"), "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "syllabus_ref": {"week": w, "genre": genre}, "sample": True, "lessons": []}
    for l in lessons:
        cname = l["course_name"]
        out["lessons"].append({
            "lesson_id": l["lesson_id"], "start": l["start"], "course": l["course"], "title": f"{genre}·{cname}（示例）",
            "segments": [{"i": i, "text": f"【示例】{cname}第 {i} 段：{genre} 的要点 {i}。"} for i in range(1, 10)],
            "questions": [{"qid": f"{l['course']}-q1", "phase": "mid", "after_segment": 5, "text": f"{cname}课中题：{genre} 最常见的节奏特征是什么？", "answer": "示例答案", "explanation": "示例解析"},
                          {"qid": f"{l['course']}-q2", "phase": "end", "after_segment": 9, "text": f"{cname}课末题：用一句话总结今天。", "answer": "示例答案", "explanation": "示例解析"}],
            "homework_note": (f"本周作业：三首 {genre}，周五 10:45 前交到教学楼作业提交箱。" if school.cfg()["courses"][l["course"]]["required"] else None)})
    d = Path(a.dir); d.mkdir(parents=True, exist_ok=True)
    f = d / f"{a.date}.json"
    if f.exists() and not a.force:
        print(f"已存在，不覆盖：{f}"); return 1
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {f}：{[x['lesson_id'] for x in out['lessons']]}"); return 0


if __name__ == "__main__":
    sys.exit(main())
