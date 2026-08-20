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
with open('media/raw/final_list.txt', 'w') as fh:
    for p in parts:
        fh.write(f"file '{os.path.abspath(p)}'\n")

run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
     '-i', 'media/raw/final_list.txt', '-c', 'copy', 'media/blue_toad_fleet_demo.mp4'])
print('media/blue_toad_fleet_demo.mp4')
