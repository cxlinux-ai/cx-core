# CX Terminal — 30-second demo (VHS tape, https://github.com/charmbracelet/vhs)
#
# Run it through demo/record-30s.sh, which checks that a real AI backend is
# available first. Every answer in the recording is produced live by that backend;
# nothing is mocked or typed in as output.
#
# The model's thinking time is cut from the GIF (Hide / Show around the wait).
# `time` stays in frame so the real latency on the recording machine is visible.

Output demo/out/cx-30s.gif
Output demo/out/cx-30s.mp4

Require cx

Set Shell "bash"
Set FontSize 20
Set Width 1200
Set Height 640
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 45ms
Set WaitTimeout 300s

Hide
Type `export PS1='\[\e[1;36m\]cx-demo\[\e[0m\] $ ' && cd "$(mktemp -d)" && clear`
Enter
Show

# 1. Ask in plain English; CX answers with commands and what they do.
Type "time cx ask 'how do I check disk usage'"
Sleep 400ms
Enter
Hide
Wait+Screen /real/
Show
Sleep 7s

# 2. Ask it to do something: CX shows the plan and waits for consent.
Type "clear"
Enter
Type "time cx ask -d 'show memory usage'"
Sleep 400ms
Enter
Hide
Wait+Screen /Proceed/
Show
Sleep 2s
Type "y"
Sleep 300ms
Enter
Wait+Screen /real/
Sleep 7s

# 3. Package install requests start with a search; nothing is installed.
Type "clear"
Enter
Type "time cx ask 'install nginx'"
Sleep 400ms
Enter
Hide
Wait+Screen /real/
Show
Sleep 7s
