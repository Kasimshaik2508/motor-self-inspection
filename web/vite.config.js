import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base: './'  -> the built files use relative paths, which Capacitor needs (it loads them from inside the app).
// proxy       -> while developing (npm run dev), calls to /api go to the FastAPI server on port 8000,
//                so the browser sees one address and no CORS setup is needed locally.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
