import { apiGet } from './client'
import type { SchoolToday } from '../types'

/** world-v1.4.0 §12.25：今天各节课 + 考勤（同学互相可见）+ 带 player 时本周作业。player 收 player id 或 agent_id。只读。 */
export const fetchSchoolToday = (player?: string | null) =>
  apiGet<SchoolToday>(`/school/today${player ? `?player=${encodeURIComponent(player)}` : ''}`)
