# Electron Desktop Module

- Location: `desktop-demo/`; separate Electron 42.4.1 client using plain HTML/CSS/JavaScript and Node >=22.12.
- Renderer never calls FastAPI directly. Renderer -> preload allowlisted API -> Electron main process -> local backend HTTP. Keep Gemini/Kakao secrets in backend/root `.env`.
- Structure:
  - `src/components/{layout,ui,watchlist,analysis,alerts}`: presentation.
  - `src/controllers`: event binding and UI flow.
  - `src/services/backend-service.js`: backend access point.
  - `src/state/app-state.js`: state, API normalization, view models.
  - `src/renderer.js`: startup/composition.
  - `main.js` and `preload.js`: Electron/backend boundary.
- Add UI pieces under the relevant component area; keep API access in services, transformations in state, and interaction orchestration in controllers.
- Documented commands: `npm install`, `npm start`, `npm run check`. Read `mem:task_completion` for cross-module verification.