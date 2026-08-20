#!/usr/bin/env python3
"""Assemble the final narrated submission video.

Previous version muxed each beat's video+mp3 into its own mp4 (encoding
audio to AAC), then decoded and re-encoded ALL of those at the final concat
(a second AAC encode), for 5 total audio join points. That double-transcode
plus per-segment AAC frame-boundary rounding is the likely source of the
audible clicks/dropouts reported after review.

This version feeds each beat's *original* mp3 directly into a single
concat filter alongside its video-only footage, so audio is encoded to AAC
exactly once. It also drops the standalone "open" title card entirely --
Beat 1 already opens with its own title card (per the script), so the old
version showed the card, faded it out, then faded the *same* card back in
for Beat 1's internal title -- a duplicate, not a design choice.

Run order: build Beat 1/3 raw footage -> assemble_final.py
"""
import subprocess

run = lambda a: subprocess.run(a, check=True)

# (video path, mp3 path, target duration = mp3's own length, needs padding?)
BEATS = [
    ('media/raw/beat1_video.mp4', 'media/vo/beat1.mp3', 68.498866, False),
    ('media/beat2_intake.mp4', 'media/vo/beat2.mp3', 63.111837, False),
    ('media/raw/beat3_console.mp4', 'media/vo/beat3.mp3', 57.817687, False),
    ('media/beat4_cloud_proof.mp4', 'media/vo/beat4.mp3', 38.127166, True),
]
CLOSE_SECS = 4.2

ins = []
for video, mp3, _dur, _pad in BEATS:
    ins += ['-i', video]
ins += ['-loop', '1', '-t', str(CLOSE_SECS), '-i', 'media/cards/close.png']
for video, mp3, _dur, _pad in BEATS:
    ins += ['-i', mp3]
ins += ['-f', 'lavfi', '-t', str(CLOSE_SECS), '-i', 'anullsrc=r=44100:cl=stereo']

n = len(BEATS)
f, vlabels, alabels = [], [], []
for i, (video, mp3, dur, pad) in enumerate(BEATS):
    pad_step = f'tpad=stop_mode=clone:stop_duration=5.0,' if pad else ''
    f.append(f'[{i}:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1,format=yuv420p,'
              f'{pad_step}trim=duration={dur:.6f},setpts=PTS-STARTPTS[v{i}]')
    a_idx = n + 1 + i  # +1 for the close card video input ahead of the audio inputs
    f.append(f'[{a_idx}:a]aresample=44100,aformat=channel_layouts=stereo,'
              f'atrim=duration={dur:.6f},asetpts=PTS-STARTPTS[a{i}]')
    vlabels.append(f'[v{i}]')
    alabels.append(f'[a{i}]')

close_v_idx = n
close_a_idx = n + 1 + n
f.append(f'[{close_v_idx}:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1,format=yuv420p,'
          f'fade=in:st=0:d=0.6,fade=out:st={CLOSE_SECS - 0.6:.2f}:d=0.6[v{n}]')
f.append(f'[{close_a_idx}:a]aresample=44100,aformat=channel_layouts=stereo[a{n}]')
vlabels.append(f'[v{n}]')
alabels.append(f'[a{n}]')

pairs = ''.join(v + a for v, a in zip(vlabels, alabels))
f.append(f'{pairs}concat=n={n + 1}:v=1:a=1[outv][outa]')

# crf 30: this version feeds raw, less-precompressed source footage (the
# original beat2/beat4 recordings) straight into the encoder instead of
# already-round-tripped intermediates, so it needs a higher crf than before
# to land under GitHub's 100MB non-LFS push limit for this ~3:48 1080p30 video.
run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *ins,
     '-filter_complex', ';'.join(f), '-map', '[outv]', '-map', '[outa]',
     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '30', '-preset', 'slow',
     '-c:a', 'aac', '-b:a', '128k', 'media/blue_toad_fleet_demo.mp4'])
print('media/blue_toad_fleet_demo.mp4')
