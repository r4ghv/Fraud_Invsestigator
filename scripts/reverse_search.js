import puppeteer from 'puppeteer-core';
import path from 'path';
import fs from 'fs';

export async function reverseImageSearch(imagePath, options = {}) {
  const absolutePath = path.resolve(imagePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`File not found: ${absolutePath}`);
  }

  const timeout = options.timeout || 35000;
  const executablePath = options.executablePath || '/usr/bin/google-chrome-stable';

  const browser = await puppeteer.launch({
    executablePath,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-blink-features=AutomationControlled',
      '--disable-gpu',
      '--window-size=1366,768',
      '--lang=en-US,en'
    ]
  });

  try {
    const page = await browser.newPage();
    await page.setUserAgent(
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    );
    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => false });
      window.chrome = { runtime: {} };
    });

    await page.setViewport({ width: 1366, height: 768 });

    console.log(`[SearchEngine] Connecting to visual search service...`);
    await page.goto('https://www.bing.com', { waitUntil: 'networkidle2', timeout });

    // Open visual search panel
    const cameraIcon = await page.$('#sb_sbi, [aria-label*="Search using an image" i]');
    if (cameraIcon) {
      await cameraIcon.click();
      await new Promise(r => setTimeout(r, 600));
    }

    console.log(`[SearchEngine] Submitting face image: ${path.basename(absolutePath)}...`);
    await page.waitForSelector('#sb_fileinput', { timeout: 10000 });
    const fileInput = await page.$('#sb_fileinput');
    if (!fileInput) {
      throw new Error('File input #sb_fileinput not found on page');
    }

    // Set up navigation promise before file upload
    const navPromise = page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
    await fileInput.uploadFile(absolutePath);

    console.log(`[SearchEngine] Uploaded! Waiting for visual search indexing & matches...`);
    await navPromise;
    await new Promise(r => setTimeout(r, 4500));

    const currentUrl = page.url();
    const currentTitle = await page.title();
    console.log(`[SearchEngine] Reached search result: "${currentTitle}"`);
    console.log(`[SearchEngine] Result URL: ${currentUrl}`);

    // If there is a "Pages with this image" tab or link, let's also check for it
    const visualTabs = await page.$$('.tab-head, .vs_tab, a[href*="view=detailv2"]');
    for (const tab of visualTabs) {
      const txt = await page.evaluate(el => el.innerText, tab);
      if (txt && /pages with|similar/i.test(txt)) {
        await tab.click().catch(() => {});
        await new Promise(r => setTimeout(r, 1500));
        break;
      }
    }

    // Extract all structured matches
    const rawMatches = await page.evaluate(() => {
      const results = [];

      // 1. Organic web results
      document.querySelectorAll('.b_algo').forEach(item => {
        const a = item.querySelector('h2 a');
        const desc = item.querySelector('.b_caption p, .b_snippet, .b_lineclamp');
        if (a && a.href) {
          results.push({
            source_type: 'organic_search',
            title: a.innerText.trim(),
            raw_url: a.href,
            snippet: desc ? desc.innerText.trim() : ''
          });
        }
      });

      // 2. Visual search result cards
      document.querySelectorAll('[data-m]').forEach(card => {
        const raw = card.getAttribute('data-m');
        if (raw) {
          try {
            const data = JSON.parse(raw);
            if (data.purl || data.murl) {
              results.push({
                source_type: 'visual_card',
                title: data.t || data.title || '',
                raw_url: data.purl || data.murl,
                image_url: data.murl || null,
                snippet: ''
              });
            }
          } catch (e) {}
        }
      });

      // 3. Side cards / entity answers
      document.querySelectorAll('.b_entityTitle, .b_ans a').forEach(a => {
        if (a.href) {
          results.push({
            source_type: 'entity_link',
            title: a.innerText.trim(),
            raw_url: a.href,
            snippet: ''
          });
        }
      });

      // 4. Any other relevant outbound links on the results page
      document.querySelectorAll('a[href]').forEach(a => {
        const href = a.href;
        if (
          href &&
          !href.startsWith('javascript') &&
          !href.includes('bing.com/search?q=') &&
          !href.includes('bing.com/ck/a?') &&
          (href.includes('twitter.com') ||
            href.includes('x.com') ||
            href.includes('reddit.com') ||
            href.includes('linkedin.com') ||
            href.includes('instagram.com') ||
            href.includes('youtube.com') ||
            href.includes('facebook.com') ||
            href.includes('threads.net') ||
            href.includes('github.com') ||
            href.includes('wikipedia.org'))
        ) {
          results.push({
            source_type: 'direct_social_link',
            title: a.innerText.trim() || a.title || 'Social Link',
            raw_url: href,
            snippet: ''
          });
        }
      });

      return results;
    });

    // Decode Bing redirect tracking URLs (u=a1<base64>)
    function decodeUrl(u) {
      if (!u) return '';
      if (!u.includes('bing.com/ck/a?')) return u;
      try {
        const parsed = new URL(u);
        const uParam = parsed.searchParams.get('u');
        if (uParam && uParam.startsWith('a1')) {
          const b64 = uParam.slice(2);
          const buf = Buffer.from(b64, 'base64');
          return buf.toString('utf-8');
        }
      } catch (e) {}
      return u;
    }

    const uniqueMap = new Map();
    for (const item of rawMatches) {
      const decoded = decodeUrl(item.raw_url);
      if (
        decoded &&
        !decoded.includes('bing.com/') &&
        !decoded.includes('microsoft.com/') &&
        !uniqueMap.has(decoded)
      ) {
        uniqueMap.set(decoded, {
          title: item.title,
          url: decoded,
          source_type: item.source_type,
          snippet: item.snippet,
          image_url: item.image_url || null
        });
      }
    }

    const cleaned = Array.from(uniqueMap.values());
    console.log(`[SearchEngine] Total verified web matches found: ${cleaned.length}`);

    return {
      query_image: absolutePath,
      search_url: currentUrl,
      title: currentTitle,
      total_matches: cleaned.length,
      matches: cleaned
    };
  } finally {
    await browser.close();
  }
}

// If invoked as a CLI script
if (import.meta.main) {
  const target = process.argv[2] || 'sample_images/vitalik_buterin.jpg';
  const outPath = process.argv[3] || 'reverse_search_output.json';
  console.log(`[SearchEngine] Executing reverse search for: ${target}`);
  try {
    const data = await reverseImageSearch(target);
    fs.writeFileSync(outPath, JSON.stringify(data, null, 2));
    console.log(`[SearchEngine] Saved ${data.matches.length} matches to ${outPath}`);
    console.log(`[SearchEngine] Sample matches:`);
    for (const m of data.matches.slice(0, 10)) {
      console.log(` * [${m.source_type}] ${m.title || 'Untitled'}`);
      console.log(`   -> ${m.url}`);
    }
  } catch (err) {
    console.error(`[SearchEngine] Error:`, err);
    process.exit(1);
  }
}
