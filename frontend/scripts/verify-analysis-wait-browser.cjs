// Verify the built app's real router, upload handoff, waiting room and readiness.
// All API requests are intercepted with fixtures: no real account/DB/model use.
// Run after build: SCOUT_BROWSER_EXECUTABLE=/path/to/chromium node this-file.cjs
const assert = require('assert/strict');
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const {spawnSync} = require('child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const build = path.join(root, 'frontend/build');
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'scout-wait-ui-'));
const clip = process.env.SCOUT_TEST_VIDEO_PATH || path.join(root, 'frontend/public/test-video.mp4');
const poster = path.join(work, 'poster.jpg');
const frame = spawnSync(process.env.SCOUT_FFMPEG_EXECUTABLE || 'ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-ss', '25', '-i', clip, '-frames:v', '1', poster]);
if (frame.status !== 0) throw new Error('Cannot extract the test video poster: ' + frame.stderr);
const mime = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.jpg':'image/jpeg', '.png':'image/png', '.svg':'image/svg+xml', '.mp4':'video/mp4', '.ttf':'font/ttf', '.json':'application/json'};
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  const fonts = {'/fixture/head.ttf':path.join(root,'backend/fonts/Barlow-Black.ttf'), '/fixture/body.ttf':path.join(root,'backend/fonts/DMSans-Regular.ttf')};
  let file = fonts[url.pathname] || (url.pathname === '/fixture/poster.jpg' ? poster : url.pathname === '/fixture/clip.mp4' ? clip : path.join(build, url.pathname));
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(build, 'index.html');
  const size = fs.statSync(file).size, range = request.headers.range?.match(/bytes=(\d+)-(\d*)/);
  const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
  response.writeHead(range ? 206 : 200, {'Content-Type':mime[path.extname(file)] || 'application/octet-stream', 'Accept-Ranges':'bytes', 'Content-Length':end-start+1, ...(range ? {'Content-Range':`bytes ${start}-${end}/${size}`} : {})});
  fs.createReadStream(file, {start, end}).pipe(response);
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({...(process.env.SCOUT_BROWSER_EXECUTABLE ? {executablePath:process.env.SCOUT_BROWSER_EXECUTABLE} : {}), headless:true, args:['--no-sandbox','--disable-dev-shm-usage']});
  const errors = [], requests = [];
  const user = {id:'test-owner', role:'admin', full_name:'UI test', email:'ui-test@example.invalid'};
  let doc = {id:'selected', user_id:user.id, is_paid:true, analysis_target:'full', analysis_status:'analyzing', progress_step:2,
    preview:null, full_report:null, full_report_status:null, has_full_report:false, created_at:new Date(Date.now()-120000).toISOString(),
    anchors:Array.from({length:11}, (_,i)=>({t:i*5,box:{x:.3,y:.2,w:.1,h:.3}})), taps_received:11,
    player_details:{player_name:'Orman02',age:11,position:'Winger'}, poster_url:`${origin}/fixture/poster.jpg`, video_url:`${origin}/fixture/clip.mp4`};
  let releaseUpload, offline = false, agentReviews = 0;
  const context = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2});
  await context.addInitScript(({user}) => {
    localStorage.setItem('elite_user',JSON.stringify(user)); localStorage.setItem('elite_token','synthetic-ui-test-token');
    localStorage.setItem('smp_cookie_consent_v1',JSON.stringify({necessary:true,analytics:false,marketing:false}));
    localStorage.setItem('smp_cine_seen_selected','1');
    const originalNow = Date.now; window.__waitTestOffset = Number(sessionStorage.getItem('wait-test-offset')) || 0; Date.now = () => originalNow() + window.__waitTestOffset;
  }, {user});
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.pathname.startsWith('/api/')) {
      requests.push({method:request.method(),path:url.pathname});
      const headers = {'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'Authorization,Content-Type','Access-Control-Allow-Methods':'GET,POST,OPTIONS'};
      const send = data => route.fulfill({status:200,contentType:'application/json',headers,body:JSON.stringify(data)});
      if (request.method() === 'OPTIONS') return send({});
      if (url.pathname === '/api/auth/me') return send(user);
      if (url.pathname === '/api/settings/price') return send({single_price:129});
      if (url.pathname === '/api/reports/upload') {await new Promise(resolve => {releaseUpload = resolve;});return send({...doc});}
      if (url.pathname === '/api/reports/mine') return send([doc]);
      if (url.pathname === '/api/reports/selected') return send({...doc});
      if (url.pathname === '/api/reports/selected/status') {
        if (offline) return route.fulfill({status:503,headers,body:'Temporary test disconnection'});
        return send({...doc,status:doc.analysis_status,preview_ready:doc.analysis_status==='ready'&&!!doc.preview});
      }
      if (url.pathname.endsWith('/generate-full')) return send({full_report_status:'generating'});
      if (url.pathname === '/api/player-selection/mask') return send({status:'unresolved',reason:'Synthetic UI test: no server segmentation requested'});
      if (url.pathname.endsWith('/agent-review')) {agentReviews++;return send({status:'queued',messages:[]});}
      if (url.pathname === '/api/me/player-profiles') return send({items:[]});
      if (url.pathname === '/api/me/upload-eligibility') return send({eligible:true,reason:'admin'});
      if (url.pathname === '/api/me/subscription') return send({subscription:{tier:'premium'},tiers:{},usage:{}});
      if (url.pathname === '/api/progress/players') return send({items:[]});
      if (url.pathname === '/api/dashboard/community') return send({});
      return send({});
    }
    // Offline typography for repeatable layout checks. Uses bundled fonts;
    // live production still loads its normal Google font styles.
    if (url.hostname === 'fonts.googleapis.com') return route.fulfill({contentType:'text/css',body:`@font-face{font-family:'Barlow Condensed';src:url('${origin}/fixture/head.ttf');font-weight:400 900}@font-face{font-family:'DM Sans';src:url('${origin}/fixture/body.ttf');font-weight:100 900}@font-face{font-family:Inter;src:url('${origin}/fixture/body.ttf');font-weight:100 900}`});
    if (url.origin !== origin && !['data:','blob:'].includes(url.protocol)) return route.abort();
    return route.continue();
  });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  // Exercise the real resume-upload entry rather than calling an internal handler.
  await page.goto(origin+'/upload');
  // The production bundle must execute all three shared tap modules, not
  // import asset URLs. No tracking/recognition accuracy is asserted here.
  await page.getByTestId('upload-file-input').setInputFiles(clip);
  await page.getByTestId('upload-mark-start').click();
  await page.waitForFunction(() => {
    const stage = document.querySelector('[data-testid="scout-stage"]');
    const image = document.querySelector('[data-testid="scout-presented-frame"]');
    return stage?.getAttribute('aria-busy') === 'false' && image?.complete && image.naturalWidth > 0;
  }, null, {timeout:120000});
  const stage = await page.getByTestId('scout-stage').boundingBox();
  await page.touchscreen.tap(stage.x + stage.width/2, stage.y + stage.height/2);
  await page.getByTestId('scout-draft-marker').waitFor({timeout:15000});
  await page.getByTestId('scout-close').click();
  const jpeg = fs.readFileSync(poster).toString('base64');
  await page.evaluate(({jpeg,pd,anchors}) => sessionStorage.setItem('smp_resume_upload',JSON.stringify({token:'synthetic-upload-token',fileName:'selected.mp4',fileSize:1234,markerDataUrl:'data:image/jpeg;base64,'+jpeg,markerTimestamp:25,
    markerBox:{x:.3,y:.2,w:.1,h:.3},markerAnchors:anchors,photoSource:'video_crop',form:{...pd,preferred_foot:'left',country:'Denmark',video_type:'match',description:'Synthetic browser test'}})),{jpeg,pd:doc.player_details,anchors:doc.anchors});
  await page.reload();
  await page.getByRole('heading',{name:'Saving your video'}).waitFor({timeout:15000});
  assert(releaseUpload, 'actual upload handler reached the fixture endpoint');
  releaseUpload();
  await page.waitForURL('**/report/selected');
  const waitPhase = phase => page.locator(`[data-testid="analysis-waiting"][data-phase="${phase}"]`).waitFor({timeout:14000});
  await waitPhase('preparing');
  assert.equal(await page.getByTestId('premium-ready-overlay').count(),0);
  assert.equal(await page.getByTestId('bg-analysis-tracker').count(),0);
  // Ten elapsed minutes alone do not advance a phase or invent an ETA.
  await page.evaluate(() => {window.__waitTestOffset += 10*60*1000;sessionStorage.setItem('wait-test-offset',String(window.__waitTestOffset));});
  await page.waitForTimeout(1200);
  assert.equal(await page.getByTestId('analysis-waiting').getAttribute('data-phase'),'preparing');
  assert.equal(await page.getByRole('progressbar').count(),0);
  assert(!/sec left|90 sec|Identity locked/i.test(await page.getByTestId('analysis-waiting').innerText()));
  const beat = async () => {doc.last_progress_at = new Date(await page.evaluate(() => Date.now())).toISOString();};
  doc.analysis_status='ready';doc.progress_step=5;doc.preview={brief_summary:'Initial review'};await beat();
  await waitPhase('queued');
  assert.equal(requests.filter(r=>r.path.endsWith('/generate-full')).length,0,'new upload must not bypass server identity-profile preparation');
  doc.full_report_status='generating';doc.full_pipeline_stage='physical_reconstruction_start';await beat();
  await waitPhase('analyzing');
  assert.equal(agentReviews,0,'waiting page must not invent a human-review stream');
  await page.getByRole('button',{name:'Next football tip'}).click();
  assert(await page.getByRole('button',{name:'Play football tips'}).count());
  assert(await page.getByTestId('analysis-football-tips').innerText().then(t=>t.includes('Separate from your video analysis')));
  await page.getByRole('button',{name:'Watch your uploaded video'}).click();
  assert.equal(await page.locator('.analysis-video-cover video').getAttribute('src'),doc.video_url);
  await page.reload(); await waitPhase('analyzing');
  assert.equal(requests.filter(r=>r.path.endsWith('/generate-full')).length,0,'reload of active job does not start another analysis');
  await page.evaluate(() => document.fonts.ready);
  await beat();
  await page.getByTestId('analysis-server-status').filter({hasText:'Server activity'}).waitFor({timeout:14000});
  await page.evaluate(() => scrollTo(0,0));
  await page.waitForTimeout(400);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),'no horizontal scrolling at iPhone width');
  if(process.env.SCOUT_WAIT_SCREENSHOT_PATH) await page.screenshot({path:process.env.SCOUT_WAIT_SCREENSHOT_PATH,fullPage:true});
  await page.setViewportSize({width:1280,height:900});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:path.join(work,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  offline=true;
  await page.getByTestId('analysis-server-status').filter({hasText:'Connection interrupted'}).waitFor({timeout:14000});
  assert.equal(await page.getByTestId('analysis-waiting').getAttribute('data-phase'),'analyzing');
  offline=false;await beat();
  await page.getByRole('button',{name:'Back to dashboard'}).click(); await page.waitForURL('**/dashboard');
  await page.getByTestId('bg-analysis-tracker').waitFor({timeout:14000});
  assert(!(await page.getByTestId('bg-analysis-tracker').innerText()).includes('ready'));
  await page.getByRole('button',{name:'Follow your analysis'}).click(); await page.waitForURL('**/report/selected');await waitPhase('analyzing');
  doc.full_report_status='verifying';await beat();await waitPhase('verifying');
  doc.full_report={scores:{technical:5,tactical:5,physical:5,mentality:5},scout_view:{},action_timeline:[],video_comments:[]};
  doc.has_full_report=true;doc.full_report_status='finalizing';await beat();await waitPhase('finalizing');
  assert.equal(await page.getByTestId('premium-report-v2').count(),0,'partial report body stays withheld');
  doc.full_report_status='ready';await beat();
  try {
    await page.getByTestId('premium-report-v2').waitFor({timeout:15000});
  } catch(error) {
    console.error(JSON.stringify({pageErrors:errors,body:(await page.locator('body').innerText()).slice(0,2200),recentRequests:requests.slice(-8)},null,2));
    await page.screenshot({path:path.join(work,'ready-failure.png'),fullPage:true});
    throw error;
  }
  assert.equal(await page.getByTestId('analysis-waiting').count(),0,'exactly one transition to completed report');
  assert.deepEqual(errors,[],'no uncaught page errors');
  console.log(JSON.stringify({passed:true,checks:20,productionTapModulesExecute:true,uploadHandoff:true,previewNotDone:true,reloadNoRestart:true,networkRecovery:true,partialBodyWithheld:true,readyReportOpens:true,mobileWidth:390,desktopWidth:1280,apiRequests:requests.length,errors,temporaryOutput:work},null,2));
  await browser.close();await new Promise(resolve=>server.close(resolve));
})().catch(error=>{console.error(error);server.close();process.exit(1);});
