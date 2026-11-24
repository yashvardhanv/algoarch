#!/bin/bash
# usage: sheet.sh take.mp4 out.png [cols] [rows]  -> evenly spaced frames tiled with timestamps
f=$1; o=$2; c=${3:-4}; r=${4:-3}; n=$((c*r))
d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
ffmpeg -v error -y -i "$f" -vf "fps=$n/$d,scale=640:-1,drawtext=text='%{pts\:hms}':x=8:y=8:fontcolor=white:box=1:boxcolor=black@0.6:fontsize=22,tile=${c}x${r}" -frames:v 1 "$o"
