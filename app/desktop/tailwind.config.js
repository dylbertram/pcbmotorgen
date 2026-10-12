/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{svelte,js,ts}"],
  theme: {
    extend: {
      colors: {
        slate: Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map(shade => [shade, `rgb(var(--slate-${shade}) / <alpha-value>)`])),
      },
    },
  },
  plugins: [],
};
