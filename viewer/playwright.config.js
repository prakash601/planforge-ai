import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  outputDir: "../outputs/browser-tests",
  workers: 1,
  use: {
    baseURL: process.env.PLANFORGE_VIEWER_URL || "http://127.0.0.1:8765",
    launchOptions: {
      args: [
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
      ],
    },
  },
});
