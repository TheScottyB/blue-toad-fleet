#!/usr/bin/env python3
"""Composite the recorded walkthrough with title cards and lower thirds.

Run order:  record_walkthrough.mjs -> make_title_cards.mjs -> build_video.py
"""
import json, subprocess

beats = {b['label']: b['t'] for b in json.load(open('media/raw/beats.json'))}
dur = float(subprocess.check_output(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
     '-of', 'csv=p=0', 'media/raw/walkthrough.webm']).strip())
off = dur - beats['end']          # recorder starts before the first beat
V = {k: v + off for k, v in beats.items()}

wins = [('lt-hero',     V['hero'] + 0.4,     V['topology'] - 0.5),
        ('lt-topology', V['topology'] + 0.7, V['curator'] - 0.6),
        ('lt-curator',  V['curator'] + 0.7,  V['memory'] - 0.6),
        ('lt-memory',   V['memory'] + 0.7,   V['sheet'] - 0.6),
        ('lt-sheet',    V['sheet'] + 0.7,    V['bids'] - 0.6),
        ('lt-skips',    V['skips'] + 0.5,    V['end'] - 0.4)]

ins = ['-i', 'media/raw/walkthrough.webm']
for c, _, _ in wins:
    ins += ['-loop', '1', '-i', f'media/cards/{c}.png']

f = ['[0:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1[base]']
prev = 'base'
for i, (c, s, e) in enumerate(wins, 1):
    f.append(f'[{i}:v]format=rgba,fade=in:st={s:.2f}:d=0.45:alpha=1,'
             f'fade=out:st={e-0.45:.2f}:d=0.45:alpha=1[c{i}]')
    f.append(f"[{prev}][c{i}]overlay=0:0:enable='between(t,{s-0.1:.2f},{e:.2f})'[v{i}]")
    prev = f'v{i}'
f.append(f'[{prev}]trim=duration={dur:.2f},setpts=PTS-STARTPTS[main]')

run = lambda a: subprocess.run(a, check=True)
run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *ins,
     '-filter_complex', ';'.join(f), '-map', '[main]',
     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'slow',
     'media/main.mp4'])
for name, secs, fo in (('open', 4.5, 3.9), ('close', 5.5, 4.8)):
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-loop', '1',
         '-t', str(secs), '-i', f'media/cards/{name}.png',
         '-vf', f'fps=30,scale=1920:1080,setsar=1,fade=in:st=0:d=0.7,fade=out:st={fo}:d=0.6',
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', f'media/{name}.mp4'])
open('media/list.txt', 'w').write("file 'open.mp4'\nfile 'main.mp4'\nfile 'close.mp4'\n")
run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat',
     '-safe', '0', '-i', 'media/list.txt', '-c', 'copy',
     'media/blue_toad_fleet_demo.mp4'])
print('media/blue_toad_fleet_demo.mp4')
