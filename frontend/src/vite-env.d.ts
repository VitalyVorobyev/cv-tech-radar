/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" when the build is targeting the public static site (no backend). */
  readonly VITE_STATIC?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
