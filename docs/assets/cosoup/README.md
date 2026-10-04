# CoSoup assets

A small, repository-local identity set for documentation and future interfaces:

| Asset | Use |
| --- | --- |
| [banner.svg](banner.svg) | Compact README header; uses the shared design palette. |
| [mark.svg](mark.svg) | Simplified vector mark for small surfaces. |
| [mascots.png](mascots.png) | Steve and the friendly bowl on a light presentation background. |
| [steve.png](steve.png) | Standalone chef illustration with transparency. |
| [bowl.png](bowl.png) | Standalone friendly bowl illustration with transparency. |
| `badges/*.svg` | Static, local technology and license badges. |

The illustrations are AI-generated original mascot artwork, rather than characters copied from the anime references. These repository assets are covered by the root [MIT License](../../../LICENSE). They contain no private portfolio data. Decorative candle shapes are not live signals or performance claims. No external image, font or badge service is required.

The PNGs are illustration sources; the SVG mark is the preferred starting point for small icons. The app names, package scopes, deployment paths and app icons remain unchanged by this documentation branding.

## Badge maintenance

Badges are static documentation, not build status or automatically updating version claims. When dependency pins change, update the corresponding SVG title/text and root README alt text together:

- Python `3.12+`: root development guide and server Dockerfile.
- Node `24 LTS`: root development guide and web build Dockerfile. This is the documented development toolchain, not the minimum `engines.node` version or the optional Codex image's Node version.
- FastAPI: `apps/server/requirements.txt`.
- React: `apps/web/package.json` (also used by mobile).
- Expo: `apps/mobile/package.json`.
- TypeScript: root `package.json`.
- MIT: root `LICENSE`.

Keep the SVGs self-contained: no scripts, remote references or embedded credentials.
