# Assets — Intara

Static artwork used by the landing page and Studio.

## Folder structure

```
assets/
  planet-intara.png       # 1024×1024 transparent
  starfield.jpg           # 1920×1080
  wish-orb.png            # 512×512
  constellation.svg       # 800×400
  nebula-gradient.png     # 1200×800
  glyphs/
    schema.png
    frontend.png
    backend.png
    scroll.png
```

## Import map

The frontend imports assets by path:

```ts
import planet from '@/assets/planet-intara.png'
import starfield from '@/assets/starfield.jpg'
import wishOrb from '@/assets/wish-orb.png'
import nebula from '@/assets/nebula-gradient.png'
import schemaGlyph from '@/assets/glyphs/schema.png'
```

Vite serves them from `public/` or through the `src/assets/` alias. If an asset is missing, the app falls back to CSS gradients and inline glyphs, so the UI remains usable.
