# CoSoup kitchen animation

The web kitchen combines original Steve cel artwork with a lightweight Canvas animation in `apps/web/src/components/kitchen-animation.ts`. The six-second cooking loop tosses decorative stock symbols; a separate serving pose responds to a newly published report. Editing this animation requires no Blender installation.

The small animated bowl mark is rendered from a procedural Blender scene. With Blender 4.3 or later and FFmpeg with `libwebp`/`libwebp_anim` on PATH, run from the repository root:

```sh
blender --background --threads 4 --python tools/mascots/build_bowl.py -- \
  --output-dir apps/web/public/mascots \
  --scene-file /tmp/cosoup-bowl.blend
```

The script saves an editable `.blend` scene and 48 transparent PNG frames beside that scene, then exports `bowl-idle.webp` and `bowl-poster.webp` into the web assets. It uses CPU rendering with no network or credentials. Keep generated scenes and frame directories outside the checkout. Blender is needed only to change/render the mark; the Mac/Linux Docker installer uses the committed WebP assets.

Steve's transparent four-pose atlas and separate tossing pose are original generated artwork from the CoSoup animation study. Their optimized WebP versions live in `apps/web/public/mascots`; see its asset notes. Global pause and device reduced motion are handled in `Kitchen.tsx` and `Theme.tsx`. The canvas stops updating when hidden/offscreen, and the serving pose ends after one second.

All source and original artwork follow the repository MIT license. Stock labels are illustrative ingredients, never live signals or market data.
