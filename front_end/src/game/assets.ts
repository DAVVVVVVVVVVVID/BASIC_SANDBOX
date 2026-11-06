/**
 * 自制 CC0 素材清单（由 tools/gen_assets.py 生成到 public/assets/gen/）。改生成器时同步这里。
 */
export const GEN_DIR = 'assets/gen'
export const GEN_TILES_KEY = 'gen_tiles'
export const GEN_TILE = 16
export const GEN_TILE_COLS = 8

/** 与 tools/gen_assets.py 的 TILE_NAMES 顺序一致 */
export const TILE_INDEX = {
  grass: 0, grass_flower: 1, grass_park: 2, road: 3, square: 4, dock: 5, floor_wood: 6, floor_tile: 7,
  wall_top: 8, wall_face: 9, water0: 10, water1: 11, water2: 12, water3: 13, carpet: 14, shop_floor: 15,
  door: 16, grass_dark: 17,
} as const
export type TileName = keyof typeof TILE_INDEX
export const WATER_FRAMES = [TILE_INDEX.water0, TILE_INDEX.water1, TILE_INDEX.water2, TILE_INDEX.water3]

export const CHAR_KEYS = ['whale', 'achan', 'cook', 'grocer', 'fisher', 'regular', 'villager', 'whale_v1', 'achan_v1'] as const
export type CharKey = typeof CHAR_KEYS[number]
export const CHAR_FRAME = { w: 16, h: 24 }
/** 行：down / left / right / up；列：站 走A 站 走B；第 5 行：坐(正) 睡 坐(左) 坐(右) */
export const CHAR_ROWS: Record<'down' | 'left' | 'right' | 'up', number> = { down: 0, left: 1, right: 2, up: 3 }
export const POSE_ROW = 4

/** `?art=v1` 时鲸仔 / 阿蝉用 persona 文字版形象 */
let artVersion: 'v1' | 'v2' = 'v2'
export function setArtVersion(v: 'v1' | 'v2') { artVersion = v }
export function resolveCharKey(k: CharKey): CharKey {
  if (artVersion === 'v1' && (k === 'whale' || k === 'achan')) return `${k}_v1` as CharKey
  return k
}

export const OBJ_KEYS = [
  'bed', 'bed_21', 'bath', 'fridge', 'desk', 'stream_desk', 'desk_12', 'book', 'phone', 'restaurant_table',
  'bench', 'fishing_spot', 'shop_counter', 'sofa', 'cook', 'sink', 'toilet', 'well', 'tree', 'game_console',
] as const

export const objTextureKey = (type: string) => `objgen_${type}`
export const charTextureKey = (key: CharKey) => `char_${key}`

const NPC_POOL: CharKey[] = ['cook', 'grocer', 'fisher', 'regular', 'villager']

/** 按名字 / 身份挑角色外观：鲸仔、阿蝉固定，NPC 先按关键词，否则按名字哈希稳定分配 */
export function charKeyFor(name: string, controller?: string): CharKey {
  const n = (name || '').toLowerCase()
  if (/鲸|whale/.test(n)) return 'whale'
  if (/阿蝉|achan|蝉/.test(n)) return 'achan'
  if (/厨|cook|chef/.test(n)) return 'cook'
  if (/杂货|grocer|店/.test(n)) return 'grocer'
  if (/渔|fish/.test(n)) return 'fisher'
  if (/常客|regular/.test(n)) return 'regular'
  if (controller === 'human') return 'achan'   // 作者进来操控默认是阿蝉
  let h = 0
  for (const ch of n) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return NPC_POOL[h % NPC_POOL.length]
}

/** 预加载全部自制素材（幂等） */
export function preloadGenAssets(scene: Phaser.Scene) {
  if (!scene.textures.exists(GEN_TILES_KEY)) {
    scene.load.spritesheet(GEN_TILES_KEY, `${GEN_DIR}/tiles.png`, { frameWidth: GEN_TILE, frameHeight: GEN_TILE })
  }
  for (const k of CHAR_KEYS) {
    if (!scene.textures.exists(charTextureKey(k))) {
      scene.load.spritesheet(charTextureKey(k), `${GEN_DIR}/char_${k}.png`, { frameWidth: CHAR_FRAME.w, frameHeight: CHAR_FRAME.h })
    }
  }
  for (const k of OBJ_KEYS) {
    if (!scene.textures.exists(objTextureKey(k))) scene.load.image(objTextureKey(k), `${GEN_DIR}/obj_${k}.png`)
  }
}

/** 角色与水面动画（幂等） */
export function createGenAnimations(scene: Phaser.Scene) {
  const anims = scene.anims
  for (const k of CHAR_KEYS) {
    const tex = charTextureKey(k)
    if (!scene.textures.exists(tex)) continue
    for (const dir of ['down', 'left', 'right', 'up'] as const) {
      const row = CHAR_ROWS[dir] * 4
      if (!anims.exists(`${k}_idle_${dir}`)) anims.create({ key: `${k}_idle_${dir}`, frames: [{ key: tex, frame: row }], frameRate: 1, repeat: -1 })
      if (!anims.exists(`${k}_walk_${dir}`)) {
        anims.create({ key: `${k}_walk_${dir}`, frames: anims.generateFrameNumbers(tex, { frames: [row + 1, row, row + 3, row] }), frameRate: 8, repeat: -1 })
      }
    }
    const pr = POSE_ROW * 4
    const sitFrame: Record<string, number> = { down: pr, up: pr, left: pr + 2, right: pr + 3 }
    for (const dir of ['down', 'left', 'right', 'up'] as const) {
      if (!anims.exists(`${k}_sit_${dir}`)) anims.create({ key: `${k}_sit_${dir}`, frames: [{ key: tex, frame: sitFrame[dir] }], frameRate: 1, repeat: -1 })
    }
    if (!anims.exists(`${k}_sleep`)) anims.create({ key: `${k}_sleep`, frames: [{ key: tex, frame: pr + 1 }], frameRate: 1, repeat: -1 })
  }
  if (scene.textures.exists(GEN_TILES_KEY) && !anims.exists('gen_water')) {
    anims.create({ key: 'gen_water', frames: anims.generateFrameNumbers(GEN_TILES_KEY, { frames: WATER_FRAMES }), frameRate: 2, repeat: -1 })
  }
}
