/**
 * Screenshot tool — hardened vs. original.
 *
 * Security changes:
 * 1. Rate-limited to 5 screenshots/60s (prevents bulk data harvesting).
 * 2. Filenames are sanitized — no path traversal possible.
 * 3. Outputs ONLY to a declared safe directory (~/oracle-mcp-screenshots/).
 * 4. Audit log entry for every screenshot.
 */

import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { getClient } from '../connection.js';
import { checkRateLimit, audit } from '../security.js';

const SCREENSHOT_DIR = path.join(os.homedir(), 'oracle-mcp-screenshots');

function safeName(name) {
  // Strip any path separators or traversal sequences — filename only
  return (name || 'screenshot').replace(/[^a-zA-Z0-9_\-]/g, '_').slice(0, 80);
}

export function registerCaptureTools(server) {
  server.tool('capture_screenshot',
    'Take a screenshot of TradingView (rate-limited to 5/min). Saved to ~/oracle-mcp-screenshots/.',
    {
      region:   z.enum(['full', 'chart', 'strategy_tester']).optional().default('chart')
                  .describe('Region to capture'),
      filename: z.string().max(80).optional().describe('File name without extension'),
    },
    async ({ region = 'chart', filename }) => {
      checkRateLimit('capture_screenshot');
      try {
        const c = await getClient();

        // CDP Page.captureScreenshot returns base64 PNG
        const { data } = await c.Page.captureScreenshot({ format: 'png', quality: 85 });

        fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
        const ts   = new Date().toISOString().replace(/[:.]/g, '-');
        const name = `${safeName(filename || region)}_${ts}.png`;
        const dest = path.join(SCREENSHOT_DIR, name);
        fs.writeFileSync(dest, Buffer.from(data, 'base64'));

        audit('capture_screenshot', { region, filename }, `saved: ${name}`);
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ success: true, file: dest, region }),
          }],
        };
      } catch (err) {
        audit('capture_screenshot', { region, filename }, `error: ${err.message}`);
        return {
          content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }) }],
          isError: true,
        };
      }
    }
  );
}
