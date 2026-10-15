# NCHURE Technologies — Evolution Website

A standalone Next.js App Router website located in `website/`. It is intentionally separate from the existing NCHURE CRM root so the current CRM/API deployment is not replaced by the marketing site.

## Run locally

```bash
cd website
npm install
npm run dev
```

## Deployment

Create a separate Vercel project from this repository and set **Root Directory** to `website`. Use the default Next.js framework preset. Do not change the existing CRM project's root directory if it must remain available.

## Experience implementation

- Next.js App Router, TypeScript, Tailwind CSS
- Three.js via React Three Fiber; procedural hardware geometry and physically based materials
- GSAP ScrollTrigger drives the six-step scroll progress; reverse scrolling reverses the sequence
- Reduced-motion preference skips the long scroll animation and presents the final state
- Contact enquiry is client-side validated and opens a prefilled email draft to `founder@nchure.tech`. It does not transmit/store data. Replace with a server-side route or trusted form provider before expecting direct submissions.

## Important visual limitation

The current scene is a procedural 3D prototype, not a scanned or manufacturer-grade CAD model. It uses reusable board geometry and procedural components to demonstrate a coherent evolution. The transition swaps component generations at stage boundaries; it is not a physically exact mesh morph. For production-grade product-film realism, replace the procedural groups in `components/PCBScene.tsx` with a reviewed, optimized GLB/GLTF assembly with named meshes/materials, baked normal/roughness maps and explicit per-stage transforms. No client achievements or performance metrics are fabricated in the content.

## Quality checks

Run `npm run build` and `npm run lint` from this directory. Browser-level scroll, WebGL, mobile and reduced-motion QA still needs to be performed against a deployed preview. No deployment or build success should be assumed until CI/preview checks complete.
