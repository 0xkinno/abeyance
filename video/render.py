import asyncio, json, subprocess, sys
from playwright.async_api import async_playwright
S = json.load(open('build/scenes.json')); FPS = 30; N = int(S['total'] * FPS)
async def main():
    ff = subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','image2pipe','-framerate',str(FPS),'-c:v','mjpeg','-i','-',
        '-c:v','libx264','-preset','medium','-crf','21','-maxrate','3200k','-bufsize','6400k','-pix_fmt','yuv420p','-r',str(FPS),'build/silent.mp4'], stdin=subprocess.PIPE)
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width':1920,'height':1080})
        await pg.goto('http://127.0.0.1:8765/page.html'); await pg.wait_for_function('window.READY===true')
        for i in range(N):
            await pg.evaluate(f'seek({i/FPS})')
            ff.stdin.write(await pg.screenshot(type='jpeg', quality=94))
            if i % 300 == 0: print(i, N, flush=True)
        await b.close()
    ff.stdin.close(); ff.wait(); print('done')
asyncio.run(main())
