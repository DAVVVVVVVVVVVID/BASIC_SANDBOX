/**
 * 旧暗色面板（HUD / 背包 / 日志 / 聊天）嵌进像素 RPG cream 面板时的配色映射（主播 11-16）。
 * RpgShell 挂载时 setUiSkin('rpg')，各处颜色字面量经 c('#xxxxxx') 取值；旧布局不受影响。
 */
let skin: 'dark' | 'rpg' = 'dark'
export function setUiSkin(s: 'dark' | 'rpg') { skin = s }
export function uiSkin() { return skin }
const MAP: Record<string, string> = {
  '#e2e8f0': '#3B2F2F', '#fff7ed': '#3B2F2F', '#a0aec0': '#7A6A5A', '#718096': '#9A8C7C', '#90cdf4': '#2F6FAE', '#c3dafe': '#2F6FAE',
  '#4a5568': '#CFC2AE', '#2d3748': '#F2EAD9', '#2a2d3e': '#F2EAD9', '#1a1b2e': '#FFFFFF', '#1a202c': '#3B2F2F',
  '#68d391': '#2E8B6E', '#9ae6b4': '#2E8B6E', '#fc8181': '#D9534F', '#e53e3e': '#D9534F', '#fbd38d': '#B7791F', '#f6ad55': '#C05621', '#ffe9a8': '#8A6116', '#ed8936': '#C05621', '#ecc94b': '#B7791F',
  '#2b6cb0': '#3BB7A8', '#2b4c7e': '#3BB7A8', '#276749': '#3BB7A8', '#742a2a': '#FF8A73', '#9b2c2c': '#FF8A73', '#553c9a': '#7E62C9', '#744210': '#B7791F', '#22543d': '#3BB7A8',
}
/** 颜色字面量 → 当前皮肤的颜色 */
export const c = (hex: string) => (skin === 'rpg' ? MAP[hex.toLowerCase()] ?? hex : hex)
/** 旧面板的半透明深底 → cream 皮肤下透明 */
export const bgDark = (rgba: string) => (skin === 'rpg' ? 'transparent' : rgba)
