# Assets — Intara

Place AI-generated assets here as per `ASSET_PROMPTS.md`.

## Folder Structure
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

## Import Map (for code)

FE will import as:
```ts
import planet from '@/assets/planet-intara.png'
import starfield from '@/assets/starfield.jpg'
import wishOrb from '@/assets/wish-orb.png'
import nebula from '@/assets/nebula-gradient.png'
import schemaGlyph from '@/assets/glyphs/schema.png'
```

Vite handles `assets/` via `public/` or `src/assets/` alias — after placement, run `npm run dev` and check no 404 in console.

## Placeholders

If asset missing, app uses CSS fallback — so you can start with empty folder and add later.

## Checklist

- [ ] planet-intara.png
- [ ] starfield.jpg
- [ ] wish-orb.png
- [ ] constellation.svg
- [ ] nebula-gradient.png
- [ ] glyphs/schema.png
- [ ] glyphs/frontend.png
- [ ] glyphs/backend.png
- [ ] glyphs/scroll.png

After placing, run:
```bash
ls -lh assets/ assets/glyphs/
```
and notify agent.
