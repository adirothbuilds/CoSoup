import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:90000,workers:1,fullyParallel:false,retries:0,
  outputDir:'../../test-results',use:{baseURL:process.env.SCANNER_TEST_ORIGIN??'http://127.0.0.1:8081',trace:'off',video:'off',screenshot:'off'},
  projects:[{name:'desktop-chromium',use:{...devices['Desktop Chrome'],launchOptions:process.env.SCANNER_CHROMIUM_PATH?{executablePath:process.env.SCANNER_CHROMIUM_PATH}:undefined}},
    {name:'iphone-layout-chromium',use:{...devices['iPhone 13'],defaultBrowserType:'chromium',launchOptions:process.env.SCANNER_CHROMIUM_PATH?{executablePath:process.env.SCANNER_CHROMIUM_PATH}:undefined}},
    ...(process.env.SCANNER_TEST_WEBKIT==='1'?[{name:'iphone-webkit',use:{...devices['iPhone 13']}}]:[])]});
