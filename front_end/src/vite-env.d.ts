/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_PROXY_TARGET?: string
  readonly VITE_PORT?: string
  readonly VITE_OBSERVE_BASE?: string
  readonly VITE_OBSERVE_TARGET?: string
  readonly VITE_TOWNS_YAML?: string
  readonly VITE_DATASET_DIR?: string
  readonly VITE_SANDBOX_DATA_DIR?: string
  readonly VITE_GAME_RUNS_DIR?: string
  readonly VITE_SELF_DAYS_DIR?: string
  readonly VITE_SELF_MEMORY_DIR?: string
}
