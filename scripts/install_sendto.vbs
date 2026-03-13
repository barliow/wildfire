' Run Wildfire GUI with the sent file path. No console window.
' Copy this file to: %APPDATA%\Microsoft\Windows\SendTo\Wildfire.vbs
' Or run: python scripts\install_sendto.py

Set sh = CreateObject("WScript.Shell")
args = ""
For i = 0 To WScript.Arguments.Count - 1
  If i > 0 Then args = args & " "
  args = args & """" & WScript.Arguments(i) & """"
Next
sh.Run "pythonw -m wildfire " & args, 0, False
