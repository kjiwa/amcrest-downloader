Output "assets/demo.gif"
Output "assets/demo_frames.png"

Set FontSize 12
Set Width 1150
Set Height 440
Set Padding 15
Set Theme "Catppuccin Mocha"
Set TypingSpeed 25ms

Hide
Type "export PATH=$PWD/demo/bin:$PATH"
Enter
Type "export AMCREST_PASSWORD=secret"
Enter
Type "export PS1='$ '"
Enter
Type "curl -s http://127.0.0.1:8765/healthz >/dev/null 2>&1 || (python3 demo/mock_camera.py 8765 </dev/null >/dev/null 2>&1 & sleep 1)"
Enter
Type "clear"
Enter
Show

Sleep 300ms
Type "amcrest-downloader --host 192.168.1.100 -u admin --start 2026-09-09T08:00:00 --end 2026-09-09T08:30:00 --list-only"
Sleep 300ms
Enter

Sleep 2500ms

Type "amcrest-downloader --host 192.168.1.100 -u admin --start 2026-09-09T08:00:00 --end 2026-09-09T08:30:00 --output-file morning_clip.mp4"
Sleep 300ms
Enter

Sleep 3s

Hide
Type "curl -s http://127.0.0.1:8765/shutdown >/dev/null 2>&1 || true"
Enter
Type "rm -f morning_clip.mp4"
Enter
Sleep 500ms







