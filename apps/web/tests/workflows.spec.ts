import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

// This suite requires a disposable/private server with cached daily reports.
// Never enable traces or persist credentials into test artifacts.
const tokenFile=process.env.SCANNER_TEST_TOKEN_FILE;
test.beforeEach(async({page})=>{
  if(!tokenFile)throw new Error('Set SCANNER_TEST_TOKEN_FILE to the private test owner token file');
  await page.goto('/');await page.getByLabel('Owner token').fill(readFileSync(tokenFile,'utf8').trim());
  await page.getByRole('button',{name:'Connect to private server'}).click();
  await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();
});

test('real research map, daily candles and data dates',{tag:'@cached'},async({page})=>{
  await page.getByRole('button',{name:'Research',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Market workspace'})).toBeVisible();
  const row=page.locator('.stock-row').first();await expect(row).toBeVisible({timeout:60000});await row.click();
  await expect(page.getByTestId('daily-candles')).toBeVisible({timeout:60000});
  await expect(page.getByText('One candle = one completed trading session',{exact:false})).toBeVisible();
  for(const label of ['3D','List','1D','1W','1M']) {
    const size=await page.getByRole('button',{name:label,exact:true}).first().boundingBox();
    expect(size?.height).toBeGreaterThanOrEqual(44);
  }
  await page.getByRole('button',{name:'List',exact:true}).click();await expect(page.locator('.scene')).toHaveCount(0);
  expect(await page.evaluate(()=>localStorage.length)).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('scan preview queues a durable offline job once',async({page})=>{
  await page.getByRole('button',{name:'Preview date coverage'}).click();
  await expect(page.getByRole('button',{name:'Queue scan',exact:true})).toBeEnabled();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/scans')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Queue scan',exact:true}).click();const submitted=await (await response).json();expect(submitted.job_id).toBeTruthy();
  await expect(page.getByText(`Job queued: ${submitted.job_id}`)).toBeVisible();
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Activity',exact:true,level:1})).toBeVisible();
  await page.reload();await expect(page.getByRole('heading',{name:'Activity',exact:true,level:1})).toBeVisible();
  await expect(page.locator('.job-row').first()).toBeVisible();
});

test('portfolio journal, audited correction and document review',async({page})=>{
  await page.getByRole('button',{name:'Portfolio',exact:true}).click();
  await page.getByText('Create portfolio',{exact:true}).click();
  const name=`Browser fixture ${Date.now()}`;await page.getByLabel('New portfolio name').fill(name);await page.getByRole('button',{name:'Create',exact:true}).click();
  await expect(page.locator('select').first()).toContainText(name);await page.locator('select').first().selectOption({label:name});
  await page.getByText('Record a journal entry',{exact:true}).click();
  await page.getByLabel('Entry type').selectOption('opening');await page.getByLabel('Actual time (device timezone)').fill('2026-10-02T12:00');
  await page.getByLabel('Symbol',{exact:true}).fill('AVT');await page.getByLabel('Quantity',{exact:true}).fill('2.1234567891');
  await page.getByRole('button',{name:'Record journal entry'}).click();await expect(page.getByText('2.1234567891 shares')).toBeVisible();
  await page.getByRole('button',{name:'Correct',exact:true}).click();const correction=page.getByRole('heading',{name:'Audited correction'}).locator('..').locator('..');
  await correction.getByLabel('Quantity',{exact:true}).fill('3.1234567891');await correction.getByRole('button',{name:'Save audited correction'}).click();await expect(page.getByText('3.1234567891 shares')).toBeVisible();
  await page.getByText('Import & review a document',{exact:true}).click();
  const csv='type,at,symbol,quantity,price,fees,currency,external_ref\nbuy,2026-10-02T15:00:00Z,ARW,1,100,0,USD,browser-import-'+Date.now()+'\n';
  await page.locator('input[type=file]').setInputFiles({name:'transactions.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
  await expect(page.getByText('Status: awaiting_review')).toBeVisible({timeout:60000});
  await page.getByRole('button',{name:'Copy proposals into review editor'}).click();
  await page.getByRole('button',{name:'Confirm reviewed rows'}).click();
  await expect(page.getByText('Status: confirmed')).toBeVisible();
  await expect(page.getByText('1.0000000000 shares')).toBeVisible();
});

test('natural-language agent context preview works while runtime stays disabled',async({page})=>{
  await page.getByRole('button',{name:'More',exact:true}).click();
  await page.getByLabel('Your question').fill('Which candidates have confirmed volume, and what research is missing?');
  await expect(page.getByRole('button',{name:'Queue analysis'})).toBeDisabled();
  await page.getByRole('button',{name:'Preview structured context'}).click();
  await expect(page.locator('summary').filter({hasText:'Agent context v1'})).toBeVisible();
  await page.locator('summary').filter({hasText:'Agent context v1'}).click();
  await expect(page.getByText('stock-scanner.agent-context',{exact:false})).toBeVisible();
});
