// Render index.html to a Letter PDF with Chrome. Usage: node build.mjs <out.pdf>
import { chromium } from '../slides/deck/node_modules/playwright-chromium/index.mjs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const here = path.dirname(fileURLToPath(import.meta.url))
const out = process.argv[2] || path.join(here, 'SEAN-D1-architecture.pdf')
const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome' })
const p = await b.newPage()
await p.goto('file://' + path.join(here, 'index.html'), { waitUntil: 'networkidle' })
await p.evaluate(() => document.fonts.ready)
await p.pdf({ path: out, preferCSSPageSize: true, printBackground: true })
await b.close()
console.log('wrote', out)
