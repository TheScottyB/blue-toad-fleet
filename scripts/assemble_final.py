#!/usr/bin/env python3
"""Assemble the final narrated submission video.

open card -> beat1 (intro+gallery) -> beat2 (intake) -> beat3 (console) ->
beat4 (cloud proof) -> close card, each beat already muxed with its
ElevenLabs narration. Title cards get a silent AAC track so every concat
input shares the same codec/stream layout.

Run order: build_beat1/2/3/4 -> assemble_final.py
"""
import os, subprocess

run = lambda a: subprocess.run(a, check=True)


def card(png: str, secs: float, fade_out_at: float, out: str) -> None:
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
         '-loop', '1', '-t', str(secs), '-i', f'media/cards/{png}.png',
         '-f', 'lavfi', '-t', str(secs), '-i', 'anullsrc=r=44100:cl=stereo',
         '-vf', f'fps=30,scale=1920:1080,setsar=1,fade=in:st=0:d=0.7,'
                f'fade=out:st={fade_out_at}:d=0.6',
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'slow',
         '-c:a', 'aac', '-shortest', out])


card('open', 3.2, 2.7, 'media/raw/open_card.mp4')
card('close', 4.2, 3.6, 'media/raw/close_card.mp4')

parts = ['media/raw/open_card.mp4', 'media/beat1_final.mp4', 'media/beat2_final.mp4',
         'media/beat3_final.mp4', 'media/beat4_final.mp4', 'media/raw/close_card.mp4']

# Each part was encoded independently (different aac timestamp bases), which makes
# the concat *demuxer* with `-c copy` unreliable -- it can silently truncate the
# output (no audio, wrong duration) without ffmpeg reporting a fatal error under
# -loglevel error. The concat *filter* decodes and re-encodes everything, so the
# output is always the full, correct length.
ins = []
for p in parts:
    ins += ['-i', p]

f = []
labels = []
for i in range(len(parts)):
    f.append(f'[{i}:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1,format=yuv420p[v{i}]')
    f.append(f'[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}]')
    labels += [f'[v{i}]', f'[a{i}]']
f.append(f"{''.join(labels)}concat=n={len(parts)}:v=1:a=1[outv][outa]")

# crf 26 (not 18) to keep the final file comfortably under GitHub's 100MB
# non-LFS push limit for this ~3:52 1080p30 video.
run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *ins,
     '-filter_complex', ';'.join(f), '-map', '[outv]', '-map', '[outa]',
     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '26', '-preset', 'slow',
     '-c:a', 'aac', '-b:a', '128k', 'media/blue_toad_fleet_demo.mp4'])
print('media/blue_toad_fleet_demo.mp4')
