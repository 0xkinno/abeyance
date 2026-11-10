import asyncio, json, subprocess, pathlib, edge_tts
V = "en-US-ChristopherNeural"
out = pathlib.Path("build"); out.mkdir(exist_ok=True)
items = json.load(open("vo.json"))
async def main():
    for it in items:
        f = out / f"{it['id']}.mp3"
        await edge_tts.Communicate(it["text"], V, rate="-2%", pitch="-4Hz").save(str(f))
asyncio.run(main())
t = 0.0; scenes = []
for it in items:
    f = out / f"{it['id']}.mp3"
    d = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(f)]).decode().strip())
    dur = it["lead"] + d + it["tail"]
    scenes.append({"id": it["id"], "start": round(t,3), "dur": round(dur,3), "vo": round(d,3), "lead": it["lead"], "text": it["text"]})
    t += dur
json.dump({"scenes": scenes, "total": round(t,3)}, open("build/scenes.json","w"), indent=1)
print([ (s["id"], s["dur"]) for s in scenes], "total", round(t,2), "vo", round(sum(s["vo"] for s in scenes),1))
